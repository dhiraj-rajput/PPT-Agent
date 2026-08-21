"""
utils/pdf_converter.py
----------------------
Unified DOCX to PDF conversion utility for OrbitAvanya / PPT-Agent.

Provides cross-platform conversion:
  1. LibreOffice `--headless --convert-to pdf` CLI execution (primary cross-platform method)
  2. win32com Microsoft Word COM automation (Windows fallback if Office is installed)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from utils.helpers import setup_logger

logger = setup_logger(__name__)


def convert_docx_to_pdf(docx_path: str | Path, output_dir: str | Path | None = None) -> Path:
    """
    Converts a DOCX file to PDF.
    Returns the absolute Path of the generated PDF.

    Raises:
        RuntimeError if both LibreOffice and Word COM fail or are unavailable.
    """
    docx_file = Path(docx_path).resolve()
    if not docx_file.exists():
        raise FileNotFoundError(f"Input DOCX file not found: {docx_file}")

    target_dir = Path(output_dir).resolve() if output_dir else docx_file.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    expected_pdf = target_dir / f"{docx_file.stem}.pdf"

    # 1. Try LibreOffice CLI first
    libreoffice_bin = (
        shutil.which("libreoffice")
        or shutil.which("soffice")
        or (r"C:\Program Files\LibreOffice\program\soffice.exe" if sys.platform == "win32" and os.path.exists(r"C:\Program Files\LibreOffice\program\soffice.exe") else None)
    )

    if libreoffice_bin:
        try:
            logger.info(f"[PDFConverter] Converting {docx_file.name} using LibreOffice...")
            cmd = [
                libreoffice_bin,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(target_dir),
                str(docx_file),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and expected_pdf.exists():
                logger.info(f"[PDFConverter] Successfully converted to {expected_pdf.name}")
                return expected_pdf
            else:
                logger.warning(f"[PDFConverter] LibreOffice conversion warning: {result.stderr}")
        except Exception as e:
            logger.warning(f"[PDFConverter] LibreOffice failed: {e}")

    # 2. Try Windows MS Word COM Automation if running on Windows
    if sys.platform == "win32":
        try:
            import win32com.client  # type: ignore
            logger.info(f"[PDFConverter] Trying MS Word COM automation for {docx_file.name}...")
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            try:
                doc = word.Documents.Open(str(docx_file))
                # 17 = wdFormatPDF
                doc.SaveAs(str(expected_pdf), FileFormat=17)
                doc.Close()
                logger.info(f"[PDFConverter] Successfully converted via Word COM to {expected_pdf.name}")
                return expected_pdf
            finally:
                word.Quit()
        except Exception as e:
            logger.warning(f"[PDFConverter] MS Word COM automation failed: {e}")

    if expected_pdf.exists():
        return expected_pdf

    raise RuntimeError(
        f"Failed to convert {docx_file.name} to PDF. Neither LibreOffice nor MS Word COM were able to convert the file."
    )
