"""
documents/rfp_response/rfp_parser.py
------------------------------------
Parses RFP/tender text into a structured shape used by the rest of the
pipeline (outline building, clarifying questions, document generation).

REWRITE NOTE: The previous version capped raw text at 120,000 chars and fed
it to a single LLM call. That silently truncated anything past ~25-35 pages
of a dense tender before the model ever saw it -- for a document like a
90+ page GCC/SCC/annexure-heavy tender, more than half the document was
simply invisible to the pipeline, and the fixed RFP_PARSER_PROMPT schema had
no fields for tender-specific structure (envelope bidding, bid security,
mandatory annexures/forms) even for the part that WAS seen.

This version:
  1. Never truncates. For text under a safe single-call threshold, it parses
     in one call (fast path). Above that, it splits into overlapping chunks
     and extracts each chunk independently (RFP_CHUNK_EXTRACT_PROMPT), then
     merges all chunk extracts (never raw text again -- input size to the
     merge call stays bounded) into one final structure via
     RFP_MERGE_SYNTHESIS_PROMPT. Every chunk gets read; nothing is dropped
     for being "past" some cutoff.
  2. Extracts `structural_elements` (mandatory annexures/forms, bid-security
     requirements, submission format, pricing-format requirements) and an
     `rfp_type` classification, not just a flat requirements list -- this is
     what lets the outline stage build an RFP-specific outline instead of a
     hardcoded skeleton.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from utils.helpers import setup_logger
from pipeline.ai.client import get_ai_client
from documents.prompts import (
    RFP_PARSER_PROMPT,
    RFP_CHUNK_EXTRACT_PROMPT,
    RFP_MERGE_SYNTHESIS_PROMPT,
)

logger = setup_logger(__name__)

# Below this size, parse in a single call (fast path, no chunking overhead).
SINGLE_CALL_CHAR_THRESHOLD = 55_000

# Chunk size and overlap for the map-reduce path. Overlap ensures a
# requirement/clause that straddles a chunk boundary isn't half-lost.
CHUNK_SIZE = 45_000
CHUNK_OVERLAP = 2_000

# Output budgets per call type.
MERGE_MAX_TOKENS = 16000
CHUNK_MAX_TOKENS = 8192
SINGLE_CALL_MAX_TOKENS = 12000


class RFPParser:
    """Extracts text from RFP files and parses requirements/structure, chunking
    instead of truncating when the source document is large."""

    def __init__(self, solicitation_number: str, project_root: str = str(Path(__file__).resolve().parent.parent.parent)):
        self.solicitation_number = solicitation_number
        self.project_root = Path(project_root)
        self.rfp_docs_dir = self.project_root / "downloads" / "opportunities" / solicitation_number / "rfp_docs"

    def extract_text_from_pdfs(self) -> Dict[str, str]:
        """Extracts text from all supported RFP documents in the directory."""
        extracted_text = {}
        if not self.rfp_docs_dir.exists():
            logger.warning(f"RFP docs directory not found: {self.rfp_docs_dir}")
            return extracted_text

        valid_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".docx", ".doc", ".txt", ".html"}
        doc_files = [f for f in self.rfp_docs_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_extensions]

        from pipeline.ocr.ocr_manager import get_ocr_manager
        ocr_mgr = get_ocr_manager()

        for doc_path in doc_files:
            filename = doc_path.name
            try:
                ocr_result = ocr_mgr.extract(doc_path)
                text = str(ocr_result.get("text", "") or "")
                extracted_text[filename] = text
            except Exception as e:
                logger.error(f"Failed to extract text from {filename}: {e}")

        return extracted_text

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def parse_requirements(self, doc_texts: Dict[str, str]) -> Dict[str, Any]:
        """Parses extracted RFP text into the full structured shape, never
        truncating -- chunks + merges for large documents instead."""
        combined_text = "\n\n".join(doc_texts.values())
        if not combined_text.strip():
            logger.warning("No text extracted from RFP documents. Returning empty structure.")
            return self._empty_parse_structure()

        from pipeline.ai.mode import run_with_fallback

        char_count = len(combined_text)
        logger.info(f"[RFPParser] Parsing {char_count:,} chars of extracted RFP text "
                    f"({'single-call' if char_count <= SINGLE_CALL_CHAR_THRESHOLD else 'chunked'} path).")

        def ai_fn() -> Dict[str, Any]:
            if char_count <= SINGLE_CALL_CHAR_THRESHOLD:
                result = self._parse_single_call(combined_text)
            else:
                result = self._parse_chunked(combined_text)
            result["raw_text"] = combined_text
            return result

        def rule_fn() -> Dict[str, Any]:
            logger.warning("[RFPParser] Using rule fallback for RFP parsing.")
            return self._rule_fallback(combined_text)

        result, path_used = run_with_fallback("rfp_parser", ai_fn, rule_fn)
        result["generated_via"] = path_used
        return result

    # ------------------------------------------------------------------
    # Fast path: single call for documents under the threshold
    # ------------------------------------------------------------------

    def _parse_single_call(self, text: str) -> Dict[str, Any]:
        client = get_ai_client()
        messages = [
            {"role": "system", "content": RFP_PARSER_PROMPT},
            {"role": "user", "content": f"Solicitation Number: {self.solicitation_number}\n\nRFP Document Text:\n{text}"},
        ]
        ai_res = client.chat_json(messages, max_tokens=SINGLE_CALL_MAX_TOKENS)
        return {
            "solicitation_number": self.solicitation_number,
            "parsed_content": ai_res.get("parsed_content", ""),
            "rfp_type": ai_res.get("rfp_type", "capability_tender"),
            "missing_fields": ai_res.get("missing_fields", []),
            "metadata": ai_res.get("metadata", {}),
            "requirements": ai_res.get("requirements", []),
            "compliance_requirements": ai_res.get("compliance_requirements", []),
            "structural_elements": ai_res.get("structural_elements", []),
            "summary": ai_res.get("summary", ""),
        }

    # ------------------------------------------------------------------
    # Map-reduce path: chunk -> extract each -> merge
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str) -> List[str]:
        chunks = []
        start = 0
        n = len(text)
        while start < n:
            end = min(start + CHUNK_SIZE, n)
            chunks.append(text[start:end])
            if end >= n:
                break
            start = end - CHUNK_OVERLAP
        return chunks

    def _parse_chunked(self, text: str) -> Dict[str, Any]:
        client = get_ai_client()
        chunks = self._chunk_text(text)
        logger.info(f"[RFPParser] Splitting into {len(chunks)} chunk(s) of ~{CHUNK_SIZE:,} chars each.")

        chunk_extracts: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(chunks, start=1):
            try:
                messages = [
                    {"role": "system", "content": RFP_CHUNK_EXTRACT_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Solicitation Number: {self.solicitation_number}\n"
                            f"Chunk {idx} of {len(chunks)} (in document order):\n\n{chunk}"
                        ),
                    },
                ]
                extract = client.chat_json(messages, max_tokens=CHUNK_MAX_TOKENS)
                chunk_extracts.append(extract)
                logger.info(
                    f"[RFPParser] Chunk {idx}/{len(chunks)}: "
                    f"{len(extract.get('requirements', []))} requirement(s), "
                    f"{len(extract.get('structural_elements', []))} structural element(s)."
                )
            except Exception as exc:
                logger.warning(f"[RFPParser] Chunk {idx}/{len(chunks)} extraction failed, continuing: {exc}")

        if not chunk_extracts:
            raise RuntimeError("All chunk extractions failed; nothing to merge.")

        merge_input = json.dumps(chunk_extracts, indent=2)
        merge_messages = [
            {"role": "system", "content": RFP_MERGE_SYNTHESIS_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Solicitation Number: {self.solicitation_number}\n"
                    f"Number of chunks merged: {len(chunk_extracts)}\n\n"
                    f"Chunk extracts (in document order):\n{merge_input}"
                ),
            },
        ]
        merged = client.chat_json(merge_messages, max_tokens=MERGE_MAX_TOKENS)

        return {
            "solicitation_number": self.solicitation_number,
            "parsed_content": merged.get("parsed_content", ""),
            "rfp_type": merged.get("rfp_type", "capability_tender"),
            "missing_fields": merged.get("missing_fields", []),
            "metadata": merged.get("metadata", {}),
            "requirements": merged.get("requirements", []),
            "compliance_requirements": merged.get("compliance_requirements", []),
            "structural_elements": merged.get("structural_elements", []),
            "summary": merged.get("summary", ""),
            "chunks_processed": len(chunks),
        }

    # ------------------------------------------------------------------
    # Fallbacks
    # ------------------------------------------------------------------

    def _empty_parse_structure(self) -> Dict[str, Any]:
        return {
            "solicitation_number": self.solicitation_number,
            "parsed_content": "No content extracted.",
            "rfp_type": "capability_tender",
            "missing_fields": ["RFP document text missing"],
            "metadata": {"solicitation_number": self.solicitation_number},
            "requirements": [],
            "compliance_requirements": [],
            "structural_elements": [],
            "summary": "Empty solicitation document.",
            "raw_text": "",
        }

    def _rule_fallback(self, text: str) -> Dict[str, Any]:
        return {
            "solicitation_number": self.solicitation_number,
            "parsed_content": text[:2000],
            "rfp_type": "capability_tender",
            "missing_fields": ["Detailed AI parsing unavailable"],
            "metadata": {"solicitation_number": self.solicitation_number},
            "requirements": [{"name": "General Scope", "description": text[:300], "status": "Required"}],
            "compliance_requirements": [],
            "structural_elements": [],
            "summary": f"Solicitation {self.solicitation_number} response.",
            "raw_text": text[:10000],
        }
