"""
app/routes/rfp_respond.py
--------------------------
RFP Auto-Respond — upload an RFP document, get back a fully-written proposal using MySQL.
"""

from __future__ import annotations

import asyncio
import logging
import os
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


def _load_task_result(task: dict) -> dict:
    """task['result'] may come back as a dict (JSON column already decoded
    by the driver) or as a raw JSON string, depending on config -- normalize
    either way so callers don't have to guess."""
    raw = task.get("result") if isinstance(task, dict) else None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            try:
                return ast.literal_eval(raw)
            except Exception:
                return {}
    return {}


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
        "-u",  # unbuffered stdout/stderr -- see note below, this is the fix
               # for progress appearing "stuck" and then jumping to 100%.
        str(PROJECT_ROOT / "scripts" / "bidforge_cli.py"),
        "--rfp", rfp_paths,
        "--output", output_name,
    ]
    if template_path:
        cmd += ["--template", str(template_path)]
    if wizard_config:
        cmd += ["--wizard-config", wizard_config]

    # WHY "-u": when Python's stdout is a pipe (not a real terminal, which is
    # exactly what subprocess.PIPE below gives it), CPython defaults to fully
    # block-buffered output instead of line-buffered. Every "print("Step
    # N...")" call in bidforge_cli.py / pipeline.py was sitting in an internal
    # buffer and never actually reaching this process's `proc.stdout` until
    # either the buffer filled (rare -- these are short lines) or the child
    # process exited. In practice that meant every progress line arrived in
    # one burst right as the subprocess finished, which is exactly the
    # "stuck the whole time, then jumps straight to 100%" symptom. "-u"
    # forces unbuffered I/O for the whole child process regardless of what
    # anything further down the call stack does.
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

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
                env=env,
                bufsize=1,  # line-buffered on our (reading) side too
            )
            final_path = None
            if proc.stdout:
                for line in proc.stdout:
                    safe_line = line.strip()
                    print(f"[RFP-Respond] {safe_line}")
                    # Match on the actual "Step N:" prefix instead of
                    # fragile substrings of whatever wording follows it --
                    # the previous version's "Step 3" branch could never
                    # actually fire (that line always matched the
                    # "competitor"+"market pricing" branch first), and
                    # "Step 4" incorrectly matched the "Step 4: Synthesizing
                    # pricing strategy" line while claiming to be "Generating
                    # final proposal document" -- meanwhile the real Step 5
                    # (the longest step) matched nothing at all, so progress
                    # sat frozen during the slowest part of the pipeline.
                    step_match = re.match(r"^Step (\d+):\s*(.*)$", safe_line)
                    if step_match:
                        step_num = int(step_match.group(1))
                        step_label = step_match.group(2).strip() or safe_line
                        step_progress = {1: 15, 2: 35, 3: 50, 4: 65, 5: 80, 6: 95}.get(step_num, 80)
                        update(step_progress, step_label)
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

def _save_upload_file_sync(file: UploadFile, dest_path: Path, max_bytes: int = 10 * 1024 * 1024) -> None:
    total_written = 0
    with open(dest_path, "wb") as out:
        while True:
            chunk = file.file.read(64 * 1024)
            if not chunk:
                break
            total_written += len(chunk)
            if total_written > max_bytes:
                out.close()
                if dest_path.exists():
                    dest_path.unlink()
                raise HTTPException(
                    status_code=413,
                    detail=f"File '{file.filename}' exceeds the 10MB size limit."
                )
            out.write(chunk)


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

    task_id = uuid.uuid4().hex[:12]
    task_dir = UPLOAD_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    rfp_dests = []
    for file in rfp_files:
        if file.filename:
            dest = task_dir / _safe_name(file.filename)
            await asyncio.to_thread(_save_upload_file_sync, file, dest)
            rfp_dests.append(str(dest))

    if not rfp_dests:
        raise HTTPException(400, "At least one valid RFP file must be uploaded.")

    rfp_paths_str = ",".join(rfp_dests)

    template_dest = None
    if template_file is not None and template_file.filename:
        if not template_file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "Template must be a .docx file.")
        template_dest = task_dir / _safe_name(template_file.filename)
        await asyncio.to_thread(_save_upload_file_sync, template_file, template_dest)
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

    # `result` is where update_task_status actually stores filename (and
    # everything else), but this endpoint previously returned the raw DB row
    # un-flattened while the frontend reads `taskState.filename` at the top
    # level -- meaning the download button never actually had a filename to
    # work with once generation finished. Flatten it here.
    result_data = _load_task_result(task)
    task["filename"] = result_data.get("filename")
    task["result"] = result_data
    return task


@router.get("/download/{filename}")
async def download_result(filename: str, current_user: dict = Depends(get_current_user)):
    safe_filename = Path(filename).name

    if _mysql_available:
        try:
            async for db in get_db_session():
                # NOTE: filename is written into the `result` JSON column by
                # update_task_status (never into `extra_data`, which nothing
                # in this module writes to) -- querying extra_data here meant
                # this lookup never matched any row, silently skipping the
                # ownership check below for every request.
                stmt = select(SQL_TaskStatus).where(SQL_TaskStatus.result["filename"].as_string() == safe_filename)
                task = (await db.execute(stmt)).scalars().first()
                if task and getattr(task, "result", None):
                    extra = task.result if isinstance(task.result, dict) else {}
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
                # NOTE: filename is written into the `result` JSON column by
                # update_task_status (never into `extra_data`, which nothing
                # in this module writes to) -- querying extra_data here meant
                # this lookup never matched any row, silently skipping the
                # ownership check below for every request.
                stmt = select(SQL_TaskStatus).where(SQL_TaskStatus.result["filename"].as_string() == safe_filename)
                task = (await db.execute(stmt)).scalars().first()
                if task and getattr(task, "result", None):
                    extra = task.result if isinstance(task.result, dict) else {}
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
