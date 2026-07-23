"""
pipeline/ocr/ocr_api.py
------------------------
Cloud OCR client using OCR.space API.

Free tier: 25,000 requests/month, no registration required.
API key optional (without key: 500 req/day; with free key: 25K/month).
Get a free API key at: https://ocr.space/ocrapi/freekey

Why this over local OCR:
  - Zero local computation (no GPU/CPU intensive model loading)
  - Native multi-page PDF support
  - No rasterization needed — send the PDF directly
  - Table detection mode built-in (Engine2)
  - Works identically on any machine regardless of OS or installed packages

Usage:
    from pipeline.ocr.ocr_api import OCRSpaceClient

    client = OCRSpaceClient(api_key="your_key")  # or reads from env
    result = client.extract_text("path/to/document.pdf")
    # result: {"text": "...", "engine": "ocrspace", "pages": 5, "success": True}
"""

from __future__ import annotations

import io
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)


class OCRSpaceClient:
    """
    Cloud OCR via OCR.space REST API.
    Supports PDF, PNG, JPG, TIFF, BMP, GIF directly.
    """

    BASE_URL = "https://api.ocr.space/parse/image"
    DEFAULT_LANGUAGE = "eng"
    # Engine1 = fast standard OCR, Engine2 = better for tables/forms
    ENGINE_FAST = "1"
    ENGINE_TABLE = "2"

    MIN_CHARS_SUCCESS = 30  # Minimum chars to consider extraction successful

    def __init__(
        self,
        api_key: str = "",
        language: str = "eng",
        timeout: float = 120.0,
    ):
        """
        Args:
            api_key:  OCR.space API key. Defaults to OCR_SPACE_API_KEY env var.
                      Without a key uses "helloworld" (demo, 500 req/day).
            language: OCR language code (default: "eng").
            timeout:  HTTP request timeout in seconds.
        """
        self.api_key = api_key or os.getenv("OCR_SPACE_API_KEY", "") or "helloworld"
        self.language = language
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_text(
        self, file_path: Union[str, Path], use_table_mode: bool = False
    ) -> Dict[str, object]:
        """
        Extract text from a document file using OCR.space API.

        Args:
            file_path:       Path to the file (PDF, PNG, JPG, TIFF, etc.)
            use_table_mode:  If True, uses Engine2 which is optimised for tables/forms.

        Returns:
            {
                "text": str,       # Full extracted text (all pages joined)
                "engine": str,     # "ocrspace"
                "pages": int,      # Number of pages processed
                "success": bool,
                "error": str,      # Only present on failure
            }
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return {
                "text": "",
                "engine": "ocrspace",
                "pages": 0,
                "success": False,
                "error": f"File not found: {file_path}",
            }

        suffix = file_path.suffix.lower()
        
        # Handle PDF page limit edge cases (OCR.space free API limit is 3 pages per upload)
        if suffix == ".pdf":
            try:
                import fitz
                doc = fitz.open(str(file_path))
                page_count = len(doc)
                doc.close()

                if page_count > 3:
                    if page_count > 15:
                        logger.warning(
                            f"[OCRSpace] PDF '{file_path.name}' has {page_count} pages. "
                            "This exceeds the cloud API recommended limit of 15 pages. "
                            "Failing early to trigger local OCR fallback."
                        )
                        return {
                            "text": "",
                            "engine": "ocrspace",
                            "pages": page_count,
                            "success": False,
                            "error": f"PDF too large for cloud API: {page_count} pages",
                        }
                    
                    # Process large PDFs in parallel 3-page chunks
                    return self._process_large_pdf(file_path, page_count, use_table_mode)
            except Exception as e:
                logger.warning(f"[OCRSpace] Failed to inspect PDF page count: {e}. Trying single upload.")

        try:
            result = self._call_api(file_path, use_table_mode=use_table_mode)

            # If fast engine returns too little text, retry with table engine
            if (
                not use_table_mode
                and result.get("success")
                and len(str(result.get("text", ""))) < self.MIN_CHARS_SUCCESS * 3
            ):
                logger.info(
                    "[OCRSpace] Fast engine returned minimal text — retrying with Engine2 (table mode)"
                )
                result2 = self._call_api(file_path, use_table_mode=True)
                if len(str(result2.get("text", ""))) > len(str(result.get("text", ""))):
                    return result2

            return result

        except Exception as e:
            logger.error(f"[OCRSpace] Extraction failed for {file_path.name}: {e}")
            return {
                "text": "",
                "engine": "ocrspace",
                "pages": 0,
                "success": False,
                "error": str(e),
            }

    def _process_large_pdf(
        self, file_path: Path, page_count: int, use_table_mode: bool
    ) -> Dict[str, object]:
        """Split PDF into 3-page chunks, process in parallel, and merge."""
        import fitz
        import tempfile
        from concurrent.futures import ThreadPoolExecutor

        doc = fitz.open(str(file_path))
        chunks: List[Path] = []
        max_pages = 3

        logger.info(f"[OCRSpace] Splitting {page_count}-page PDF '{file_path.name}' into 3-page chunks...")

        try:
            for i in range(0, page_count, max_pages):
                chunk_doc = fitz.open()
                end_page = min(i + max_pages, page_count)
                chunk_doc.insert_pdf(doc, from_page=i, to_page=end_page - 1)
                
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                chunk_path = Path(tmp.name)
                tmp.close()
                
                chunk_doc.save(str(chunk_path))
                chunk_doc.close()
                chunks.append(chunk_path)
        except Exception as e:
            logger.error(f"[OCRSpace] Failed to split PDF: {e}")
            return {
                "text": "",
                "engine": "ocrspace",
                "pages": page_count,
                "success": False,
                "error": f"Failed to split PDF: {e}",
            }
        finally:
            doc.close()

        results: List[Dict[str, Any]] = [None] * len(chunks) # type: ignore

        def _worker(idx: int, path: Path):
            try:
                res = self._call_api(path, use_table_mode=use_table_mode)
                results[idx] = res
            except Exception as exc:
                logger.error(f"[OCRSpace] Chunk {idx} failed: {exc}")
                results[idx] = {"text": "", "success": False, "error": str(exc)}
            finally:
                try:
                    path.unlink()
                except Exception:
                    pass

        # Limit concurrency to 5 parallel workers to prevent rate limiting
        with ThreadPoolExecutor(max_workers=min(len(chunks), 5)) as executor:
            futures = [executor.submit(_worker, idx, path) for idx, path in enumerate(chunks)]
            for fut in futures:
                try:
                    fut.result()
                except Exception:
                    pass

        # Merge text
        merged_texts = []
        total_pages = 0
        success_count = 0
        errors = []

        for idx, res in enumerate(results):
            if res and res.get("success"):
                merged_texts.append(str(res.get("text", "")))
                total_pages += int(res.get("pages", 0))
                success_count += 1
            else:
                err_msg = res.get("error", "Unknown error") if res else "No response"
                errors.append(f"Chunk {idx}: {err_msg}")

        full_text = "\f".join(merged_texts)
        success = len(full_text.strip()) >= self.MIN_CHARS_SUCCESS

        if success_count == len(chunks):
            return {
                "text": full_text,
                "engine": "ocrspace",
                "pages": total_pages,
                "success": success,
            }
        else:
            err_summary = "; ".join(errors)
            logger.warning(f"[OCRSpace] Parallel extraction completed with errors: {err_summary}")
            return {
                "text": full_text,
                "engine": "ocrspace",
                "pages": total_pages,
                "success": success,  # True if we still got enough characters from successful chunks
                "error": err_summary,
            }

    def extract_from_bytes(
        self, content: bytes, filename: str = "document.pdf"
    ) -> Dict[str, object]:
        """
        Extract text from raw bytes by sending directly to OCR.space.
        """
        import tempfile

        suffix = Path(filename).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            return self.extract_text(tmp_path)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call_api(
        self, file_path: Path, use_table_mode: bool = False
    ) -> Dict[str, object]:
        """
        POST the file to the OCR.space API and parse the response.
        """
        engine = self.ENGINE_TABLE if use_table_mode else self.ENGINE_FAST
        suffix = file_path.suffix.lower()

        # OCR.space supports PDFs natively — no rasterization needed
        is_pdf = suffix == ".pdf"

        data = {
            "apikey": self.api_key,
            "language": self.language,
            "isOverlayRequired": "false",
            "detectOrientation": "true",
            "scale": "true",
            "isTable": "true" if use_table_mode else "false",
            "OCREngine": engine,
        }

        # For PDFs: enable multi-page parsing
        if is_pdf:
            data["isSearchablePdfHideTextLayer"] = "false"

        with open(file_path, "rb") as fh:
            file_content = fh.read()

        mime_type = self._get_mime_type(suffix)
        files = {"file": (file_path.name, file_content, mime_type)}

        logger.info(
            f"[OCRSpace] Calling API for '{file_path.name}' "
            f"(engine={engine}, size={len(file_content) // 1024}KB)"
        )

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.BASE_URL, data=data, files=files)

        if resp.status_code == 429:
            raise RuntimeError(
                "OCR.space API rate limit exceeded. "
                "Get a free API key at https://ocr.space/ocrapi/freekey "
                "to raise limit to 25,000 requests/month."
            )

        if not resp.is_success:
            raise RuntimeError(
                f"OCR.space API returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        res_data = resp.json()
        return self._parse_response(res_data, file_path.name)

    def _parse_response(
        self, data: dict, filename: str
    ) -> Dict[str, object]:
        """Parse the OCR.space JSON response into our standard result format."""

        is_error = data.get("IsErroredOnProcessing", False)
        error_msg = data.get("ErrorMessage", [])
        if isinstance(error_msg, list):
            error_msg = "; ".join(error_msg)

        if is_error:
            logger.warning(f"[OCRSpace] API reported processing error for '{filename}': {error_msg}")
            return {
                "text": "",
                "engine": "ocrspace",
                "pages": 0,
                "success": False,
                "error": error_msg or "OCR.space processing error",
            }

        parsed_results = data.get("ParsedResults", [])
        if not parsed_results:
            return {
                "text": "",
                "engine": "ocrspace",
                "pages": 0,
                "success": False,
                "error": "No parsed results returned",
            }

        page_texts: List[str] = []
        for page_result in parsed_results:
            page_text = page_result.get("ParsedText", "") or ""
            page_texts.append(page_text)

        full_text = "\f".join(page_texts)  # form-feed as page separator
        char_count = len(full_text.strip())

        logger.info(
            f"[OCRSpace] '{filename}': {len(page_texts)} page(s), {char_count} chars extracted"
        )

        return {
            "text": full_text,
            "engine": "ocrspace",
            "pages": len(page_texts),
            "success": char_count >= self.MIN_CHARS_SUCCESS,
        }

    def _get_mime_type(self, suffix: str) -> str:
        """Return MIME type for the file suffix."""
        mime_map = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_map.get(suffix, "application/octet-stream")
