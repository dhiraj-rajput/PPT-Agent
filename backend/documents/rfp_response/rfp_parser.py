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
from typing import Any, Callable, Dict, List, Optional

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

# Chunk size and overlap for the map-reduce path. Prefer section-aware
# splits first (SECTION-N, ANNEXURE-N, etc.) so Bid Evaluation Criteria,
# Scope of Work, and Price Schedule stay intact — fixed-size only as fallback.
CHUNK_SIZE = 45_000
CHUNK_OVERLAP = 2_000
# Soft target for section-aware chunks; large sections may exceed this and
# will be sub-split with overlap so nothing is dropped.
SECTION_TARGET_SIZE = 40_000

# Output budgets per call type.
MERGE_MAX_TOKENS = 16000
CHUNK_MAX_TOKENS = 8192
SINGLE_CALL_MAX_TOKENS = 12000

# Structural markers common in Indian / international multi-section tenders.
# Order matters: longer/more-specific patterns first when matching.
_SECTION_HEADER_RE = None  # compiled lazily in _get_section_header_re()


class RFPParser:
    # Optional progress_callback set by parse_requirements(...)
    _progress_cb: Optional[Callable[[int, str], None]] = None
    """Extracts text from RFP files and parses requirements/structure, chunking
    instead of truncating when the source document is large."""

    def __init__(self, solicitation_number: str, project_root: str = str(Path(__file__).resolve().parent.parent.parent)):
        self.solicitation_number = solicitation_number
        self.project_root = Path(project_root)
        self.rfp_docs_dir = self.project_root / "downloads" / "opportunities" / solicitation_number / "rfp_docs"
        self._progress_cb = None

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

    def parse_requirements(
        self,
        doc_texts: Dict[str, str],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        """Parses extracted RFP text into the full structured shape, never
        truncating -- chunks + merges for large documents instead.

        progress_callback(progress_0_to_100, message) is optional and used by
        /rfp-respond/analyze so the UI can show "Chunk 12/40" instead of
        sitting at a frozen 5%.
        """
        self._progress_cb = progress_callback
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
                if self._progress_cb:
                    self._progress_cb(12, "Parsing RFP in a single pass…")
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

    @staticmethod
    def _get_section_header_re():
        """Compile once: SECTION-N, ANNEXURE-N, Part N, Schedule, Volume, etc.

        Do NOT embed inline flags like (?m)/(?i) inside alternatives — Python
        raises 'global flags not at the start of the expression' when those
        appear mid-pattern after joining with '|'. Use re.M|re.I on compile.
        """
        global _SECTION_HEADER_RE
        if _SECTION_HEADER_RE is not None:
            return _SECTION_HEADER_RE
        import re
        patterns = [
            r"^[\s]*SECTION[\s\-–—:]*\d+[A-Za-z]?",
            r"^[\s]*ANNEXURE[\s\-–—:]*\d+[A-Za-z]?",
            r"^[\s]*ANNEX[\s\-–—:]*\d+[A-Za-z]?",
            r"^[\s]*SCHEDULE[\s\-–—:]*[A-Z0-9]+",
            r"^[\s]*APPENDIX[\s\-–—:]*[A-Z0-9]+",
            r"^[\s]*VOLUME[\s\-–—:]*[IVX0-9]+",
            r"^[\s]*PART[\s\-–—:]*[IVX0-9]+",
            r"^[\s]*CHAPTER[\s\-–—:]*\d+",
            r"^[\s]*Article[\s\-–—:]*\d+",
            r"^[\s]*INVITATION TO BID",
            r"^[\s]*INSTRUCTIONS TO BIDDERS",
            r"^[\s]*SCOPE OF WORK",
            r"^[\s]*BID EVALUATION CRITERIA",
            r"^[\s]*PRICE SCHEDULE",
            r"^[\s]*GENERAL CONDITIONS OF CONTRACT",
            r"^[\s]*SPECIAL CONDITIONS OF CONTRACT",
            r"^[\s]*RESPONSIBILITY MATRIX",
        ]
        # Non-capturing groups avoid "too many groups" and flag-in-middle issues
        combined = "(?:" + ")|(?:".join(patterns) + ")"
        _SECTION_HEADER_RE = re.compile(combined, re.IGNORECASE | re.MULTILINE)
        return _SECTION_HEADER_RE

    def _chunk_text(self, text: str) -> List[str]:
        """
        Prefer section-aware splits so multi-section tenders (ITB, SOW, BEC,
        GCC, annexures, price schedules) stay coherent for the LLM. Fall back
        to fixed-size overlapping windows only when no headers are found or a
        single section exceeds the target size.
        """
        if not text:
            return []

        header_re = self._get_section_header_re()
        matches = list(header_re.finditer(text))

        if len(matches) >= 2:
            # Build segments from header positions (include preamble before first header)
            boundaries = [0] + [m.start() for m in matches] + [len(text)]
            segments: List[str] = []
            for i in range(len(boundaries) - 1):
                seg = text[boundaries[i]:boundaries[i + 1]].strip()
                if seg:
                    segments.append(seg)

            # Pack consecutive short sections together so we don't fire one LLM
            # call per 1–2 page annexure header (was producing 60–70 chunks and
            # making the UI look stuck for 10+ minutes).
            packed: List[str] = []
            buf = ""
            min_pack = max(8_000, SECTION_TARGET_SIZE // 4)
            for seg in segments:
                if not buf:
                    buf = seg
                elif len(buf) + len(seg) + 2 <= SECTION_TARGET_SIZE:
                    buf = buf + "\n\n" + seg
                else:
                    # Prefer not to leave a tiny leftover buffer
                    if len(buf) < min_pack and packed:
                        packed[-1] = packed[-1] + "\n\n" + buf
                        buf = seg
                    else:
                        packed.append(buf)
                        buf = seg
            if buf:
                if packed and len(buf) < min_pack:
                    packed[-1] = packed[-1] + "\n\n" + buf
                else:
                    packed.append(buf)
            segments = packed

            # Sub-split any segment that is still huge
            chunks: List[str] = []
            for seg in segments:
                if len(seg) <= SECTION_TARGET_SIZE:
                    chunks.append(seg)
                else:
                    chunks.extend(self._fixed_size_chunks(seg))
            if chunks:
                logger.info(
                    f"[RFPParser] Section-aware chunking: {len(matches)} header(s) → "
                    f"{len(chunks)} chunk(s) (target ≤{SECTION_TARGET_SIZE:,} chars)."
                )
                return chunks

        return self._fixed_size_chunks(text)

    def _fixed_size_chunks(self, text: str) -> List[str]:
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
        total = len(chunks)
        logger.info(f"[RFPParser] Splitting into {total} chunk(s) of ~{CHUNK_SIZE:,} chars each.")
        if self._progress_cb:
            self._progress_cb(
                8,
                f"Section-aware split: {total} chunk(s) — extracting requirements…",
            )

        chunk_extracts: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(chunks, start=1):
            # Map chunk index into progress band 8 → 36 (leave room for merge)
            pct = 8 + int(28 * (idx - 1) / max(total, 1))
            if self._progress_cb:
                self._progress_cb(
                    min(36, pct),
                    f"Parsing chunk {idx}/{total} "
                    f"({len(chunk):,} chars)…",
                )
            try:
                messages = [
                    {"role": "system", "content": RFP_CHUNK_EXTRACT_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Solicitation Number: {self.solicitation_number}\n"
                            f"Chunk {idx} of {total} (in document order):\n\n{chunk}"
                        ),
                    },
                ]
                extract = client.chat_json(messages, max_tokens=CHUNK_MAX_TOKENS)
                chunk_extracts.append(extract)
                logger.info(
                    f"[RFPParser] Chunk {idx}/{total}: "
                    f"{len(extract.get('requirements', []))} requirement(s), "
                    f"{len(extract.get('structural_elements', []))} structural element(s)."
                )
            except Exception as exc:
                logger.warning(f"[RFPParser] Chunk {idx}/{total} extraction failed, continuing: {exc}")

        if not chunk_extracts:
            raise RuntimeError("All chunk extractions failed; nothing to merge.")

        if self._progress_cb:
            self._progress_cb(38, f"Merging {len(chunk_extracts)} chunk extract(s)…")

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
