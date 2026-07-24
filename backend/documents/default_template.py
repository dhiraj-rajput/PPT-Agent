"""
documents/default_template.py
-------------------------------
Persists a single org-wide "default" .docx template that every document
generation entry point (RFP Auto-Respond, Proposal Builder, RFP upload) falls
back to when the user doesn't attach a one-off template to that specific
request. Set once from any of those pages, used everywhere.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORE_DIR = PROJECT_ROOT / "private" / "default_template"
TEMPLATE_PATH = STORE_DIR / "template.docx"
META_PATH = STORE_DIR / "meta.json"


def set_default_template(source_path: str, original_filename: str, uploaded_by: Optional[str] = None) -> dict:
    """Copy the uploaded file into persistent storage as the new default
    template, replacing any previous one."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, TEMPLATE_PATH)

    meta = {
        "original_filename": original_filename,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": uploaded_by,
    }
    META_PATH.write_text(json.dumps(meta), encoding="utf-8")
    logger.info(f"[DefaultTemplate] Set default template from '{original_filename}'.")
    return meta


def get_default_template_path() -> Optional[str]:
    """Return the path to the persisted default template, or None if none
    has been uploaded yet."""
    if TEMPLATE_PATH.exists():
        return str(TEMPLATE_PATH)
    return None


def get_default_template_meta() -> Optional[dict]:
    if not TEMPLATE_PATH.exists():
        return None
    meta = {}
    if META_PATH.exists():
        try:
            meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta["has_template"] = True
    return meta


def clear_default_template() -> None:
    for p in (TEMPLATE_PATH, META_PATH):
        try:
            if p.exists():
                p.unlink()
        except Exception as e:
            logger.warning(f"[DefaultTemplate] Could not remove {p}: {e}")
    logger.info("[DefaultTemplate] Default template cleared.")
