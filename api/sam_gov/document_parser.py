"""
api/sam_gov/document_parser.py
------------------------------
Downloads and extracts text content from PDF and HTML attachments.
Uses pypdf to parse PDF files.
"""

import logging
import os
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

from utils.helpers import setup_logger

logger = setup_logger(__name__)


class DocumentParser:
    """
    Downloads documents (PDFs, HTML files) from URLs and extracts their raw text.
    """

    @staticmethod
    def download_file(url: str) -> Optional[bytes]:
        """Download file content from a URL."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            logger.info(f"Downloading document: {url}")
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to download document from {url}: {e}")
            return None

    @staticmethod
    def extract_text_from_pdf(pdf_bytes: bytes) -> str:
        """Extract text from a PDF file using pypdf."""
        import io
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            text_pages = []
            for idx, page in enumerate(reader.pages):
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
        try:
            soup = BeautifulSoup(html_bytes, "lxml")
            
            # Remove scripts, styles, and navigation elements
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()
                
            text = soup.get_text(separator="\n")
            
            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines()]
            chunks = [phrase for phrase in lines if phrase]
            clean_text = "\n".join(chunks)
            
            return clean_text
        except Exception as e:
            logger.error(f"Failed to parse HTML: {e}")
            return ""

    def parse_document(self, url: str) -> Dict[str, Any]:
        """
        Download and parse document at URL.
        """
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path) or "document"
        
        result = {
            "url": url,
            "filename": filename,
            "content": "",
            "status": "failed"
        }

        # Check if url looks like a PDF or HTML
        content_bytes = self.download_file(url)
        if not content_bytes:
            result["status"] = "download_failed"
            return result

        # Determine file type from extension or signature
        is_pdf = filename.lower().endswith(".pdf") or content_bytes.startswith(b"%PDF")
        
        if is_pdf:
            logger.info(f"Parsing PDF document: {filename}")
            text = self.extract_text_from_pdf(content_bytes)
            if text.strip():
                result["content"] = text
                result["status"] = "success"
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
        downloads_dir = os.path.join("downloads", "opportunities", opportunity_id)
        return self.download_and_save_to_path(url, downloads_dir)

    def download_and_save_to_path(self, url: str, target_dir: str) -> Dict[str, Any]:
        """
        Download file from URL, save to the specified target directory,
        and return the metadata and raw binary content.
        Uses response headers to guess the correct filename and extension.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        
        result = {
            "url": url,
            "filename": "document",
            "local_path": "",
            "file_size": 0,
            "binary_content": b"",
            "status": "failed"
        }

        try:
            logger.info(f"Downloading document: {url}")
            response = requests.get(url, headers=headers, timeout=25)
            response.raise_for_status()
            content_bytes = response.content
        except Exception as e:
            logger.error(f"Failed to download document from {url}: {e}")
            result["status"] = "download_failed"
            return result

        # 1. Try to extract filename from Content-Disposition header
        filename = ""
        cd_header = response.headers.get("Content-Disposition")
        if cd_header:
            match = re.search(r'filename=["\']?([^"\';\n]+)["\']?', cd_header)
            if match:
                filename = match.group(1).strip()

        # 2. If no filename in Content-Disposition, parse from URL path
        if not filename:
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path) or "document"
            
            # If filename has no extension or is the generic "download"
            base, ext = os.path.splitext(filename)
            if filename == "download" or not ext:
                # 3. Guess extension from Content-Type or file signature
                ct_header = response.headers.get("Content-Type", "").lower()
                guessed_ext = ""
                if "application/pdf" in ct_header or content_bytes.startswith(b"%PDF"):
                    guessed_ext = ".pdf"
                elif "text/html" in ct_header or content_bytes.startswith(b"<html") or content_bytes.startswith(b"<!DOCTYPE"):
                    guessed_ext = ".html"
                elif "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in ct_header:
                    guessed_ext = ".docx"
                elif "application/msword" in ct_header:
                    guessed_ext = ".doc"
                elif "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in ct_header:
                    guessed_ext = ".xlsx"
                elif "application/vnd.ms-excel" in ct_header:
                    guessed_ext = ".xls"
                elif "application/zip" in ct_header:
                    guessed_ext = ".zip"
                else:
                    # Guess by searching file contents if possible, default to .html
                    guessed_ext = ".html"

                if base == "download" or base == "document":
                    # Use a hash of the URL to prevent collisions
                    import hashlib
                    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                    filename = f"doc_{url_hash}{guessed_ext}"
                else:
                    filename = f"{base}{guessed_ext}"

        result["filename"] = filename

        try:
            os.makedirs(target_dir, exist_ok=True)
            local_filepath = os.path.join(target_dir, filename)
            
            with open(local_filepath, "wb") as f:
                f.write(content_bytes)
                
            logger.info(f"Successfully saved document locally to: {local_filepath}")
            
            result["local_path"] = os.path.abspath(local_filepath)
            result["file_size"] = len(content_bytes)
            result["binary_content"] = content_bytes
            result["status"] = "success"
        except Exception as e:
            logger.error(f"Failed to save document locally to {target_dir}: {e}")
            result["status"] = "save_failed"

        return result

