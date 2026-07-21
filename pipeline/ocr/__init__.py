"""
pipeline/ocr
------------
Unified OCR pipeline with cascading engine fallback.
Primary: Docling (CPU-friendly, handles tables/forms/layouts)
Secondary: PaddleOCR (excellent for complex layouts on CPU)
Tertiary: Enhanced Tesseract (300 DPI with preprocessing)
Last resort: PyMuPDF raw text extraction
"""
from pipeline.ocr.ocr_manager import OCRManager, extract_text_from_file

__all__ = ["OCRManager", "extract_text_from_file"]
