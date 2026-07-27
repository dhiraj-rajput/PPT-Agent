"""
app/routes/proposals.py
-------------------------
Proposal generation endpoints & WebSockets using Motor async DB client.
"""

import asyncio
import logging
import re
import sys
import subprocess
import traceback
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from utils.db_client import get_async_collection, get_collection, update_task_status, get_task_status_db
from app.routes.reports import sync_reports_with_mongo
from app.core.auth import get_current_user, decode_and_get_user_async

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/proposals", tags=["proposals"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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


async def get_user_proposal_tasks_dict_async(user_id: str) -> dict:
    col = get_async_collection("task_statuses")
    tasks = await col.find({"type": "proposal_generation", "userId": user_id}, {"_id": 0, "expireAt": 0, "updatedAt": 0}).to_list(length=1000)
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
                user_tasks = await get_user_proposal_tasks_dict_async(user_id)
                await websocket.send_json(user_tasks)
            except Exception:
                pass

manager = ConnectionManager()


from utils.helpers import get_python_executable

def run_proposal_generation_sync(mode: str, solicitation: Optional[str] = None, winner: Optional[str] = None, loop=None):
    """
    Synchronous runner executing pipeline subprocesses based on mode.
    Runs from a thread pool.
    """
    sol_num = solicitation or ""
    win_name = winner or ""
    safe_sol = "".join(c if c.isalnum() else "_" for c in sol_num).upper()
    safe_win = "".join(c if c.isalnum() else "_" for c in win_name).lower()

    python_bin = get_python_executable()

    if mode == "prime" or mode == "reference":
        task_key = f"prime-{sol_num}"
        target_filename = f"{sol_num}_prime_proposal.pdf"
        profile_cmd = None
        doc_cmd = [
            python_bin,
            str(PROJECT_ROOT / "scripts" / "respond_to_rfp.py"),
            "--mode", "prime",
            "--solicitation", sol_num
        ]
    elif mode == "subcontract":
        task_key = f"subcontract-{sol_num}-{win_name}"
        target_filename = f"{sol_num}_subcontract_proposal.pdf"
        profile_cmd = [
            python_bin,
            str(PROJECT_ROOT / "main.py"),
            win_name
        ]
        doc_cmd = [
            python_bin,
            str(PROJECT_ROOT / "scripts" / "respond_to_rfp.py"),
            "--mode", "subcontract",
            "--solicitation", sol_num,
            "--winner", win_name
        ]
    else:  # partnership
        task_key = f"partnership-{win_name}"
        target_filename = f"{safe_win}_partnership_proposal.pdf"
        profile_cmd = [
            python_bin,
            str(PROJECT_ROOT / "main.py"),
            win_name
        ]
        doc_cmd = [
            python_bin,
            str(PROJECT_ROOT / "scripts" / "respond_to_rfp.py"),
            "--mode", "partnership",
            "--winner", win_name
        ]

    def update_progress(prog: int, msg: str, stat: str = "processing", file_n: Optional[str] = None):
        update_proposal_task(task_key, prog, stat, msg, file_n)
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast_for_users(), loop)

    try:

        update_progress(10, "Initializing proposal generation task...")

        if solicitation:
            update_progress(12, f"Ensuring RFP documents are downloaded for {solicitation}...")
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
                logger.warning(f"[Proposals] RFP download check warning: {download_err}")

        # Step 1: Profile Scraper
        if profile_cmd:
            update_progress(15, f"Initializing competitor profiling scraper for {win_name}...")
            
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

        # Step 2: Document Generation
        initial_progress = 80 if profile_cmd else 15
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
            logger.error(f"Error compiling proposal: process exited with code {p_doc.returncode}")
            update_progress(80, f"Generation failed (process code {p_doc.returncode})", "failed")
            return

        sync_reports_with_mongo()

        update_progress(100, "Proposal document compiled successfully!", "completed", target_filename)

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
            logger.warning(f"Could not update draft request status: {e}")

    except Exception as e:
        logger.error(f"Subprocess compilation error: {e}")
        update_progress(0, f"Pipeline failed: {str(e)}", "failed")


async def run_proposal_generation_task(mode: str, solicitation: Optional[str] = None, winner: Optional[str] = None):
    """Background task wrapper."""
    loop = asyncio.get_running_loop()
    await asyncio.to_thread(run_proposal_generation_sync, mode, solicitation, winner, loop)


@router.post("")
@router.post("/")
@router.post("/generate")
async def trigger_proposal_generation(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    mode = payload.get("mode", "partnership")
    solicitation = payload.get("solicitation")
    winner = payload.get("winner")
    tender_title = payload.get("tender_title") or "Tender Proposal"

    # Write selected company profile to active_bidding_company.json if provided
    wizard_data = payload.get("wizard_data")
    if wizard_data and "company_profile" in wizard_data:
        company_profile = wizard_data["company_profile"]
        private_dir = PROJECT_ROOT / "private"
        private_dir.mkdir(parents=True, exist_ok=True)
        import json
        with open(private_dir / "active_bidding_company.json", "w", encoding="utf-8") as f:
            json.dump(company_profile, f, indent=2)
    else:
        # Remove active bidding company profile to fallback to default
        active_bidding_path = PROJECT_ROOT / "private" / "active_bidding_company.json"
        if active_bidding_path.exists():
            try:
                active_bidding_path.unlink()
            except Exception:
                pass

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

    try:
        drafts_col = get_async_collection("draft_requests")
        await drafts_col.update_one(
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
async def generate_partnership(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    payload["mode"] = "partnership"
    return await trigger_proposal_generation(payload, background_tasks, current_user)


@router.get("")
async def list_proposal_tasks(current_user: dict = Depends(get_current_user)):
    return await get_user_proposal_tasks_dict_async(str(current_user["_id"]))


@router.get("/status")
async def get_task_status(
    company_name: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    if not company_name:
        return {"progress": 0, "status": "idle", "message": "No company name provided."}
        
    user_tasks = await get_user_proposal_tasks_dict_async(str(current_user["_id"]))
    for key, task in user_tasks.items():
        if company_name.lower() in key.lower():
            return task
            
    return {"progress": 0, "status": "idle", "message": "No active tasks."}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    if not token:
        await websocket.accept()
        await websocket.close(code=1008, reason="Token missing")
        return
    
    user_id = None
    user = await decode_and_get_user_async(token)
    if user:
        user_id = str(user.get("_id") or user.get("id", ""))
    else:
        # Fallback decode if user collection record wasn't retrieved
        try:
            from app.core.auth import SECRET_KEY, ALGORITHM, jwt
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = str(payload.get("sub", ""))
        except Exception:
            pass

    if not user_id:
        await websocket.accept()
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await manager.connect(websocket, user_id)
    try:
        await websocket.send_json(await get_user_proposal_tasks_dict_async(user_id))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.get("/recent")
async def get_recent_proposals(
    company_name: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        await asyncio.to_thread(sync_reports_with_mongo)
        reports_col = get_async_collection("reports")
        
        recent = await reports_col.find(
            {"company_name": {"$regex": re.escape(company_name), "$options": "i"}},
            {"_id": 0}
        ).sort("date", -1).to_list(length=100)
        return recent
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
