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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

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
    parsed_rfp_json_path: Optional[str] = None,
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
    if parsed_rfp_json_path:
        cmd += ["--parsed-rfp-json", parsed_rfp_json_path]

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
                    # Match on the leading "Step N:" marker itself rather than
                    # fragile substrings of whatever wording happens to follow
                    # it -- the old version matched some steps only by
                    # coincidence (e.g. "Step 3" never actually matched
                    # anything because that line always hit the "competitor"
                    # branch first) and silently stopped updating progress at
                    # all for RFP types that skip the inventory/competitor
                    # stages (see pipeline.py).
                    step_match = re.match(r"^Step (\d+):", safe_line)
                    step_num = int(step_match.group(1)) if step_match else None
                    if step_num == 1:
                        update(10, "Parsing uploaded RFP document (this can take a while for large tenders)...")
                    elif step_num == 2:
                        update(40, safe_line.split(":", 1)[1].strip() if ":" in safe_line else "Exploring requirements...")
                    elif step_num == 3:
                        update(55, safe_line.split(":", 1)[1].strip() if ":" in safe_line else "Exploring market data...")
                    elif step_num == 4:
                        update(70, "Synthesizing pricing strategy...")
                    elif step_num == 5:
                        update(85, "Generating final proposal document...")
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


def _load_task_result(task: dict) -> Dict[str, Any]:
    """task['result'] may come back as a dict (JSON column already decoded)
    or a JSON string, depending on driver/config -- normalize either way."""
    raw = task.get("result") if isinstance(task, dict) else None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


# ---------------------------------------------------------------------------
# /analyze -- parses the uploaded RFP FIRST (before any wizard questions are
# shown), builds an RFP-specific outline, and surfaces genuinely-necessary
# clarifying questions derived from THIS document. This replaces the old
# flow where the pre-generation wizard opened immediately on file selection
# and asked generic, RFP-blind questions because the file hadn't been
# uploaded (let alone parsed) yet.
# ---------------------------------------------------------------------------

def _run_analyze_sync(task_id: str, user_id: str, rfp_paths: str, template_path: Optional[str]) -> None:
    def update(progress: int, message: str, status: str = "processing", **extra_fields: Any) -> None:
        payload = {"userId": user_id, **extra_fields}
        update_task_status(task_id, "rfp_analyze", progress, status, message, None, extra=payload)

    task_dir = UPLOAD_DIR / task_id
    try:
        update(8, "Reading uploaded RFP document(s)...")

        from documents.bidforge.parse import parse_uploaded_rfp
        parsed_rfp = parse_uploaded_rfp(rfp_paths, task_id)

        company_context = ""
        if template_path:
            try:
                from documents.template_analyzer import analyze_template
                profile = analyze_template(template_path)
                company_context = profile.to_company_profile_summary()
            except Exception as exc:
                logger.debug(f"[RFP-Analyze] Could not extract company profile from template: {exc}")

        update(45, "Building a proposal outline tailored to this RFP's own requirements and annexures...")
        from documents.bidforge.outline import build_outline
        outline = build_outline(parsed_rfp, company_context=company_context)

        update(75, "Checking what still needs your input before we can generate an accurate response...")
        from documents.bidforge.clarify import build_clarifying_questions
        clarify = build_clarifying_questions(parsed_rfp, company_context=company_context, answered=[], round_number=1)

        # Persist everything needed downstream so /clarify and /upload can
        # reuse this exact parse instead of re-running (potentially dozens
        # of chunked LLM calls) from scratch.
        (task_dir / "parsed_rfp.json").write_text(json.dumps(parsed_rfp, default=str), encoding="utf-8")
        (task_dir / "outline.json").write_text(json.dumps(outline, default=str), encoding="utf-8")
        (task_dir / "rfp_paths.txt").write_text(rfp_paths, encoding="utf-8")
        (task_dir / "resolved_answers.json").write_text("[]", encoding="utf-8")
        if template_path:
            (task_dir / "template_path.txt").write_text(template_path, encoding="utf-8")

        result_payload = {
            "rfp_type": parsed_rfp.get("rfp_type"),
            "summary": parsed_rfp.get("summary"),
            "metadata": parsed_rfp.get("metadata"),
            "missing_fields": parsed_rfp.get("missing_fields", []),
            "requirements_count": len(parsed_rfp.get("requirements", [])),
            "structural_elements": parsed_rfp.get("structural_elements", []),
            "outline": {"sections": outline.get("sections", []), "notes": outline.get("notes", "")},
            "questions": clarify.get("questions", []),
            "round": clarify.get("round", 1),
            "is_final_round": clarify.get("is_final_round", False),
        }
        update(100, "Analysis ready.", status="completed", analysis=result_payload)
    except Exception as exc:
        logger.exception(f"[RFP-Analyze] Analysis failed for task {task_id}")
        update(0, f"RFP analysis failed: {exc}", status="failed")


