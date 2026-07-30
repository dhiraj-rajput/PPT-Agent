"""
app/routes/proposals.py
-------------------------
Proposal generation endpoints & WebSockets using MySQL.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
import subprocess
import traceback
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from utils.db_client import get_db_session, get_sync_db_session, _mysql_available, update_task_status, get_task_status_db
from app.routes.reports import sync_reports_with_db, _format_report_dict
from app.core.auth import get_current_user, decode_and_get_user_async
from models.sql_models import (
    TaskStatus as SQL_TaskStatus,
    DraftRequest as SQL_DraftRequest,
    Tender as SQL_Tender,
    Report as SQL_Report,
)
from sqlalchemy import select, update, insert, delete, func, or_, and_

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
    result = {}
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_TaskStatus).where(SQL_TaskStatus.result["userId"].as_string() == user_id)
                res = await db.execute(stmt)
                for t in res.scalars().all():
                    extra = t.result or {}
                    result[t.task_id] = {
                        "progress": t.progress,
                        "status": t.status,
                        "message": t.message,
                        "filename": extra.get("filename"),
                        "mode": extra.get("mode"),
                        "solicitation": extra.get("solicitation"),
                        "winner": extra.get("winner"),
                        "tender_title": extra.get("tender_title")
                    }
        except Exception as e:
            logger.error(f"Failed to fetch proposal tasks from MySQL: {e}")
    return result


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[tuple[WebSocket, str]] = []

    async def connect(self, websocket: WebSocket, user_id: str):
        try:
            from starlette.websockets import WebSocketState
            if getattr(websocket, "client_state", None) != WebSocketState.CONNECTED:
                await websocket.accept()
        except Exception as e:
            logger.warning(f"[WebSocket] accept failed or already accepted: {e}")
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


@router.get("/active-tasks")
async def get_active_proposal_tasks(current_user: dict = Depends(get_current_user)):
    """HTTP polling fallback for environments where WebSockets are not enabled (e.g. shared hosting)."""
    user_id = str(current_user.get("id") or "")
    return await get_user_proposal_tasks_dict_async(user_id)


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
                notice_id = solicitation
                with get_sync_db_session() as db:
                    stmt_t = select(SQL_Tender).where(SQL_Tender.solicitation_number == solicitation)
                    tender = db.execute(stmt_t).scalars().first()
                    if tender:
                        notice_id = str(getattr(tender, "id", "") or solicitation)

                from app.routes.tenders import ensure_rfp_downloaded
                ensure_rfp_downloaded(str(notice_id), str(solicitation))

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

        sync_reports_with_db()

        update_progress(100, "Proposal document compiled successfully!", "completed", target_filename)

        try:
            with get_sync_db_session() as db:
                db.execute(
                    update(SQL_DraftRequest)
                    .where(SQL_DraftRequest.notice_id == solicitation, SQL_DraftRequest.mode == mode)
                    .values(draft_status="completed", updated_at=datetime.utcnow())
                )
                db.commit()
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
        import uuid
        task_id = uuid.uuid4().hex[:8]
        with open(private_dir / f"company_profile_{task_id}.json", "w", encoding="utf-8") as f:
            json.dump(company_profile, f, indent=2)
    else:
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
            "userId": str(current_user["id"])
        }
    )

    background_tasks.add_task(run_proposal_generation_task, mode, solicitation, winner)

    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(
                    update(SQL_DraftRequest)
                    .where(SQL_DraftRequest.notice_id == solicitation, SQL_DraftRequest.mode == mode)
                    .values(draft_status="processing", updated_at=datetime.utcnow())
                )
                await db.commit()
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
    return await get_user_proposal_tasks_dict_async(str(current_user["id"]))


@router.get("/status")
async def get_task_status(
    company_name: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    if not company_name:
        return {"progress": 0, "status": "idle", "message": "No company name provided."}
        
    user_tasks = await get_user_proposal_tasks_dict_async(str(current_user["id"]))
    for key, task in user_tasks.items():
        if company_name.lower() in key.lower():
            return task
            
    return {"progress": 0, "status": "idle", "message": "No active tasks."}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    from starlette.websockets import WebSocketState
    
    if not token:
        try:
            if getattr(websocket, "client_state", None) != WebSocketState.CONNECTED:
                await websocket.accept()
            await websocket.close(code=1008, reason="Token missing")
        except Exception:
            pass
        return
    
    user_id = None
    user = await decode_and_get_user_async(token)
    if user:
        user_id = str(user.get("id", ""))
    else:
        try:
            from app.core.auth import SECRET_KEY, ALGORITHM, jwt
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = str(payload.get("sub", ""))
        except Exception:
            pass

    if not user_id:
        try:
            if getattr(websocket, "client_state", None) != WebSocketState.CONNECTED:
                await websocket.accept()
            await websocket.close(code=1008, reason="Unauthorized")
        except Exception:
            pass
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
        await asyncio.to_thread(sync_reports_with_db)
        
        recent = []
        if _mysql_available:
            async for db in get_db_session():
                stmt = select(SQL_Report).order_by(SQL_Report.created_at.desc())
                res = await db.execute(stmt)
                for r in res.scalars().all():
                    r_dict = _format_report_dict(r)
                    if company_name.lower() in r_dict.get("company_name", "").lower():
                        recent.append(r_dict)
        return recent
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
