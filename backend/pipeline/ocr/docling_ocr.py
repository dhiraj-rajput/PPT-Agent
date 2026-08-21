"""
pipeline/ocr/docling_ocr.py
----------------------------
Docling-based document OCR and parsing.
Docling is CPU-friendly, handles tables, forms, multi-column layouts,
and can process PDFs within 8GB RAM without a GPU.

Install: pip install docling
Docs: https://github.com/DS4SD/docling
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DOCLING_AVAILABLE = False
try:
    from docling.document_converter import (
        DocumentConverter as _DoclingConverter,  # type: ignore
    )
    _DOCLING_AVAILABLE = True
except ImportError:
    _DoclingConverter = None
    logger.warning(
        "Docling is not installed. Install with: pip install docling\n"
        "Falling back to PaddleOCR / Tesseract for OCR."
    )


class DoclingOCR:
    """
    Docling-powered document parser.
    Converts PDFs, DOCX, images to structured markdown with table detection.
    """

    _converter: Any = None  # Lazy-loaded singleton

    @classmethod
    def _get_converter(cls) -> object | None:
        """Lazy-initialize the Docling converter (loaded once, reused)."""
        if not _DOCLING_AVAILABLE or _DoclingConverter is None:
            return None
        if cls._converter is None:
            try:
                logger.info("[DoclingOCR] Initializing Docling converter (first use)...")
                cls._converter = _DoclingConverter()
                logger.info("[DoclingOCR] Docling converter ready.")
            except Exception as e:
                logger.error(f"[DoclingOCR] Failed to initialize Docling: {e}")
                cls._converter = None
        return cls._converter

    @classmethod
    def is_available(cls) -> bool:
        """Return True if Docling is installed and initialized."""
        return _DOCLING_AVAILABLE and cls._get_converter() is not None

    @classmethod
    def extract_text(cls, file_path: str | Path) -> dict[str, object]:
        """
        Extract text and structure from a document using Docling.

        Returns:
            {
                "text": str,          # Full extracted text (markdown format)
                "pages": int,         # Number of pages processed
                "engine": "docling",
                "success": bool,
            }
        """
        result = {"text": "", "pages": 0, "engine": "docling", "success": False}

        converter: Any = cls._get_converter()
        if converter is None:
            result["error"] = "Docling not available"
            return result

        file_path = Path(file_path)
        if not file_path.exists():
            result["error"] = f"File not found: {file_path}"
            return result

        try:
            logger.info(f"[DoclingOCR] Processing: {file_path.name}")
            conversion_result = converter.convert(str(file_path))
            markdown_text = conversion_result.document.export_to_markdown()

            # Count approximate pages
            pages = len(conversion_result.document.pages) if hasattr(conversion_result.document, 'pages') else 1

            result["text"] = markdown_text
            result["pages"] = pages
            result["success"] = bool(markdown_text.strip())
            logger.info(f"[DoclingOCR] Extracted {len(markdown_text)} chars from {pages} pages: {file_path.name}")
        except Exception as e:
            logger.error(f"[DoclingOCR] Failed to process {file_path.name}: {e}")
            result["error"] = str(e)

        return result

    @classmethod
    def extract_text_from_bytes(cls, pdf_bytes: bytes, suffix: str = ".pdf") -> dict[str, object]:
        """
        Extract text from raw PDF bytes by saving to a temp file.
        """
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = Path(tmp.name)
        try:
            return cls.extract_text(tmp_path)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass
