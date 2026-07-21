"""
app/sam_gov/document_parser.py
------------------------------
Downloads and extracts text content from PDF and HTML attachments.
Fixes: API key injection, content validation (rejects HTML error pages),
filename sanitization, retry logic, and fallback HTML parser.
"""

import logging
import os
import re
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urljoin, urlencode, parse_qs, urlunparse
import requests

try:
    from bs4 import BeautifulSoup as _BS
    _BS_PARSER = "lxml"
    try:
        import lxml  # noqa: F401
    except ImportError:
        _BS_PARSER = "html.parser"
except ImportError:
    _BS = None
    _BS_PARSER = None

from utils.helpers import setup_logger

logger = setup_logger(__name__)

# Illegal filename characters on Windows (also strip on other OS for compatibility)
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SAM_GOV_BASE = "https://api.sam.gov"


def _sanitize_filename(raw: str) -> str:
    """Strip query strings, URL-decode, and remove OS-illegal characters from a filename."""
    # Strip query string from filename if it slipped through
    if "?" in raw:
        raw = raw.split("?")[0]
    # URL-decode %XX sequences
    try:
        from urllib.parse import unquote
        raw = unquote(raw)
    except Exception:
        pass
    # Replace illegal chars with underscore
    raw = _ILLEGAL_CHARS.sub("_", raw)
    # Collapse multiple underscores / spaces
    raw = re.sub(r'_{2,}', '_', raw).strip('_. ')
    return raw or "document"


def _inject_api_key(url: str, api_key: str) -> str:
    """Append or replace the api_key query parameter in a URL."""
    if not api_key:
        return url
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params["api_key"] = [api_key]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


def _resolve_url(url: str, base: str = _SAM_GOV_BASE) -> str:
    """Resolve relative URLs against the SAM.gov base URL."""
    if url.startswith(("http://", "https://")):
        return url
    return urljoin(base, url)


def _is_valid_pdf(content: bytes) -> bool:
    """Return True if content starts with a PDF magic header."""
    return content[:4] == b"%PDF"


class DocumentParser:
    """
    Downloads documents (PDFs, HTML files) from URLs and extracts their raw text.
    Now includes: API key injection, content validation, filename sanitization,
    retry with exponential backoff, and HTML parser fallback.
    """

    _DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/octet-stream,text/html,*/*",
    }
    _MAX_RETRIES = 3
    _RETRY_BASE_WAIT = 1.5  # seconds

    def __init__(self, api_key: str = "") -> None:
        from config.settings import settings
        self.api_key = api_key or getattr(settings, "SAM_GOV_API_KEY", "") or ""

    @staticmethod
    def _get_api_key() -> str:
        try:
            from config.settings import settings
            return getattr(settings, "SAM_GOV_API_KEY", "") or ""
        except Exception:
            return ""

    def download_file(self, url: str) -> Optional[bytes]:
        """Download file content from a URL with retry and API key injection."""
        url = _resolve_url(url)
        url = _inject_api_key(url, self.api_key)
        last_error = None
        for attempt in range(self._MAX_RETRIES):
            try:
                logger.info(f"Downloading document (attempt {attempt+1}): {url}")
                resp = requests.get(
                    url,
                    headers=self._DEFAULT_HEADERS,
                    timeout=30,
                    allow_redirects=True,
                )
                if resp.status_code in (401, 403):
                    logger.warning(f"Auth error {resp.status_code} downloading {url}. Check SAM_GOV_API_KEY.")
                    return None
                resp.raise_for_status()
                return resp.content
            except Exception as e:
                last_error = e
                if attempt < self._MAX_RETRIES - 1:
                    wait = self._RETRY_BASE_WAIT * (2 ** attempt)
                    logger.warning(f"Download attempt {attempt+1} failed: {e}. Retrying in {wait:.1f}s")
                    time.sleep(wait)
        logger.error(f"Failed to download document from {url} after {self._MAX_RETRIES} attempts: {last_error}")
        return None

    @staticmethod
    def extract_text_from_pdf(pdf_bytes: bytes) -> str:
        """Extract text from a PDF file using pypdf."""
        import io
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            text_pages = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_pages.append(page_text)
            full_text = "\n\n".join(text_pages)
            logger.info(f"Extracted {len(reader.pages)} pages of text from PDF.")
            return full_text
        except Exception as e:
            logger.error(f"Failed to parse PDF: {e}")
            return ""

    @staticmethod
    def extract_text_from_html(html_bytes: bytes) -> str:
        """Extract and clean text from HTML content."""
        if _BS is None:
            # Fallback: plain text strip
            try:
                return html_bytes.decode("utf-8", errors="replace")
            except Exception:
                return ""
        try:
            soup = _BS(html_bytes, _BS_PARSER)
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()
            text = soup.get_text(separator="\n")
            lines = [line.strip() for line in text.splitlines()]
            clean_text = "\n".join(phrase for phrase in lines if phrase)
            return clean_text
        except Exception as e:
            logger.error(f"Failed to parse HTML: {e}")
            return ""

    def parse_document(self, url: str) -> Dict[str, Any]:
        """Download and parse document at URL (supports PDFs, Images, Word, HTML, Text)."""
        parsed_url = urlparse(url)
        filename = _sanitize_filename(os.path.basename(parsed_url.path) or "document")

        result = {"url": url, "filename": filename, "content": "", "status": "failed"}

        content_bytes = self.download_file(url)
        if not content_bytes:
            result["status"] = "download_failed"
            return result

        ext = Path(filename).suffix.lower()
        is_pdf = ext == ".pdf" or _is_valid_pdf(content_bytes)

        if is_pdf:
            if not _is_valid_pdf(content_bytes):
                logger.warning(f"File {filename} has PDF extension but no PDF magic bytes — skipping.")
                result["status"] = "invalid_pdf"
                return result
            logger.info(f"Parsing PDF document with OCR pipeline: {filename}")
            try:
                from pipeline.ocr.ocr_manager import get_ocr_manager
                ocr_res = get_ocr_manager().extract_from_bytes(content_bytes, filename=filename)
                text = ocr_res.get("text", "")
            except Exception as e:
                logger.warning(f"OCR manager failed for {filename}: {e}. Falling back to pypdf.")
                text = self.extract_text_from_pdf(content_bytes)

            if text.strip():
                result["content"] = text
                result["status"] = "success"

        elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"):
            logger.info(f"Parsing image document with OCR: {filename}")
            try:
                from pipeline.ocr.ocr_manager import get_ocr_manager
                ocr_res = get_ocr_manager().extract_from_bytes(content_bytes, filename=filename)
                text = ocr_res.get("text", "")
                if text.strip():
                    result["content"] = text
                    result["status"] = "success"
            except Exception as e:
                logger.error(f"Image OCR failed for {filename}: {e}")

        elif ext in (".docx", ".doc"):
            logger.info(f"Parsing Word document: {filename}")
            try:
                from pipeline.ocr.ocr_manager import get_ocr_manager
                ocr_res = get_ocr_manager().extract_from_bytes(content_bytes, filename=filename)
                text = ocr_res.get("text", "")
                if text.strip():
                    result["content"] = text
                    result["status"] = "success"
            except Exception as e:
                logger.error(f"Word doc parsing failed for {filename}: {e}")

        else:
            logger.info(f"Parsing HTML/Text document: {filename}")
            text = self.extract_text_from_html(content_bytes)
            if text.strip():
                result["content"] = text
                result["status"] = "success"

        return result

    def download_and_save_document(self, url: str, opportunity_id: str) -> Dict[str, Any]:
        """
        Download file from URL, save to local downloads directory,
        and return the metadata and raw binary content.
        """
        downloads_dir = Path("downloads") / "opportunities" / opportunity_id
        return self.download_and_save_to_path(url, str(downloads_dir))

    def download_and_save_to_path(self, url: str, target_dir: str) -> Dict[str, Any]:
        """
        Download file from URL, save to the specified target directory.
        - Injects SAM.gov API key into the URL
        - Validates PDF content (rejects HTML error pages saved as PDFs)
        - Sanitizes filename for cross-OS compatibility
        - Uses retry with exponential backoff
        """
        url = _resolve_url(url)
        url_with_key = _inject_api_key(url, self.api_key)

        result = {
            "url": url,
            "filename": "document",
            "local_path": "",
            "file_size": 0,
            "binary_content": b"",
            "status": "failed",
        }

        last_error = None
        response = None
        for attempt in range(self._MAX_RETRIES):
            try:
                logger.info(f"Downloading to disk (attempt {attempt+1}): {url}")
                response = requests.get(
                    url_with_key,
                    headers=self._DEFAULT_HEADERS,
                    timeout=30,
                    allow_redirects=True,
                )
                if response.status_code in (401, 403):
                    logger.warning(
                        f"Auth error {response.status_code} for {url}. "
                        f"Ensure SAM_GOV_API_KEY is set correctly."
                    )
                    result["status"] = "auth_failed"
                    return result
                response.raise_for_status()
                break  # success
            except Exception as e:
                last_error = e
                if attempt < self._MAX_RETRIES - 1:
                    wait = self._RETRY_BASE_WAIT * (2 ** attempt)
                    logger.warning(f"Download attempt {attempt+1} failed: {e}. Retrying in {wait:.1f}s")
                    time.sleep(wait)
                else:
                    logger.error(f"Failed to download {url} after {self._MAX_RETRIES} attempts: {e}")
                    result["status"] = "download_failed"
                    return result

        if response is None:
            result["status"] = "download_failed"
            return result

        content_bytes = response.content

        # --- Determine filename ---
        filename = ""
        cd_header = response.headers.get("Content-Disposition", "")
        if cd_header:
            m = re.search(r'filename=["\']?([^"\';\n]+)["\']?', cd_header)
            if m:
                filename = _sanitize_filename(m.group(1).strip())

        if not filename:
            parsed_url = urlparse(url)
            raw_name = os.path.basename(parsed_url.path) or "document"
            filename = _sanitize_filename(raw_name)

        base, ext = os.path.splitext(filename)
        if not ext or base in ("download", "document", ""):
            ct = response.headers.get("Content-Type", "").lower()
            if "application/pdf" in ct or _is_valid_pdf(content_bytes):
                ext = ".pdf"
            elif "image/png" in ct or content_bytes[:8] == b"\x89PNG\r\n\x1a\n":
                ext = ".png"
            elif "image/jpeg" in ct or content_bytes[:2] == b"\xff\xd8":
                ext = ".jpg"
            elif "text/html" in ct or content_bytes[:15].lower().startswith((b"<html", b"<!doctype")):
                ext = ".html"
            elif "vnd.openxmlformats-officedocument.wordprocessingml" in ct:
                ext = ".docx"
            elif "application/msword" in ct:
                ext = ".doc"
            elif "application/zip" in ct:
                ext = ".zip"
            else:
                ext = ".html"

            if base in ("download", "document", ""):
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                filename = f"doc_{url_hash}{ext}"
            else:
                filename = f"{base}{ext}"

        # --- Reject HTML error pages saved as PDFs ---
        if filename.lower().endswith(".pdf") and not _is_valid_pdf(content_bytes):
            logger.warning(
                f"Skipping {filename}: URL returned HTML/non-PDF content. "
                f"This is likely a login redirect or error page. Check SAM_GOV_API_KEY."
            )
            result["status"] = "invalid_pdf_content"
            return result

        result["filename"] = filename

        try:
            target_path = Path(target_dir)
            target_path.mkdir(parents=True, exist_ok=True)
            local_filepath = target_path / filename

            with open(local_filepath, "wb") as f:
                f.write(content_bytes)

            logger.info(f"Successfully saved document locally to: {local_filepath}")
            result["local_path"] = str(local_filepath.resolve())
            result["file_size"] = len(content_bytes)
            result["binary_content"] = content_bytes
            result["status"] = "success"
        except Exception as e:
            logger.error(f"Failed to save document locally to {target_dir}: {e}")
            result["status"] = "save_failed"

        return result
