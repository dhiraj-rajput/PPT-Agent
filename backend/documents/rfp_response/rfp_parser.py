"""
documents/rfp_response/rfp_parser.py
------------------------------------
Updated RFPParser using the new structured RFP_PARSER_PROMPT and fallback logic.
Removed hardcoded VA/Healthcare regex bias.
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

from utils.helpers import setup_logger
from pipeline.ai.client import get_ai_client
from documents.prompts import RFP_PARSER_PROMPT
from documents.schemas import ParsedRFP

logger = setup_logger(__name__)

class RFPParser:
    """Extracts text from RFP PDF files and parses requirements using structured AI prompt."""

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

    def parse_requirements(self, doc_texts: Dict[str, str]) -> Dict[str, Any]:
        """Parses extracted RFP text using the unified RFP_PARSER_PROMPT."""
        combined_text = "\n\n".join(doc_texts.values())
        if not combined_text.strip():
            logger.warning("No text extracted from RFP documents. Returning empty structure.")
            return self._empty_parse_structure()

        # Was capped at 30,000 chars, silently truncating anything past ~6-8
        # pages of an RFP before it ever reached the model. Gemini 2.5 Flash /
        # most current models comfortably handle 100k+ chars of input, and a
        # truncated RFP is the single biggest cause of "vague, unrelated to
        # the RFP" output downstream -- every later stage inherits this text.
        sample_text = combined_text[:120000]
        if len(combined_text) > len(sample_text):
            logger.warning(
                f"[RFPParser] RFP text ({len(combined_text)} chars) exceeds the "
                f"{len(sample_text)}-char cap and was truncated. Consider chunking "
                f"for very large solicitations."
            )

        messages = [
            {"role": "system", "content": RFP_PARSER_PROMPT},
            {"role": "user", "content": f"Solicitation Number: {self.solicitation_number}\n\nRFP Document Text:\n{sample_text}"}
        ]

        from pipeline.ai.mode import run_with_fallback

        def ai_fn() -> Dict[str, Any]:
            client = get_ai_client()
            ai_res = client.chat_json(messages)
            return {
                "solicitation_number": self.solicitation_number,
                "parsed_content": ai_res.get("parsed_content", ""),
                "missing_fields": ai_res.get("missing_fields", []),
                "metadata": ai_res.get("metadata", {}),
                "requirements": ai_res.get("requirements", []),
                "compliance_requirements": ai_res.get("compliance_requirements", []),
                "summary": ai_res.get("summary", ""),
                "raw_text": sample_text
            }

        def rule_fn() -> Dict[str, Any]:
            logger.warning(f"[RFPParser] Using rule fallback for RFP parsing.")
            return self._rule_fallback(combined_text)

        result, path_used = run_with_fallback("rfp_parser", ai_fn, rule_fn)
        result["generated_via"] = path_used
        return result

    def _empty_parse_structure(self) -> Dict[str, Any]:
        return {
            "solicitation_number": self.solicitation_number,
            "parsed_content": "No content extracted.",
            "missing_fields": ["RFP document text missing"],
            "metadata": {"solicitation_number": self.solicitation_number},
            "requirements": [],
            "compliance_requirements": [],
            "summary": "Empty solicitation document.",
            "raw_text": ""
        }

    def _rule_fallback(self, text: str) -> Dict[str, Any]:
        return {
            "solicitation_number": self.solicitation_number,
            "parsed_content": text[:1000],
            "missing_fields": ["Detailed AI parsing unavailable"],
            "metadata": {"solicitation_number": self.solicitation_number},
            "requirements": [{"name": "General Scope", "description": text[:200], "status": "Required"}],
            "compliance_requirements": [],
            "summary": f"Solicitation {self.solicitation_number} response.",
            "raw_text": text[:5000]
        }