@router.post("/analyze")
async def analyze_rfp(
    background_tasks: BackgroundTasks,
    rfp_files: list[UploadFile] = File(...),
    template_file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
):
    """Upload + parse an RFP and get back an RFP-specific outline and a short
    list of clarifying questions -- BEFORE any document is generated. Poll
    GET /rfp-respond/status/{task_id}; once status == "completed",
    result.analysis contains {rfp_type, summary, outline, questions, round,
    is_final_round}. If questions is non-empty, collect answers and call
    POST /rfp-respond/clarify, then either loop again or proceed straight to
    POST /rfp-respond/upload with analysis_task_id=<this task_id>."""
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

    user_id = str(current_user["id"])
    await update_task_status_async(
        task_id, "rfp_analyze", 0, "processing", "Upload received, starting analysis...", None,
        extra={"userId": user_id},
    )
    background_tasks.add_task(
        _run_analyze_sync, task_id, user_id, rfp_paths_str, str(template_dest) if template_dest else None
    )
    return {"status": "started", "task_id": task_id}


class ClarifyAnswer(BaseModel):
    id: str
    question: Optional[str] = None
    answer: Any = None


class ClarifyRequest(BaseModel):
    task_id: str
    answers: List[ClarifyAnswer] = []


@router.post("/clarify")
async def clarify_rfp(payload: ClarifyRequest, current_user: dict = Depends(get_current_user)):
    """Submit answers to the previous round's questions and get back either
    the next round's questions (if anything is still genuinely unresolved,
    up to 3 rounds total) or an empty list once nothing more is needed."""
    task = await get_task_status_async(payload.task_id)
    if not task:
        raise HTTPException(404, "Unknown task_id")
    user_id = str(current_user["id"])
    if _get_task_user_id(task) != user_id:
        raise HTTPException(403, "Access denied: You do not own this task.")

    task_dir = UPLOAD_DIR / payload.task_id
    parsed_path = task_dir / "parsed_rfp.json"
    if not parsed_path.exists():
        raise HTTPException(400, "No completed analysis found for this task_id. Call /analyze first.")

    parsed_rfp = json.loads(parsed_path.read_text(encoding="utf-8"))

    resolved_path = task_dir / "resolved_answers.json"
    resolved = json.loads(resolved_path.read_text(encoding="utf-8")) if resolved_path.exists() else []
    new_answers = [a.model_dump() for a in payload.answers]
    resolved.extend(new_answers)
    resolved_path.write_text(json.dumps(resolved, default=str), encoding="utf-8")

    prior_result = _load_task_result(task)
    prior_round = int(prior_result.get("round") or 1)
    next_round = prior_round + 1

    company_context = ""
    template_marker = task_dir / "template_path.txt"
    if template_marker.exists():
        try:
            from documents.template_analyzer import analyze_template
            profile = analyze_template(template_marker.read_text(encoding="utf-8").strip())
            company_context = profile.to_company_profile_summary()
        except Exception:
            pass

    from documents.bidforge.clarify import build_clarifying_questions
    clarify = await asyncio.to_thread(
        build_clarifying_questions, parsed_rfp, company_context, resolved, next_round
    )

    updated_result = dict(prior_result)
    updated_result["round"] = clarify.get("round", next_round)
    updated_result["is_final_round"] = clarify.get("is_final_round", True)
    updated_result["questions"] = clarify.get("questions", [])
    await update_task_status_async(
        payload.task_id, "rfp_analyze", 100, "completed", "Clarification round updated.", None,
        extra={"userId": user_id, "analysis": updated_result},
    )

    return {
        "task_id": payload.task_id,
        "questions": clarify.get("questions", []),
        "round": clarify.get("round", next_round),
        "is_final_round": clarify.get("is_final_round", True),
        "resolved_answers_count": len(resolved),
    }


