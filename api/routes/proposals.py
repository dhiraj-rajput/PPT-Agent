import asyncio
import sys
import subprocess
import traceback
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from utils.db_client import get_collection
from api.routes.reports import sync_reports_with_mongo

router = APIRouter(prefix="/proposals", tags=["proposals"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# In-memory progress tracker
# Key: task_key (e.g. "prime-N00178-26-R-3001", "subcontract-FAA-26-CY-0088-Guidehouse", "partnership-Guidehouse")
# Value: {"progress": int, "status": str, "message": str, "filename": str, "mode": str, "solicitation": str, "winner": str}
proposal_tasks = {}

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
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
        if task_key not in proposal_tasks:
            proposal_tasks[task_key] = {}
        proposal_tasks[task_key]["progress"] = prog
        proposal_tasks[task_key]["message"] = msg
        proposal_tasks[task_key]["status"] = stat
        if file_n:
            proposal_tasks[task_key]["filename"] = file_n
        
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast(proposal_tasks), loop)

    try:
        # Initialize
        update_progress(5, "Initializing proposal generation task...")

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


@router.post("/generate")
def trigger_proposal_generation(payload: dict, background_tasks: BackgroundTasks):
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

    proposal_tasks[task_key] = {
        "progress": 5,
        "status": "processing",
        "message": "Initializing proposal generation task...",
        "filename": None,
        "mode": mode,
        "solicitation": solicitation,
        "winner": winner,
        "tender_title": tender_title
    }

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
def generate_partnership(payload: dict, background_tasks: BackgroundTasks):
    """Legacy B2B endpoint — maps to the generic generate endpoint."""
    payload["mode"] = "partnership"
    return trigger_proposal_generation(payload, background_tasks)


@router.get("/status")
def get_task_status(company_name: Optional[str] = None):
    """Check task status and progress for a specific company, or return all active tasks."""
    if not company_name:
        return proposal_tasks
        
    # Check if any task key contains the company_name as a substring
    for key, task in proposal_tasks.items():
        if company_name.lower() in key.lower():
            return task
            
    return {"progress": 0, "status": "idle", "message": "No active tasks."}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Push initial task states upon connection
        await websocket.send_json(proposal_tasks)
        while True:
            # Keep socket alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.get("/recent")
def get_recent_proposals(company_name: str):
    """Retrieve recently generated proposals for a company."""
    try:
        sync_reports_with_mongo()
        reports_col = get_collection("reports")
        
        recent = list(reports_col.find(
            {"company_name": {"$regex": company_name, "$options": "i"}},
            {"_id": 0}
        ).sort("date", -1))
        return recent
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
