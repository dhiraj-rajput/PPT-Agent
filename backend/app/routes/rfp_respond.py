"""
app/routes/rfp_respond.py
--------------------------
RFP Auto-Respond — upload an RFP document, get back a fully-written proposal using MySQL.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import sys
import uuid
import json
import ast
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.auth import get_current_user
from utils.db_client import (
    get_db_session,
    _mysql_available,
    update_task_status,
    get_task_status_db,
    update_task_status_async,
    get_task_status_async,
)
from models.sql_models import TaskStatus as SQL_TaskStatus
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rfp-respond", tags=["rfp-respond"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = PROJECT_ROOT / "private" / "rfp_respond_uploads"
OUTPUT_DIR = PROJECT_ROOT / "output" / "rfp_respond"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _safe_name(name: str) -> str:
    stem = Path(name).stem
    ext = Path(name).suffix
    safe_stem = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)[:60]
    return f"{safe_stem}{ext}"


def _get_task_user_id(task: dict) -> str:
    res_val = task.get("result") or task.get("extra_data") or {}
    if isinstance(res_val, str):
        try:
            res_val = json.loads(res_val)
        except Exception:
            try:
                res_val = ast.literal_eval(res_val)
            except Exception:
                res_val = {}
    return str(res_val.get("userId") or "")


def _register_rfp_report(task_id: str, filename: str) -> None:
    """Insert or update a Report row in MySQL for a completed RFP Auto-Respond document."""
    try:
        from utils.db_client import get_sync_db_session
        from models.sql_models import Report as SQL_Report
        from sqlalchemy import select, insert, update as sql_update
        from datetime import datetime

        file_path = OUTPUT_DIR / filename
        if not file_path.exists():
            return

        file_size = file_path.stat().st_size
        mtime = file_path.stat().st_mtime
        file_ext = file_path.suffix.upper().lstrip('.')

        extra = {
            "company_name": "RFP Auto-Respond",
            "companyName": "RFP Auto-Respond",
            "proposal_type": "RFP Auto-Response",
            "proposalType": "RFP Auto-Response",
            "solicitation_number": task_id,
            "title": filename,
            "subtitle": "AI-generated RFP proposal",
            "date": datetime.fromtimestamp(mtime).strftime("%b %d, %Y"),
            "size": f"{round(file_size / 1024)} KB",
            "ref": task_id,
            "type": file_ext,
            "source": "RFP Auto-Respond",
            "mtime": mtime,
            "rfp_respond": True,
        }

        with get_sync_db_session() as db:
            stmt = select(SQL_Report).where(SQL_Report.filename == filename)
            existing = db.execute(stmt).scalar_one_or_none()
            if not existing:
                db.execute(insert(SQL_Report).values(
                    filename=filename,
                    file_path=str(file_path),
                    file_size=file_size,
                    report_type="RFP Auto-Response",
                    status="Generated",
                    extra_data=extra,
                    created_at=datetime.fromtimestamp(mtime),
                ))
            else:
                db.execute(sql_update(SQL_Report).where(SQL_Report.id == existing.id).values(
                    extra_data=extra, report_type="RFP Auto-Response", status="Generated"
                ))
            db.commit()
    except Exception as exc:
        logger.warning(f"[RFP] Failed to register report in DB: {exc}")


def _run_pipeline_sync(
    task_id: str,
    rfp_paths: str,
    output_name: str,
    template_path: Optional[Path],
    wizard_config: Optional[str] = None,
) -> None:
    """Run bidforge_cli.py as a subprocess and update progress in MySQL."""

    from utils.helpers import get_python_executable
    python_bin = get_python_executable()

    def update(progress: int, message: str, status: str = "processing", filename: Optional[str] = None):
        update_task_status(task_id, "rfp_respond", progress, status, message, filename)

    cmd = [
        python_bin,
        str(PROJECT_ROOT / "scripts" / "bidforge_cli.py"),
        "--rfp", rfp_paths,
        "--output", output_name,
    ]
    if template_path:
        cmd += ["--template", str(template_path)]
    if wizard_config:
        cmd += ["--wizard-config", wizard_config]

    try:
        from utils.helpers import SUBPROCESS_SEMAPHORE

        update(4, "Waiting in queue for document-generation resources...")
        with SUBPROCESS_SEMAPHORE:
            update(5, "Starting RFP Auto-Respond pipeline...")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            final_path = None
            if proc.stdout:
                for line in proc.stdout:
                    safe_line = line.strip()
                    print(f"[RFP-Respond] {safe_line}")
                    if "Step 1" in safe_line:
                        update(15, "Parsing uploaded RFP document...")
                    elif "checking inventory" in safe_line.lower():
                        update(35, "Checking our inventory against requirements...")
                    elif "competitor" in safe_line.lower() and "market pricing" in safe_line.lower():
                        update(50, "Gathering competitor / market pricing intelligence...")
                    elif "Step 3" in safe_line:
                        update(65, "Synthesizing pricing strategy...")
                    elif "Step 4" in safe_line:
                        update(80, "Generating final proposal document...")
                    elif safe_line.startswith("SUCCESS:"):
                        final_path = safe_line.split("SUCCESS:", 1)[1].strip()
                    elif safe_line.startswith("FAILED:"):
                        update(0, safe_line.split("FAILED:", 1)[1].strip(), "failed")

            proc.wait()
            if proc.returncode != 0 or not final_path:
                existing = get_task_status_db(task_id)
                if not existing or existing.get("status") != "failed":
                    update(0, f"Pipeline exited with code {proc.returncode}", "failed")
                return

            filename = Path(final_path).name
            update(100, "Proposal document generated successfully!", "completed", filename)
            _register_rfp_report(task_id, filename)
    except Exception as exc:
        update(0, f"Pipeline failed: {exc}", "failed")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_rfp(
    background_tasks: BackgroundTasks,
    rfp_files: list[UploadFile] = File(...),
    template_file: Optional[UploadFile] = File(None),
    wizard_config: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    if len(rfp_files) > 5:
        raise HTTPException(status_code=400, detail="Cannot upload more than 5 RFP files at once.")

    MAX_FILE_SIZE = 10 * 1024 * 1024

    task_id = uuid.uuid4().hex[:12]
    task_dir = UPLOAD_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    rfp_dests = []
    for file in rfp_files:
        if file.filename:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File '{file.filename}' exceeds the 10MB size limit."
                )
            dest = task_dir / _safe_name(file.filename)

            def write_rfp_file(path_target, file_content):
                with open(path_target, "wb") as f:
                    f.write(file_content)

            await asyncio.to_thread(write_rfp_file, dest, content)
            rfp_dests.append(str(dest))

    if not rfp_dests:
        raise HTTPException(400, "At least one valid RFP file must be uploaded.")

    rfp_paths_str = ",".join(rfp_dests)

    template_dest = None
    if template_file is not None and template_file.filename:
        if not template_file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "Template must be a .docx file.")
        content = await template_file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="Template file exceeds the 10MB size limit.")
        template_dest = task_dir / _safe_name(template_file.filename)

        def write_tmpl_file(path_target, file_content):
            with open(path_target, "wb") as f:
                f.write(file_content)

        await asyncio.to_thread(write_tmpl_file, template_dest, content)
    else:
        from documents.default_template import get_default_template_path
        default_path = get_default_template_path()
        if default_path:
            template_dest = Path(default_path)

    output_name = f"rfp_respond_{task_id}"
    user_id = str(current_user["id"])
    await update_task_status_async(
        task_id,
        "rfp_respond",
        0,
        "processing",
        "Upload received, queuing pipeline...",
        None,
        extra={"userId": user_id, "wizardConfig": wizard_config}
    )

    background_tasks.add_task(
        _run_pipeline_sync, task_id, rfp_paths_str, output_name, template_dest, wizard_config
    )
    return {"status": "started", "task_id": task_id}


@router.get("/status/{task_id}")
async def get_status(task_id: str, current_user: dict = Depends(get_current_user)):
    task = await get_task_status_async(task_id)
    if not task:
        raise HTTPException(404, "Unknown task_id")

    user_id = str(current_user["id"])
    task_owner = _get_task_user_id(task)
    if task_owner and task_owner != user_id:
        raise HTTPException(403, "Access denied: You do not own this task.")
    return task


@router.get("/download/{filename}")
async def download_result(filename: str, current_user: dict = Depends(get_current_user)):
    safe_filename = Path(filename).name

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_TaskStatus).where(SQL_TaskStatus.extra_data["filename"].as_string() == safe_filename)
                task = (await db.execute(stmt)).scalars().first()
                if task and getattr(task, "extra_data", None):
                    extra = task.extra_data if isinstance(task.extra_data, dict) else {}
                    user_id = str(current_user["id"])
                    if extra.get("userId") and str(extra.get("userId")) != user_id:
                        raise HTTPException(403, "Access denied: You do not own this file.")
        except HTTPException:
            raise
        except Exception:
            pass

    path = OUTPUT_DIR / safe_filename
    if path.exists():
        suffix = path.suffix.lower()
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if suffix == ".docx"
            else "application/pdf" if suffix == ".pdf" else "application/octet-stream"
        )
        return FileResponse(path, media_type=media_type, filename=safe_filename)
    raise HTTPException(404, "File not found")


@router.get("/view/{filename}")
async def view_result(filename: str, current_user: dict = Depends(get_current_user)):
    safe_filename = Path(filename).name

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_TaskStatus).where(SQL_TaskStatus.extra_data["filename"].as_string() == safe_filename)
                task = (await db.execute(stmt)).scalars().first()
                if task and getattr(task, "extra_data", None):
                    extra = task.extra_data if isinstance(task.extra_data, dict) else {}
                    user_id = str(current_user["id"])
                    if extra.get("userId") and str(extra.get("userId")) != user_id:
                        raise HTTPException(403, "Access denied: You do not own this file.")

        except HTTPException:
            raise
        except Exception:
            pass

    path = OUTPUT_DIR / safe_filename
    if not path.exists():
        raise HTTPException(404, "File not found")

    suffix = path.suffix.lower()
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if suffix == ".docx"
        else "application/pdf" if suffix == ".pdf" else "application/octet-stream"
    )
    return FileResponse(path, media_type=media_type)


@router.get("/view-upload/{task_id}/{filename}")
async def view_uploaded_source(task_id: str, filename: str, current_user: dict = Depends(get_current_user)):
    task = await get_task_status_async(task_id)
    if not task:
        raise HTTPException(404, "Unknown task_id")
    user_id = str(current_user["id"])
    if _get_task_user_id(task) != user_id:
        raise HTTPException(403, "Access denied: You do not own this task.")

    safe_filename = Path(filename).name
    task_dir = UPLOAD_DIR / task_id
    path = task_dir / safe_filename
    if not path.exists():
        raise HTTPException(404, "File not found")

    suffix = path.suffix.lower()
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if suffix == ".docx"
        else "application/pdf" if suffix == ".pdf" else "application/octet-stream"
    )
    return FileResponse(path, media_type=media_type)
