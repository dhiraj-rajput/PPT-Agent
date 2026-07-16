"""
api/routes/bidforge.py
-----------------------
Manual-upload entry point for the BidForge pipeline: the user uploads an
RFP file (and optionally a .docx template), and the pipeline runs the same
way api/routes/proposals.py runs the prime/subcontract/partnership
pipelines — as a subprocess, with progress tracked in-memory and polled by
the frontend.
"""

import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(prefix="/bidforge", tags=["bidforge"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = PROJECT_ROOT / "private" / "bidforge_uploads"
OUTPUT_DIR = PROJECT_ROOT / "output" / "bidforge"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory progress tracker, keyed by task_id. Same shape/pattern as
# api/routes/proposals.py's `proposal_tasks`.
bidforge_tasks = {}


def _safe_name(name: str) -> str:
    stem = Path(name).stem
    ext = Path(name).suffix
    safe_stem = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)[:60]
    return f"{safe_stem}{ext}"


def run_bidforge_sync(task_id: str, rfp_path: Path, output_name: str, template_path: Optional[Path]):
    def update(progress: int, message: str, status: str = "processing", filename: Optional[str] = None):
        bidforge_tasks[task_id]["progress"] = progress
        bidforge_tasks[task_id]["message"] = message
        bidforge_tasks[task_id]["status"] = status
        if filename:
            bidforge_tasks[task_id]["filename"] = filename

    cmd = [
        sys.executable, "bidforge_cli.py",
        "--rfp", str(rfp_path),
        "--output", output_name,
    ]
    if template_path:
        cmd += ["--template", str(template_path)]

    try:
        update(5, "Starting BidForge pipeline...")
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT), text=True, encoding="utf-8", errors="ignore",
        )
        final_path = None
        for line in proc.stdout:
            safe_line = line.strip()
            print(f"[BidForge Pipe] {safe_line}")
            if "Step 1" in line:
                update(15, "Parsing uploaded RFP document...")
            elif "checking inventory" in line:
                update(35, "Checking our inventory against requirements...")
            elif "competitor / market pricing" in line:
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
            if bidforge_tasks[task_id]["status"] != "failed":
                update(0, f"Pipeline exited with code {proc.returncode}", "failed")
            return

        filename = Path(final_path).name
        update(100, "Proposal document generated successfully!", "completed", filename)
    except Exception as exc:
        update(0, f"Pipeline failed: {exc}", "failed")


@router.post("/upload")
async def upload_rfp(
    background_tasks: BackgroundTasks,
    rfp_file: UploadFile = File(...),
    template_file: Optional[UploadFile] = File(None),
):
    """
    Upload an RFP document (and optionally a .docx template) and kick off
    the BidForge pipeline in the background. Returns a task_id to poll via
    GET /api/bidforge/status/{task_id}.
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
            raise HTTPException(status_code=400, detail="Template must be a .docx file.")
        template_dest = task_dir / _safe_name(template_file.filename)
        with open(template_dest, "wb") as f:
            f.write(await template_file.read())

    output_name = f"bidforge_{task_id}"
    bidforge_tasks[task_id] = {
        "progress": 0,
        "status": "processing",
        "message": "Upload received, queuing pipeline...",
        "filename": None,
    }

    background_tasks.add_task(run_bidforge_sync, task_id, rfp_dest, output_name, template_dest)

    return {"status": "started", "task_id": task_id}


@router.get("/status/{task_id}")
def get_status(task_id: str):
    task = bidforge_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    return task


@router.get("/download/{filename}")
def download_result(filename: str):
    safe_filename = Path(filename).name  # prevent path traversal
    for ext_dir, media_type in [(OUTPUT_DIR, "application/pdf"), (OUTPUT_DIR, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")]:
        path = ext_dir / safe_filename
        if path.exists():
            return FileResponse(path, media_type=media_type, filename=safe_filename)
    raise HTTPException(status_code=404, detail="File not found")
