"""
app/routes/templates.py
-------------------------
Org-wide default .docx template management, shared by the Proposal Builder,
RFP Auto-Respond, and RFP upload pages.

Endpoints:
  POST   /api/templates/default        — upload/replace the default .docx template
  GET    /api/templates/default        — metadata about the current default template
  GET    /api/templates/default/view   — view the default template inline (no download)
  DELETE /api/templates/default        — clear the default template
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.auth import get_current_user
from documents.default_template import (
    set_default_template,
    get_default_template_path,
    get_default_template_meta,
    clear_default_template,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/templates", tags=["templates"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/default")
async def upload_default_template(
    template_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a .docx template and set it as the org-wide default used by
    Proposal Builder, RFP Auto-Respond, and RFP upload whenever a request
    doesn't attach its own one-off template."""
    if not template_file.filename or not template_file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Default template must be a .docx file.")

    # UploadFile is not an async iterator on all Starlette versions — use .read()
    try:
        content = await template_file.read()
    except Exception as exc:
        logger.error(f"[templates] Failed to read upload: {exc}")
        raise HTTPException(400, f"Could not read uploaded file: {exc}") from exc

    if not content:
        raise HTTPException(400, "Uploaded template file is empty.")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "Template file exceeds the 10MB size limit.")

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        meta = set_default_template(
            tmp_path,
            template_file.filename,
            uploaded_by=str(current_user.get("id") or current_user.get("sub") or ""),
        )
    except Exception as exc:
        logger.exception("[templates] set_default_template failed")
        raise HTTPException(500, f"Failed to save default template: {exc}") from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"status": "ok", "has_template": True, **meta}


@router.get("/default")
async def get_default_template(current_user: dict = Depends(get_current_user)):
    meta = get_default_template_meta()
    if not meta:
        return {"has_template": False}
    return meta


@router.get("/default/view")
async def view_default_template(current_user: dict = Depends(get_current_user)):
    """Serve the default template inline so it can be previewed in the
    browser without forcing a download."""
    path = get_default_template_path()
    if not path:
        raise HTTPException(404, "No default template has been uploaded yet.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats.wordprocessingml.document",
        filename=Path(path).name,
    )


@router.delete("/default")
async def delete_default_template(current_user: dict = Depends(get_current_user)):
    clear_default_template()
    return {"status": "ok", "has_template": False}
