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

    content = await template_file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "Template file exceeds the 10MB size limit.")

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        meta = set_default_template(tmp_path, template_file.filename, uploaded_by=str(current_user["_id"]))
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"status": "ok", **meta}


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
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.delete("/default")
async def delete_default_template(current_user: dict = Depends(get_current_user)):
    clear_default_template()
    return {"status": "ok", "has_template": False}
