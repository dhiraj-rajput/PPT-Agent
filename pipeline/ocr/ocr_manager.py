"""
pipeline/ocr/ocr_manager.py
----------------------------
Unified OCR manager with cascading engine fallback.

Engine priority (configurable via OCR_ENGINE setting):
  1. Docling    — CPU-friendly, handles tables/forms/layouts within 8GB RAM
  2. PaddleOCR  — excellent table/layout detection on CPU
  3. Tesseract  — enhanced at 300 DPI with image preprocessing
  4. PyMuPDF    — raw text extraction (non-OCR fallback for digital PDFs)

Usage:
    from pipeline.ocr.ocr_manager import OCRManager, extract_text_from_file

    text = extract_text_from_file("path/to/document.pdf")
    # or
    manager = OCRManager()
    result = manager.extract("path/to/document.pdf")
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class OCRManager:
    """
    Cascading OCR manager. Tries engines in priority order and returns
    the first successful result with sufficient text content.
    """

    MIN_CHARS_FOR_SUCCESS = 50  # Minimum chars to consider extraction successful

    def __init__(self, engine: str = "auto", dpi: int = 300):
        """
        Args:
            engine: 'auto' | 'docling' | 'paddleocr' | 'tesseract' | 'pymupdf'
            dpi: DPI for rasterizing PDF pages (used by Tesseract fallback)
        """
        try:
            from config.settings import settings
            self.engine = engine or getattr(settings, "OCR_ENGINE", "auto")
            self.dpi = dpi or getattr(settings, "OCR_DPI", 300)
        except Exception:
            self.engine = engine or "auto"
            self.dpi = dpi or 300

    def extract(self, file_path: Union[str, Path]) -> Dict[str, object]:
        """
        Extract text from a document file using the configured OCR engine cascade.

        Returns:
            {
                "text": str,          # Extracted text
                "engine": str,        # Which engine succeeded
                "pages": int,
                "success": bool,
                "error": str,         # Only if all engines failed
            }
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return {"text": "", "engine": "none", "pages": 0, "success": False,
                    "error": f"File not found: {file_path}"}

        suffix = file_path.suffix.lower()

        if self.engine == "auto":
            engines = self._get_engine_order(suffix)
        else:
            engines = [self.engine]
            # Always add PyMuPDF as last resort for PDFs
            if suffix == ".pdf" and "pymupdf" not in engines:
                engines.append("pymupdf")

        last_error = None
        for eng in engines:
            try:
                result = self._run_engine(eng, file_path)
                if result.get("success") and len(str(result.get("text", ""))) >= self.MIN_CHARS_FOR_SUCCESS:
                    logger.info(f"[OCRManager] Engine '{eng}' succeeded for {file_path.name} "
                                f"({len(str(result.get('text', '')))} chars)")
                    return result
                else:
                    logger.warning(f"[OCRManager] Engine '{eng}' produced insufficient output "
                                   f"({len(str(result.get('text', '')))} chars). Trying next engine.")
                    last_error = result.get("error", "Insufficient output")
            except Exception as e:
                logger.warning(f"[OCRManager] Engine '{eng}' raised exception: {e}")
                last_error = str(e)

        logger.error(f"[OCRManager] All engines failed for {file_path.name}. Last error: {last_error}")
        return {"text": "", "engine": "none", "pages": 0, "success": False,
                "error": last_error or "All OCR engines failed"}

    def extract_from_bytes(self, content: bytes, filename: str = "document.pdf") -> Dict[str, object]:
        """
        Extract text from raw bytes by saving to a temp file.
        """
        import tempfile
        suffix = Path(filename).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            return self.extract(tmp_path)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

    def extract_pages(self, file_path: Union[str, Path]) -> List[str]:
        """
        Extract text as a list of strings (one per page) where possible.
        Falls back to splitting by form-feeds or newlines.
        """
        result = self.extract(file_path)
        text = str(result.get("text", ""))
        if not text:
            return []
        # Try to split by form-feed (page separator)
        pages = text.split("\f")
        if len(pages) <= 1:
            # Split by double newlines as proxy for pages
            pages = [p.strip() for p in text.split("\n\n\n") if p.strip()]
        return pages if pages else [text]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_engine_order(self, suffix: str) -> List[str]:
        """Return the engine priority order based on file type."""
        if suffix == ".pdf":
            return ["docling", "paddleocr", "tesseract", "pymupdf"]
        elif suffix in (".docx", ".doc", ".pptx", ".xlsx"):
            return ["docling", "pymupdf"]
        elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
            return ["docling", "paddleocr", "tesseract"]
        else:
            return ["docling", "pymupdf"]

    def _run_engine(self, engine: str, file_path: Path) -> Dict[str, object]:
        """Run a specific OCR engine on a file."""
        if engine == "docling":
            return self._run_docling(file_path)
        elif engine == "paddleocr":
            return self._run_paddleocr(file_path)
        elif engine == "tesseract":
            return self._run_tesseract(file_path)
        elif engine == "pymupdf":
            return self._run_pymupdf(file_path)
        else:
            return {"text": "", "engine": engine, "pages": 0, "success": False,
                    "error": f"Unknown engine: {engine}"}

    def _run_docling(self, file_path: Path) -> Dict[str, object]:
        """Run Docling OCR."""
        try:
            from pipeline.ocr.docling_ocr import DoclingOCR
            return DoclingOCR.extract_text(file_path)
        except Exception as e:
            return {"text": "", "engine": "docling", "pages": 0, "success": False, "error": str(e)}

    def _run_paddleocr(self, file_path: Path) -> Dict[str, object]:
        """Run PaddleOCR on a PDF (converts pages to images first)."""
        result = {"text": "", "engine": "paddleocr", "pages": 0, "success": False}
        try:
            from paddleocr import PaddleOCR # type: ignore
        except ImportError:
            result["error"] = "PaddleOCR not installed. Run: pip install paddlepaddle paddleocr"
            return result

        try:
            import fitz  # PyMuPDF for page rasterization
            ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            doc = fitz.open(str(file_path))
            all_text = []

            for page_num, page in enumerate(doc):
                mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")

                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
                    tmp_img.write(img_bytes)
                    tmp_img_path = tmp_img.name

                try:
                    ocr_result = ocr.ocr(tmp_img_path, cls=True)
                    page_text = ""
                    if ocr_result and ocr_result[0]:
                        lines = [line[1][0] for line in ocr_result[0] if line and line[1]]
                        page_text = "\n".join(lines)
                    all_text.append(page_text)
                finally:
                    try:
                        Path(tmp_img_path).unlink()
                    except Exception:
                        pass

            doc.close()
            full_text = "\f".join(all_text)  # Form-feed as page separator
            result["text"] = full_text
            result["pages"] = len(all_text)
            result["success"] = bool(full_text.strip())
        except Exception as e:
            result["error"] = str(e)

        return result

    def _run_tesseract(self, file_path: Path) -> Dict[str, object]:
        """Run enhanced Tesseract OCR at 300 DPI with preprocessing."""
        result = {"text": "", "engine": "tesseract", "pages": 0, "success": False}
        try:
            import pytesseract
        except ImportError:
            result["error"] = "pytesseract not installed"
            return result

        try:
            import fitz
            from PIL import Image, ImageFilter, ImageEnhance
            import tempfile

            suffix = file_path.suffix.lower()
            all_text = []

            if suffix == ".pdf":
                doc = fitz.open(str(file_path))
                for page in doc:
                    mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
                    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
                    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                    # Preprocessing: enhance contrast, sharpen
                    img = ImageEnhance.Contrast(img).enhance(1.5)
                    img = img.filter(ImageFilter.SHARPEN)
                    text = pytesseract.image_to_string(img, config="--psm 3 --oem 3")
                    all_text.append(text)
                doc.close()
            else:
                # Image file
                img = Image.open(str(file_path)).convert("L")
                img = ImageEnhance.Contrast(img).enhance(1.5)
                img = img.filter(ImageFilter.SHARPEN)
                text = pytesseract.image_to_string(img, config="--psm 3 --oem 3")
                all_text = [text]

            full_text = "\f".join(all_text)
            result["text"] = full_text
            result["pages"] = len(all_text)
            result["success"] = bool(full_text.strip())
        except Exception as e:
            result["error"] = str(e)

        return result

    def _run_pymupdf(self, file_path: Path) -> Dict[str, object]:
        """Extract text using PyMuPDF (no OCR — only works for digital PDFs)."""
        result = {"text": "", "engine": "pymupdf", "pages": 0, "success": False}
        try:
            import fitz
            doc = fitz.open(str(file_path))
            all_text = []
            for page in doc:
                text = page.get_text("text")
                all_text.append(text or "")
            doc.close()
            full_text = "\f".join(all_text)
            result["text"] = full_text
            result["pages"] = len(all_text)
            result["success"] = bool(full_text.strip())
        except Exception as e:
            try:
                # Fallback to pypdf
                from pypdf import PdfReader
                reader = PdfReader(str(file_path))
                pages_text = []
                for page in reader.pages:
                    t = page.extract_text() or ""
                    pages_text.append(t)
                full_text = "\f".join(pages_text)
                result["text"] = full_text
                result["pages"] = len(pages_text)
                result["success"] = bool(full_text.strip())
                result["engine"] = "pypdf"
            except Exception as e2:
                result["error"] = f"PyMuPDF: {e}; pypdf: {e2}"

        return result


# Module-level convenience function
_manager_singleton: Optional[OCRManager] = None


def get_ocr_manager() -> OCRManager:
    """Return a singleton OCRManager instance."""
    global _manager_singleton
    if _manager_singleton is None:
        _manager_singleton = OCRManager()
    return _manager_singleton


def extract_text_from_file(file_path: Union[str, Path]) -> str:
    """
    Convenience function: extract text from a file using the default OCR manager.
    Returns extracted text as a string, empty string on failure.
    """
    result = get_ocr_manager().extract(file_path)
    return result.get("text", "")
