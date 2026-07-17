"""
api/routes/rfp_respond.py
--------------------------
RFP Auto-Respond — upload an RFP document, get back a fully-written proposal.

This is the OrbitAvanya-integrated version of what was called "BidForge" in
the standalone project. It uses the same pipeline (bidforge/ package at the
project root) but is surfaced under /api/rfp-respond to match the project
naming conventions.

Endpoints:
  POST /api/rfp-respond/upload              — upload RFP + optional template, kick off pipeline
  GET  /api/rfp-respond/status/{task_id}    — poll for progress
  GET  /api/rfp-respond/download/{filename} — download the generated proposal
"""

from __future__ import annotations

import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from app.core.auth import get_current_user

router = APIRouter(prefix="/rfp-respond", tags=["rfp-respond"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = PROJECT_ROOT / "private" / "rfp_respond_uploads"
OUTPUT_DIR = PROJECT_ROOT / "output" / "rfp_respond"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from utils.db_client import update_task_status, get_task_status_db, get_collection


def _safe_name(name: str) -> str:
    stem = Path(name).stem
    ext = Path(name).suffix
    safe_stem = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)[:60]
    return f"{safe_stem}{ext}"


def _run_pipeline_sync(
    task_id: str,
    rfp_paths: str,
    output_name: str,
    template_path: Optional[Path],
) -> None:
    """Run bidforge_cli.py as a subprocess and update progress in-memory."""

    def update(progress: int, message: str, status: str = "processing", filename: Optional[str] = None):
        update_task_status(task_id, "rfp_respond", progress, status, message, filename)

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "bidforge_cli.py"),
        "--rfp", rfp_paths,
        "--output", output_name,
    ]
    if template_path:
        cmd += ["--template", str(template_path)]

    try:
        from utils.helpers import SUBPROCESS_SEMAPHORE
        update(4, "Waiting in queue for resources...")
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
    current_user: dict = Depends(get_current_user),
):
    """
    Upload one or more RFP files (PDF / DOCX / TXT) and optionally a .docx template.
    Returns a task_id to poll via GET /api/rfp-respond/status/{task_id}.
    """
    if len(rfp_files) > 5:
        raise HTTPException(status_code=400, detail="Cannot upload more than 5 RFP files at once.")

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    task_id = uuid.uuid4().hex[:12]
    task_dir = UPLOAD_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    rfp_dests = []
    for file in rfp_files:
        if file.filename:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' exceeds the 10MB size limit.")
            dest = task_dir / _safe_name(file.filename)
            with open(dest, "wb") as f:
                f.write(content)
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
            raise HTTPException(status_code=400, detail="Template file exceeds the 10MB size limit.")
        template_dest = task_dir / _safe_name(template_file.filename)
        with open(template_dest, "wb") as f:
            f.write(content)

    output_name = f"rfp_respond_{task_id}"
    user_id = current_user.get("user_id") or current_user.get("id")
    update_task_status(
        task_id,
        "rfp_respond",
        0,
        "processing",
        "Upload received, queuing pipeline...",
        None,
        extra={"userId": str(user_id)}
    )

    background_tasks.add_task(
        _run_pipeline_sync, task_id, rfp_paths_str, output_name, template_dest
    )
    return {"status": "started", "task_id": task_id}


@router.get("/status/{task_id}")
def get_status(task_id: str, current_user: dict = Depends(get_current_user)):
    task = get_task_status_db(task_id)
    if not task:
        raise HTTPException(404, "Unknown task_id")
    
    # Ownership Check
    user_id = current_user.get("user_id") or current_user.get("id")
    if task.get("userId") and task.get("userId") != str(user_id):
        raise HTTPException(403, "Access denied: You do not own this task.")
    return task


@router.get("/download/{filename}")
def download_result(filename: str, current_user: dict = Depends(get_current_user)):
    safe_filename = Path(filename).name  # prevent path traversal
    
    # Ownership Check
    col = get_collection("task_statuses")
    task = col.find_one({"filename": safe_filename})
    if task:
        user_id = current_user.get("user_id") or current_user.get("id")
        if task.get("userId") and task.get("userId") != str(user_id):
            raise HTTPException(403, "Access denied: You do not own this file.")

    for media_type in [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]:
        path = OUTPUT_DIR / safe_filename
        if path.exists():
            return FileResponse(path, media_type=media_type, filename=safe_filename)
    raise HTTPException(404, "File not found")
