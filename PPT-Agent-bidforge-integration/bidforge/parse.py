"""
bidforge/parse.py
------------------
Stage 1 of the BidForge pipeline: parse a manually-uploaded RFP file into
structured requirements + a plain-language summary. Reuses utils/rfp_parser.py
(which already has AI comprehension + OCR + rule-based fallback, all governed
by the global AI_MODE toggle) instead of re-implementing PDF parsing here.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

from utils.helpers import setup_logger

logger = setup_logger(__name__)


def parse_uploaded_rfp(rfp_file_path: str, solicitation_number: str = "") -> Dict[str, Any]:
    """
    Parses a manually-uploaded RFP document (PDF, or .txt/.docx) into the
    same structured shape RFPParser produces for SAM.gov solicitations, so
    the rest of the pipeline (inventory/competitor/summarise/generate) is
    shared code.
    """
    from utils.rfp_parser import RFPParser

    src = Path(rfp_file_path)
    if not src.exists():
        raise FileNotFoundError(f"Uploaded RFP file not found: {rfp_file_path}")

    sol_number = solicitation_number or f"BIDFORGE-{src.stem[:40]}"
    parser = RFPParser(sol_number)
    parser.rfp_docs_dir.mkdir(parents=True, exist_ok=True)

    dest = parser.rfp_docs_dir / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)

    if src.suffix.lower() == ".pdf":
        doc_texts = parser.extract_text_from_pdfs()
    elif src.suffix.lower() in (".docx", ".doc"):
        doc_texts = {src.name: _extract_docx_text(dest)}
    else:
        # Plain text / markdown / pasted email body
        doc_texts = {src.name: dest.read_text(encoding="utf-8", errors="ignore")}

    parsed = parser.parse_requirements(doc_texts)
    parsed["raw_text"] = "\n\n".join(doc_texts.values())
    parsed["source_filename"] = src.name
    logger.info(f"[BidForge:Parse] Parsed '{src.name}' via '{parsed.get('parsed_via')}' path.")
    return parsed


def _extract_docx_text(path: Path) -> str:
    try:
        import docx  # python-docx
        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs)
    except Exception as exc:
        logger.warning(f"[BidForge:Parse] Failed to extract text from docx {path.name}: {exc}")
        return ""
