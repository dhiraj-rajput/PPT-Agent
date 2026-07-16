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

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(prefix="/rfp-respond", tags=["rfp-respond"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = PROJECT_ROOT / "private" / "rfp_respond_uploads"
OUTPUT_DIR = PROJECT_ROOT / "output" / "rfp_respond"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory progress tracker keyed by task_id
rfp_respond_tasks: dict = {}


def _safe_name(name: str) -> str:
    stem = Path(name).stem
    ext = Path(name).suffix
    safe_stem = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)[:60]
    return f"{safe_stem}{ext}"


def _run_pipeline_sync(
    task_id: str,
    rfp_path: Path,
    output_name: str,
    template_path: Optional[Path],
) -> None:
    """Run bidforge_cli.py as a subprocess and update progress in-memory."""

    def update(progress: int, message: str, status: str = "processing", filename: Optional[str] = None):
        rfp_respond_tasks[task_id]["progress"] = progress
        rfp_respond_tasks[task_id]["message"] = message
        rfp_respond_tasks[task_id]["status"] = status
        if filename:
            rfp_respond_tasks[task_id]["filename"] = filename

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "bidforge_cli.py"),
        "--rfp", str(rfp_path),
        "--output", output_name,
    ]
    if template_path:
        cmd += ["--template", str(template_path)]

    try:
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
        for line in proc.stdout:
            safe_line = line.strip()
            print(f"[RFP-Respond] {safe_line}")
            if "Step 1" in line:
                update(15, "Parsing uploaded RFP document...")
            elif "checking inventory" in line.lower():
                update(35, "Checking our inventory against requirements...")
            elif "competitor" in line.lower() and "market pricing" in line.lower():
                update(50, "Gathering competitor / market pricing intelligence...")
            elif "Step 3" in line:
                update(65, "Synthesizing pricing strategy...")
            elif "Step 4" in line:
                update(80, "Generating final proposal document...")
            elif line.strip().startswith("SUCCESS:"):
                final_path = line.split("SUCCESS:", 1)[1].strip()
            elif line.strip().startswith("FAILED:"):
                update(0, line.split("FAILED:", 1)[1].strip(), "failed")

        proc.wait()
        if proc.returncode != 0 or not final_path:
            if rfp_respond_tasks[task_id]["status"] != "failed":
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
    rfp_file: UploadFile = File(...),
    template_file: Optional[UploadFile] = File(None),
):
    """
    Upload an RFP (PDF / DOCX / TXT) and optionally a .docx template.
    Returns a task_id to poll via GET /api/rfp-respond/status/{task_id}.
    """
    task_id = uuid.uuid4().hex[:12]
    task_dir = UPLOAD_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    rfp_dest = task_dir / _safe_name(rfp_file.filename or "rfp_upload.pdf")
    with open(rfp_dest, "wb") as f:
        f.write(await rfp_file.read())

    template_dest = None
    if template_file is not None and template_file.filename:
        if not template_file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "Template must be a .docx file.")
        template_dest = task_dir / _safe_name(template_file.filename)
        with open(template_dest, "wb") as f:
            f.write(await template_file.read())

    output_name = f"rfp_respond_{task_id}"
    rfp_respond_tasks[task_id] = {
        "progress": 0,
        "status": "processing",
        "message": "Upload received, queuing pipeline...",
        "filename": None,
    }

    background_tasks.add_task(
        _run_pipeline_sync, task_id, rfp_dest, output_name, template_dest
    )
    return {"status": "started", "task_id": task_id}


@router.get("/status/{task_id}")
def get_status(task_id: str):
    task = rfp_respond_tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Unknown task_id")
    return task


@router.get("/download/{filename}")
def download_result(filename: str):
    safe_filename = Path(filename).name  # prevent path traversal
    for media_type in [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]:
        path = OUTPUT_DIR / safe_filename
        if path.exists():
            return FileResponse(path, media_type=media_type, filename=safe_filename)
    raise HTTPException(404, "File not found")
