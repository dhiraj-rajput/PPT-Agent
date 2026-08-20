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
from typing import Any, Callable, Dict, Optional

from utils.helpers import setup_logger

logger = setup_logger(__name__)


def parse_uploaded_rfp(
    rfp_file_paths: str,
    solicitation_number: str = "",
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Parses one or more manually-uploaded RFP documents (PDF, or .txt/.docx) into the
    same structured shape RFPParser produces for SAM.gov solicitations, so
    the rest of the pipeline (inventory/competitor/summarise/generate) is
    shared code. Supports multiple comma-separated file paths.
    """
    from documents.rfp_response.rfp_parser import RFPParser

    paths = [Path(p.strip()) for p in rfp_file_paths.split(",") if p.strip()]
    if not paths:
        raise FileNotFoundError("No uploaded RFP files specified.")

    first_src = paths[0]
    sol_number = solicitation_number or f"BIDFORGE-{first_src.stem[:40]}"
    parser = RFPParser(sol_number)
    parser.rfp_docs_dir.mkdir(parents=True, exist_ok=True)

    # Clean old files in that folder
    for old_f in list(parser.rfp_docs_dir.iterdir()):
        if old_f.is_file():
            try:
                old_f.unlink()
            except Exception:
                pass

    # Copy all source files to the rfp_docs_dir
    for src in paths:
        if src.exists():
            dest = parser.rfp_docs_dir / src.name
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)

    doc_texts = {}
    
    # 1. Extract PDFs using RFPParser (which handles OCR fallback)
    pdf_texts = parser.extract_text_from_pdfs()
    doc_texts.update(pdf_texts)

    # 2. Extract DOCX and TXT files directly
    for old_f in parser.rfp_docs_dir.iterdir():
        if old_f.suffix.lower() == ".pdf":
            continue
        if old_f.suffix.lower() in (".docx", ".doc"):
            doc_texts[old_f.name] = _extract_docx_text(old_f)
        elif old_f.is_file():
            doc_texts[old_f.name] = old_f.read_text(encoding="utf-8", errors="ignore")

    parsed = parser.parse_requirements(doc_texts, progress_callback=progress_callback)
    parsed["raw_text"] = "\n\n".join(doc_texts.values())
    parsed["source_filename"] = ", ".join(p.name for p in paths)
    logger.info(f"[BidForge:Parse] Parsed {len(doc_texts)} uploaded file(s) via '{parsed.get('parsed_via')}' path.")
    return parsed


def _extract_docx_text(path: Path) -> str:
    try:
        import docx  # python-docx
        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs)
    except Exception as exc:
        logger.warning(f"[BidForge:Parse] Failed to extract text from docx {path.name}: {exc}")
        return ""