@router.post("/upload")
async def upload_rfp(
    background_tasks: BackgroundTasks,
    rfp_files: list[UploadFile] = File(default=[]),
    template_file: Optional[UploadFile] = File(None),
    wizard_config: Optional[str] = Form(None),
    analysis_task_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """Generates the proposal document. If `analysis_task_id` is supplied
    (the normal path from the UI, after /analyze + optional /clarify
    round(s)), the RFP files, cached parse, RFP-specific outline, and
    resolved clarifying-question answers from that analysis are reused
    automatically -- re-uploading rfp_files is then optional. Without
    analysis_task_id, this behaves as a standalone one-shot call (e.g. the
    CLI/tests), building the outline on the fly with no clarification step.
    """
    if len(rfp_files) > 5:
        raise HTTPException(status_code=400, detail="Cannot upload more than 5 RFP files at once.")

    user_id = str(current_user["id"])
    parsed_rfp_json_path: Optional[str] = None
    reused_rfp_paths: Optional[str] = None
    reused_template_path: Optional[Path] = None
    merged_wizard_config: Dict[str, Any] = {}

    if analysis_task_id:
        analysis_task = await get_task_status_async(analysis_task_id)
        if not analysis_task:
            raise HTTPException(404, "Unknown analysis_task_id.")
        if _get_task_user_id(analysis_task) != user_id:
            raise HTTPException(403, "Access denied: You do not own this analysis task.")

        analysis_dir = UPLOAD_DIR / analysis_task_id
        parsed_path = analysis_dir / "parsed_rfp.json"
        if parsed_path.exists():
            parsed_rfp_json_path = str(parsed_path)

        rfp_paths_marker = analysis_dir / "rfp_paths.txt"
        if rfp_paths_marker.exists():
            reused_rfp_paths = rfp_paths_marker.read_text(encoding="utf-8").strip()

        template_marker = analysis_dir / "template_path.txt"
        if template_marker.exists():
            reused_template_path = Path(template_marker.read_text(encoding="utf-8").strip())

        outline_path = analysis_dir / "outline.json"
        if outline_path.exists():
            try:
                outline = json.loads(outline_path.read_text(encoding="utf-8"))
                merged_wizard_config["sections"] = outline.get("sections", [])
                merged_wizard_config["outline_notes"] = outline.get("notes", "")
            except Exception as exc:
                logger.warning(f"[RFP-Upload] Could not load cached outline for {analysis_task_id}: {exc}")

        resolved_path = analysis_dir / "resolved_answers.json"
        if resolved_path.exists():
            try:
                merged_wizard_config["answers"] = json.loads(resolved_path.read_text(encoding="utf-8"))
            except Exception:
                merged_wizard_config["answers"] = []

    # A caller-supplied wizard_config (e.g. the user edited outline sections
    # in the UI before confirming) takes precedence over what was cached
    # during /analyze, field by field.
    if wizard_config:
        try:
            user_config = json.loads(wizard_config)
            if isinstance(user_config, dict):
                merged_wizard_config.update({k: v for k, v in user_config.items() if v not in (None, [], {})})
        except Exception as exc:
            logger.warning(f"[RFP-Upload] Could not parse caller-supplied wizard_config, ignoring: {exc}")

    task_id = uuid.uuid4().hex[:12]
    task_dir = UPLOAD_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    rfp_dests = []
    for file in rfp_files:
        if file.filename:
            dest = task_dir / _safe_name(file.filename)
            await asyncio.to_thread(_save_upload_file_sync, file, dest)
            rfp_dests.append(str(dest))

    if rfp_dests:
        rfp_paths_str = ",".join(rfp_dests)
        # New files were uploaded at this step instead of reusing the
        # analyzed ones -- the cached parse no longer matches, so don't
        # reuse it (fall back to parsing fresh inside the pipeline).
        if not reused_rfp_paths:
            parsed_rfp_json_path = None
    elif reused_rfp_paths:
        rfp_paths_str = reused_rfp_paths
    else:
        raise HTTPException(400, "At least one valid RFP file must be uploaded, or analysis_task_id must reference a completed analysis.")

    template_dest = reused_template_path
    if template_file is not None and template_file.filename:
        if not template_file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "Template must be a .docx file.")
        template_dest = task_dir / _safe_name(template_file.filename)
        await asyncio.to_thread(_save_upload_file_sync, template_file, template_dest)
    elif template_dest is None:
        from documents.default_template import get_default_template_path
        default_path = get_default_template_path()
        if default_path:
            template_dest = Path(default_path)

    output_name = f"rfp_respond_{task_id}"
    final_wizard_config = json.dumps(merged_wizard_config, default=str) if merged_wizard_config else wizard_config
    await update_task_status_async(
        task_id,
        "rfp_respond",
        0,
        "processing",
        "Upload received, queuing pipeline...",
        None,
        extra={"userId": user_id, "wizardConfig": final_wizard_config, "analysisTaskId": analysis_task_id}
    )

    background_tasks.add_task(
        _run_pipeline_sync, task_id, rfp_paths_str, output_name, template_dest, final_wizard_config, parsed_rfp_json_path
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

    # `result` (a JSON blob) is where update_task_status actually stores
    # filename/analysis/etc -- but existing frontend code reads
    # `taskState.filename` at the TOP level, which this endpoint never
    # populated. Flatten the couple of fields the UI relies on directly so
    # download/analysis wiring works without every caller having to know to
    # dig into `result` themselves.
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
                # in this module ever populates) -- querying extra_data here
                # meant this lookup never matched any row, silently skipping
                # the ownership check below for every download.
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
