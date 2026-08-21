"""
app/routes/rfp_respond.py
--------------------------
RFP Auto-Respond — upload an RFP document, get back a fully-written proposal using MySQL.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
import re
import subprocess
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from models.sql_models import TaskStatus as SQL_TaskStatus
from sqlalchemy import select
from utils.db_client import (
    _mysql_available,
    get_db_session,
    get_task_status_async,
    get_task_status_db,
    update_task_status,
    update_task_status_async,
)

from app.core.auth import get_current_user

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
        from datetime import datetime

        from models.sql_models import Report as SQL_Report
        from sqlalchemy import insert, select
        from sqlalchemy import update as sql_update
        from utils.db_client import get_sync_db_session

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
    template_path: Path | None,
    wizard_config: str | None = None,
) -> None:
    """Run bidforge_cli.py as a subprocess and update progress in MySQL."""

    from utils.helpers import get_python_executable
    python_bin = get_python_executable()

    def update(progress: int, message: str, status: str = "processing", filename: str | None = None):
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
# Company context helper (own profile for clarify / outline)
# ---------------------------------------------------------------------------

def _load_company_context() -> str:
    try:
        from utils.db_client import get_collection
        col = get_collection("own_company_profile")
        profile = col.find_one({}) or {}
        bits = []
        for key in (
            "name", "company_name", "legal_name", "uei", "cage_code",
            "primary_naics", "primary_naics_desc", "capabilities",
            "certifications", "size", "description", "city", "state",
            "email", "phone",
        ):
            val = profile.get(key)
            if val:
                if isinstance(val, list):
                    val = ", ".join(str(v) for v in val[:15])
                bits.append(f"{key}: {str(val)[:500]}")
        return " | ".join(bits) if bits else ""
    except Exception as exc:
        logger.warning(f"[rfp-respond] Could not load company profile: {exc}")
        return ""


def _run_analyze_sync(task_id: str, rfp_paths: str, solicitation: str = "") -> None:
    """Parse RFP → outline → clarifying questions; store results on the task."""
    def update(progress: int, message: str, status: str = "processing", extra: dict | None = None):
        update_task_status(task_id, "rfp_respond_analyze", progress, status, message, None, extra=extra)

    try:
        update(5, "Parsing uploaded RFP (section-aware, no truncation)...")
        from documents.bidforge.clarify import build_clarifying_questions
        from documents.bidforge.outline import build_outline
        from documents.bidforge.parse import parse_uploaded_rfp

        def _parse_progress(pct: int, msg: str) -> None:
            # Keep progress in the parse band (5–39) so the wizard stage UI
            # stays on "Parse RFP" until this phase finishes.
            update(max(5, min(39, int(pct))), msg)

        parsed = parse_uploaded_rfp(rfp_paths, solicitation, progress_callback=_parse_progress)
        update(40, f"Parsed RFP type={parsed.get('rfp_type')} — "
                   f"{len(parsed.get('requirements') or [])} requirements, "
                   f"{len(parsed.get('structural_elements') or [])} structural elements "
                   f"({parsed.get('chunks_processed', 1)} chunk(s)).")

        # Cache parsed JSON next to uploads so generation can skip re-parse
        task_dir = UPLOAD_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        parsed_path = task_dir / "parsed_rfp.json"
        parsed_path.write_text(json.dumps(parsed, ensure_ascii=False, default=str), encoding="utf-8")

        company_ctx = _load_company_context()
        template_sections: list = []
        try:
            from documents.default_template import get_default_template_path
            from documents.template_analyzer import analyze_template
            tpl = get_default_template_path()
            if tpl:
                profile = analyze_template(tpl)
                template_sections = list(profile.sections or [])
                # Enrich company context with template summary (IDs, tables)
                extra = profile.to_company_profile_summary()
                if extra:
                    company_ctx = (company_ctx + "\n\n" + extra).strip()
        except Exception as tpl_err:
            logger.debug(f"[rfp-respond] Template section scan skipped: {tpl_err}")

        update(60, "Building RFP-specific outline (deduping template sections)...")
        outline = build_outline(
            parsed,
            company_context=company_ctx,
            template_sections_present=template_sections,
        )

        update(80, "Generating clarifying questions from gaps & mandatory forms...")
        clarify = build_clarifying_questions(parsed, company_context=company_ctx, round_number=1)

        analysis_blob = {
            "parsed_rfp_path": str(parsed_path),
            "rfp_type": parsed.get("rfp_type"),
            "summary": parsed.get("summary"),
            "metadata": parsed.get("metadata") or {},
            "requirements_count": len(parsed.get("requirements") or []),
            "structural_elements_count": len(parsed.get("structural_elements") or []),
            "compliance_count": len(parsed.get("compliance_requirements") or []),
            "outline": outline,
            "questions": clarify.get("questions") or [],
            "round": clarify.get("round", 1),
            "is_final_round": clarify.get("is_final_round", False),
            "rfp_paths": rfp_paths,
        }
        # Frontend reads state.result.analysis OR state.analysis
        existing = get_task_status_db(task_id) or {}
        prev = existing.get("result") if isinstance(existing.get("result"), dict) else {}
        if isinstance(existing.get("result"), str):
            try:
                prev = json.loads(existing["result"])
            except Exception:
                prev = {}
        merged = {**(prev or {}), **analysis_blob, "analysis": analysis_blob}
        update(100, "Analysis complete — ready for clarifying questions.", "completed", extra=merged)
    except Exception as exc:
        logger.exception(f"[rfp-respond] analyze failed for {task_id}")
        update(0, f"Analysis failed: {exc}", "failed")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _save_upload_file_sync(file: UploadFile, dest_path: Path, max_bytes: int = 25 * 1024 * 1024) -> None:
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


@router.post("/analyze")
async def analyze_rfp(
    background_tasks: BackgroundTasks,
    rfp_files: list[UploadFile] = File(...),
    template_file: UploadFile | None = File(None),
    solicitation_number: str | None = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Pre-generation analysis: upload RFP → parse (section-aware, no truncation)
    → RFP-specific outline → clarifying questions derived from THIS document.
    Frontend RfpAnalysisWizard polls /status until completed, then shows questions.
    """
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

    if template_file is not None and template_file.filename:
        if not template_file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "Template must be a .docx file.")
        tpl_dest = task_dir / _safe_name(template_file.filename)
        await asyncio.to_thread(_save_upload_file_sync, template_file, tpl_dest)

    user_id = str(current_user["id"])
    await update_task_status_async(
        task_id,
        "rfp_respond_analyze",
        0,
        "processing",
        "Upload received — starting full RFP analysis...",
        None,
        extra={
            "userId": user_id,
            "rfp_paths": rfp_paths_str,
            "solicitation_number": solicitation_number or "",
        },
    )

    background_tasks.add_task(
        _run_analyze_sync, task_id, rfp_paths_str, solicitation_number or ""
    )
    return {"status": "started", "task_id": task_id}


