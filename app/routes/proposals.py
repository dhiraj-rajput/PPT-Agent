import asyncio
import re
import sys
import subprocess
import traceback
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from utils.db_client import get_collection
from app.routes.reports import sync_reports_with_mongo
from app.core.auth import get_current_user

router = APIRouter(prefix="/proposals", tags=["proposals"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# MongoDB-backed progress tracker
from utils.db_client import update_task_status, get_task_status_db, get_collection

def update_proposal_task(task_key: str, progress: int, status: str, message: str, filename: Optional[str] = None, extra: Optional[dict] = None):
    existing = get_task_status_db(task_key) or {}
    merged_extra = {
        "mode": existing.get("mode"),
        "solicitation": existing.get("solicitation"),
        "winner": existing.get("winner"),
        "tender_title": existing.get("tender_title"),
        "userId": existing.get("userId")
    }
    if extra:
        merged_extra.update(extra)
    update_task_status(task_key, "proposal_generation", progress, status, message, filename, merged_extra)

def get_all_proposal_tasks_dict() -> dict:
    col = get_collection("task_statuses")
    tasks = list(col.find({"type": "proposal_generation"}, {"_id": 0, "expireAt": 0, "updatedAt": 0}))
    result = {}
    for t in tasks:
        task_id = t["task_id"]
        result[task_id] = {
            "progress": t["progress"],
            "status": t["status"],
            "message": t["message"],
            "filename": t.get("filename"),
            "mode": t.get("mode"),
            "solicitation": t.get("solicitation"),
            "winner": t.get("winner"),
            "tender_title": t.get("tender_title")
        }
    return result

def get_user_proposal_tasks_dict(user_id: str) -> dict:
    col = get_collection("task_statuses")
    tasks = list(col.find({"type": "proposal_generation", "userId": user_id}, {"_id": 0, "expireAt": 0, "updatedAt": 0}))
    result = {}
    for t in tasks:
        task_id = t["task_id"]
        result[task_id] = {
            "progress": t["progress"],
            "status": t["status"],
            "message": t["message"],
            "filename": t.get("filename"),
            "mode": t.get("mode"),
            "solicitation": t.get("solicitation"),
            "winner": t.get("winner"),
            "tender_title": t.get("tender_title")
        }
    return result

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[tuple[WebSocket, str]] = []

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections.append((websocket, user_id))

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [item for item in self.active_connections if item[0] != websocket]

    async def broadcast_for_users(self):
        for websocket, user_id in self.active_connections:
            try:
                user_tasks = get_user_proposal_tasks_dict(user_id)
                await websocket.send_json(user_tasks)
            except Exception:
                pass

manager = ConnectionManager()

def run_proposal_generation_sync(mode: str, solicitation: Optional[str] = None, winner: Optional[str] = None, loop=None):
    """
    Synchronous runner executing pipeline subprocesses based on mode.
    Runs from a thread pool.
    """
    # 1. Resolve key and output file name
    sol_num = solicitation or ""
    win_name = winner or ""
    safe_sol = "".join(c if c.isalnum() else "_" for c in sol_num).upper()
    safe_win = "".join(c if c.isalnum() else "_" for c in win_name).lower()

    if mode == "prime" or mode == "reference":
        task_key = f"prime-{sol_num}"
        target_filename = f"{sol_num}_prime_proposal.pdf"
        profile_cmd = None
        doc_cmd = [
            sys.executable,
            "scripts/respond_to_rfp.py",
            "--mode", "prime",
            "--solicitation", sol_num
        ]
    elif mode == "subcontract":
        task_key = f"subcontract-{sol_num}-{win_name}"
        target_filename = f"{sol_num}_subcontract_proposal.pdf"
        profile_cmd = [
            sys.executable,
            "main.py",
            win_name
        ]
        doc_cmd = [
            sys.executable,
            "scripts/respond_to_rfp.py",
            "--mode", "subcontract",
            "--solicitation", sol_num,
            "--winner", win_name
        ]
    else:  # partnership
        task_key = f"partnership-{win_name}"
        target_filename = f"{safe_win}_partnership_proposal.pdf"
        profile_cmd = [
            sys.executable,
            "main.py",
            win_name
        ]
        doc_cmd = [
            sys.executable,
            "scripts/respond_to_rfp.py",
            "--mode", "partnership",
            "--winner", win_name
        ]

    def update_progress(prog: int, msg: str, stat: str = "processing", file_n: Optional[str] = None):
        update_proposal_task(task_key, prog, stat, msg, file_n)
        
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast_for_users(), loop)

    try:
        from utils.helpers import SUBPROCESS_SEMAPHORE
        update_progress(4, "Waiting in queue for resources...")
        with SUBPROCESS_SEMAPHORE:
            # Initialize
            update_progress(5, "Initializing proposal generation task...")

            # Ensure RFP documents are downloaded for prime/subcontract modes
            if solicitation:
                update_progress(8, f"Ensuring RFP documents are downloaded for {solicitation}...")
                try:
                    tenders_col = get_collection("tenders")
                    tender = tenders_col.find_one({
                        "$or": [
                            {"solicitation_number": {"$regex": f"^{re.escape(solicitation)}$", "$options": "i"}},
                            {"solicitation_number": solicitation}
                        ]
                    })
                    notice_id = tender["id"] if (tender and "id" in tender) else solicitation
                    
                    from app.routes.tenders import ensure_rfp_downloaded
                    ensure_rfp_downloaded(notice_id, solicitation)
                except Exception as download_err:
                    print(f"[Proposals] RFP download check warning: {download_err}")

            # ---- Step 1: Profile Scraper (if applicable) ----
            if profile_cmd:
                update_progress(10, f"Initializing competitor profiling scraper for {win_name}...")
                
                p_profile = subprocess.Popen(
                    profile_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(PROJECT_ROOT),
                    text=True,
                    encoding="utf-8",
                    errors="ignore"
                )
                
                if p_profile.stdout:
                    for line_str in p_profile.stdout:
                        safe_line = line_str.encode('ascii', errors='replace').decode('ascii').strip()
                        print(f"[Profile Pipe] {safe_line}")
                        
                        if "classify_input" in line_str:
                            update_progress(20, "Classifying target input data...")
                        elif "discover_website" in line_str:
                            update_progress(30, "Locating target company website...")
                        elif "discover_linkedin" in line_str:
                            update_progress(40, "Searching LinkedIn profiles...")
                        elif "trigger_scrapers" in line_str:
                            update_progress(50, "Triggering social & web scrapers...")
                        elif "run_website_agent" in line_str:
                            update_progress(60, "Analyzing website capabilities...")
                        elif "run_compactor" in line_str:
                            update_progress(75, "Compacting profiling metrics...")
                
                p_profile.wait()

            # ---- Step 2: Document Generation ----
            initial_progress = 80 if profile_cmd else 10
            update_progress(initial_progress, "Compiling proposal document...")
            
            p_doc = subprocess.Popen(
                doc_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            
            if p_doc.stdout:
                for line_str in p_doc.stdout:
                    safe_line = line_str.encode('ascii', errors='replace').decode('ascii').strip()
                    print(f"[Proposal Doc] {safe_line}")
                    
                    if "Step 1" in line_str:
                        if mode == "prime" or mode == "reference":
                            update_progress(25, "Parsing RFP solicitation documents...")
                        else:
                            update_progress(80, "Parsing RFP solicitation requirements...")
                    elif "Step 2" in line_str:
                        if mode == "prime" or mode == "reference":
                            update_progress(40, "Synthesizing section layouts...")
                        else:
                            update_progress(85, "Synthesizing teaming pitch outline...")
                    elif "Step 3" in line_str:
                        if mode == "prime" or mode == "reference":
                            update_progress(55, "Generating technical & administrative sections via Ollama LLM...")
                        else:
                            update_progress(90, "Compiling proposal document...")
                    elif "Step 4" in line_str or "Step 5" in line_str or "Generating DOCX-styled PDF" in line_str or "DOCX-styled PDF" in line_str:
                        update_progress(90, "Compiling Word document and rendering PDF...")
                    
            p_doc.wait()
            
            if p_doc.returncode != 0:
                print(f"Error compiling proposal: process exited with code {p_doc.returncode}")
                update_progress(80, f"Generation failed (process code {p_doc.returncode})", "failed")
                return

            # Sync MongoDB reports collection
            sync_reports_with_mongo()

            update_progress(100, "Proposal document compiled successfully!", "completed", target_filename)

        # Update draft_requests status in MongoDB if applicable
        try:
            drafts_col = get_collection("draft_requests")
            drafts_col.update_one(
                {
                    "$or": [
                        {"notice_id": solicitation},
                        {"solicitation_number": solicitation}
                    ],
                    "mode": mode
                },
                {"$set": {"draft_status": "completed", "completed_filename": target_filename}}
            )
        except Exception as e:
            print(f"Warning: Could not update draft request status: {e}")

    except Exception as e:
        traceback.print_exc()
        print(f"Subprocess compilation error: {e}")
        update_progress(0, f"Pipeline failed: {str(e)}", "failed")


async def run_proposal_generation_task(mode: str, solicitation: Optional[str] = None, winner: Optional[str] = None):
    """Background task wrapper."""
    loop = asyncio.get_running_loop()
    await asyncio.to_thread(run_proposal_generation_sync, mode, solicitation, winner, loop)


@router.post("")
@router.post("/")
@router.post("/generate")
def trigger_proposal_generation(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Start any proposal generation pipeline (prime, subcontract, partnership).
    """
    mode = payload.get("mode", "partnership")
    solicitation = payload.get("solicitation")
    winner = payload.get("winner")
    tender_title = payload.get("tender_title") or "Tender Proposal"

    if mode in ("prime", "subcontract", "reference") and not solicitation:
        raise HTTPException(status_code=400, detail="solicitation number is required for this mode")
    if mode in ("subcontract", "partnership") and not winner:
        raise HTTPException(status_code=400, detail="winner company name is required for this mode")

    if mode == "prime" or mode == "reference":
        task_key = f"prime-{solicitation}"
    elif mode == "subcontract":
        task_key = f"subcontract-{solicitation}-{winner}"
    else:
        task_key = f"partnership-{winner}"

    update_proposal_task(
        task_key,
        5,
        "processing",
        "Initializing proposal generation task...",
        None,
        {
            "mode": mode,
            "solicitation": solicitation,
            "winner": winner,
            "tender_title": tender_title,
            "userId": str(current_user["_id"])
        }
    )

    background_tasks.add_task(run_proposal_generation_task, mode, solicitation, winner)

    # Also update draft status in DB if exists
    try:
        drafts_col = get_collection("draft_requests")
        drafts_col.update_one(
            {
                "$or": [
                    {"notice_id": solicitation},
                    {"solicitation_number": solicitation}
                ],
                "mode": mode
            },
            {"$set": {"draft_status": "processing"}}
        )
    except Exception:
        pass

    return {
        "status": "started",
        "task_key": task_key,
        "message": "Proposal generation pipeline execution queued."
    }


@router.post("/generate-partnership")
def generate_partnership(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Legacy B2B endpoint — maps to the generic generate endpoint."""
    payload["mode"] = "partnership"
    return trigger_proposal_generation(payload, background_tasks)


@router.get("")
def list_proposal_tasks(current_user: dict = Depends(get_current_user)):
    """Retrieve all active proposal generation tasks for the current user."""
    return get_user_proposal_tasks_dict(str(current_user["_id"]))


@router.get("/status")
def get_task_status(
    company_name: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Check task status and progress for a specific company, or return all active tasks for the current user."""
    user_id = str(current_user["_id"])
    user_tasks = get_user_proposal_tasks_dict(user_id)
    if not company_name:
        return user_tasks
        
    # Check if any task key contains the company_name as a substring
    for key, task in user_tasks.items():
        if company_name.lower() in key.lower():
            return task
            
    return {"progress": 0, "status": "idle", "message": "No active tasks."}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    if not token:
        await websocket.close(code=1008)
        return
    
    from app.core.auth import decode_and_get_user
    user = decode_and_get_user(token)
    if not user:
        await websocket.close(code=1008)
        return

    user_id = str(user["_id"])
    await manager.connect(websocket, user_id)
    try:
        # Push initial task states upon connection scoped to user
        await websocket.send_json(get_user_proposal_tasks_dict(user_id))
        while True:
            # Keep socket alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.get("/recent")
def get_recent_proposals(
    company_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve recently generated proposals for a company."""
    try:
        sync_reports_with_mongo()
        reports_col = get_collection("reports")
        
        recent = list(reports_col.find(
            {"company_name": {"$regex": re.escape(company_name), "$options": "i"}},
            {"_id": 0}
        ).sort("date", -1))
        return recent
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