@router.post("/clarify")
async def clarify_rfp(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Submit answers to clarifying questions. If more questions remain, return them
    (next round). If nothing critical remains, start document generation using
    the cached parsed RFP so the document is not re-parsed.
    """
    task_id = str(payload.get("task_id") or "")
    answers = payload.get("answers") or []
    if not task_id:
        raise HTTPException(400, "task_id is required")

    task = await get_task_status_async(task_id)
    if not task:
        raise HTTPException(404, "Unknown task_id")
    user_id = str(current_user["id"])
    if _get_task_user_id(task) and _get_task_user_id(task) != user_id:
        raise HTTPException(403, "Access denied")

    result = _load_task_result(task)
    parsed_path = result.get("parsed_rfp_path")
    rfp_paths = result.get("rfp_paths") or ""
    if not parsed_path or not Path(parsed_path).exists():
        raise HTTPException(400, "No cached RFP analysis for this task — re-run analyze.")

    parsed = json.loads(Path(parsed_path).read_text(encoding="utf-8"))
    company_ctx = _load_company_context()
    prev_answers = result.get("answered") or []
    if not isinstance(prev_answers, list):
        prev_answers = []
    combined_answers = list(prev_answers) + list(answers)
    round_number = int(result.get("round") or 1) + 1

    from documents.bidforge.clarify import MAX_ROUNDS, build_clarifying_questions
    clarify = build_clarifying_questions(
        parsed,
        company_context=company_ctx,
        answered=combined_answers,
        round_number=min(round_number, MAX_ROUNDS),
    )
    questions = clarify.get("questions") or []

    result["answered"] = combined_answers
    result["round"] = clarify.get("round", round_number)
    result["is_final_round"] = clarify.get("is_final_round", False)
    result["questions"] = questions

    # Always surface remaining questions to the UI — including the final round.
    # Previously is_final_round=True discarded Round-3 questions and jumped
    # straight to generation, so users never saw the last batch.
    if questions:
        await update_task_status_async(
            task_id,
            "rfp_respond_analyze",
            100,
            "completed",
            f"Clarification round {result['round']} — additional questions.",
            None,
            extra=result,
        )
        return {
            "status": "need_more",
            "task_id": task_id,
            "questions": questions,
            "round": result["round"],
            "is_final_round": bool(clarify.get("is_final_round")),
            "outline": result.get("outline"),
        }

    # Ready to generate — attach answers into wizard_config and start pipeline
    wizard_config = json.dumps({
        "answers": combined_answers,
        "outline": result.get("outline"),
        "clarifying_answers": combined_answers,
    })
    output_name = f"rfp_respond_{task_id}"
    template_dest = None
    task_dir = UPLOAD_DIR / task_id
    if task_dir.exists():
        for f in task_dir.iterdir():
            if f.suffix.lower() == ".docx" and f.name != "parsed_rfp.json":
                template_dest = f
                break
    if template_dest is None:
        try:
            from documents.default_template import get_default_template_path
            default_path = get_default_template_path()
            if default_path:
                template_dest = Path(default_path)
        except Exception:
            pass

    result["wizardConfig"] = wizard_config
    await update_task_status_async(
        task_id,
        "rfp_respond",
        5,
        "processing",
        "Clarifications complete — starting document generation...",
        None,
        extra=result,
    )

    # Pass cached parse path via env-style: extend _run_pipeline to accept it
    background_tasks.add_task(
        _run_pipeline_with_cache,
        task_id,
        rfp_paths,
        output_name,
        template_dest,
        wizard_config,
        parsed_path,
    )
    return {
        "status": "generating",
        "task_id": task_id,
        "questions": [],
        "round": result["round"],
        "is_final_round": True,
        "outline": result.get("outline"),
    }


def _run_pipeline_with_cache(
    task_id: str,
    rfp_paths: str,
    output_name: str,
    template_path: Path | None,
    wizard_config: str | None = None,
    parsed_rfp_json_path: str | None = None,
) -> None:
    """Like _run_pipeline_sync but passes --parsed-rfp-json to skip re-parse."""
    from utils.helpers import get_python_executable
    python_bin = get_python_executable()

    def update(progress: int, message: str, status: str = "processing", filename: str | None = None):
        update_task_status(task_id, "rfp_respond", progress, status, message, filename)

    cmd = [
        python_bin, "-u",
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

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    try:
        from utils.helpers import SUBPROCESS_SEMAPHORE
        update(4, "Waiting in queue for document-generation resources...")
        with SUBPROCESS_SEMAPHORE:
            update(5, "Starting RFP Auto-Respond pipeline (using cached parse)...")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
                text=True,
                encoding="utf-8",
                errors="ignore",
                env=env,
                bufsize=1,
            )
            final_path = None
            if proc.stdout:
                for line in proc.stdout:
                    safe_line = line.strip()
                    print(f"[RFP-Respond] {safe_line}")
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


@router.post("/upload")
async def upload_rfp(
    background_tasks: BackgroundTasks,
    rfp_files: list[UploadFile] | None = File(None),
    template_file: UploadFile | None = File(None),
    wizard_config: str | None = Form(None),
    analysis_task_id: str | None = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Start proposal generation.

    Two modes:
      1. Fresh upload — client sends one or more RFP files (and optional template).
      2. Post-analysis — client sends analysis_task_id only; we reuse the already
         parsed RFP + outline/answers cached by /analyze + /clarify so the file
         is not re-uploaded and not re-parsed.
    """
    user_id = str(current_user["id"])
    rfp_files = rfp_files or []

    # ------------------------------------------------------------------
    # Mode 2: continue from a completed analysis task (no new files)
    # ------------------------------------------------------------------
    if analysis_task_id and not any(f.filename for f in rfp_files):
        analysis_task = await get_task_status_async(analysis_task_id)
        if not analysis_task:
            raise HTTPException(404, "Unknown analysis_task_id — re-run Analyze first.")
        owner = _get_task_user_id(analysis_task)
        if owner and owner != user_id:
            raise HTTPException(403, "Access denied: You do not own this analysis task.")

        result = _load_task_result(analysis_task)
        rfp_paths_str = result.get("rfp_paths") or ""
        parsed_path = result.get("parsed_rfp_path")
        cached_wizard = result.get("wizardConfig") or wizard_config

        if not rfp_paths_str and not parsed_path:
            raise HTTPException(
                400,
                "Analysis task has no cached RFP paths — re-upload the RFP and run Analyze again.",
            )

        # Prefer template already stored next to the analysis uploads
        template_dest = None
        analysis_dir = UPLOAD_DIR / analysis_task_id
        if analysis_dir.exists():
            for f in analysis_dir.iterdir():
                if f.suffix.lower() == ".docx" and f.name != "parsed_rfp.json":
                    template_dest = f
                    break
        if template_dest is None:
            try:
                from documents.default_template import get_default_template_path
                default_path = get_default_template_path()
                if default_path:
                    template_dest = Path(default_path)
            except Exception:
                pass

        # Keep the same task_id so the UI can keep polling /status/{id}
        task_id = analysis_task_id
        output_name = f"rfp_respond_{task_id}"
        await update_task_status_async(
            task_id,
            "rfp_respond",
            5,
            "processing",
            "Starting document generation from cached analysis...",
            None,
            extra={
                "userId": user_id,
                "wizardConfig": cached_wizard,
                "rfp_paths": rfp_paths_str,
                "parsed_rfp_path": parsed_path,
            },
        )
        background_tasks.add_task(
            _run_pipeline_with_cache,
            task_id,
            rfp_paths_str or "cached",
            output_name,
            template_dest,
            cached_wizard,
            parsed_path,
        )
        return {"status": "started", "task_id": task_id}

    # ------------------------------------------------------------------
    # Mode 1: fresh multi-file upload
    # ------------------------------------------------------------------
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
        raise HTTPException(
            400,
            "At least one valid RFP file must be uploaded (or provide analysis_task_id).",
        )

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
    await update_task_status_async(
        task_id,
        "rfp_respond",
        0,
        "processing",
        "Upload received, queuing pipeline...",
        None,
        extra={"userId": user_id, "wizardConfig": wizard_config, "rfp_paths": rfp_paths_str},
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

    # Flatten result so frontend can read filename, questions, outline at top level.
    result_data = _load_task_result(task)
    task["filename"] = result_data.get("filename")
    task["result"] = result_data
    # Nested analysis object (preferred by RfpAnalysisWizard) + top-level aliases
    analysis = result_data.get("analysis") or {
        k: result_data[k]
        for k in (
            "questions", "outline", "round", "is_final_round", "summary",
            "rfp_type", "metadata", "requirements_count", "structural_elements_count",
            "compliance_count", "parsed_rfp_path",
        )
        if k in result_data
    }
    if analysis:
        task["analysis"] = analysis
        if "analysis" not in result_data:
            task["result"] = {**result_data, "analysis": analysis}
    for key in (
        "questions", "outline", "round", "is_final_round", "summary",
        "rfp_type", "metadata", "requirements_count", "structural_elements_count",
        "compliance_count", "parsed_rfp_path",
    ):
        if key in result_data and key not in task:
            task[key] = result_data[key]
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
