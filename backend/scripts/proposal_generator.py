#!/usr/bin/env python3
"""
proposal_generator.py
======================
Generic, reusable business-proposal generator.

Feed it a JSON config (branding + content) and it produces:
  - <output>.docx  -- fully formatted Word document
  - <output>.pdf   -- rendered via LibreOffice (if installed)

The whole point: keep this file untouched, edit config.json (or write a new
config file per client), and re-run. The structure/branding stays identical;
only the content changes -- which is what makes every generated proposal
"the same kind of document" with different client details.

USAGE
-----
    python proposal_generator.py config.json output/MyProposal
    python proposal_generator.py config.json output/MyProposal --no-pdf

REQUIREMENTS
------------
    pip install python-docx
    LibreOffice ('soffice' on PATH) -- only needed for the PDF step.

CONFIG SHAPE
------------
See config.json / README.md for the full schema. In short:

{
  "brand": { company name, logo, cover graphic, colors, fonts, contact... },
  "proposal": { title, subtitle, prepared_for, prepared_by, ref, date... },
  "toc": { "heading": "Content" },
  "sections": [
     {
       "title": "Executive Summary",
       "page_break_before": true,
       "blocks": [
          {"type": "paragraph", "text": "..."},
          {"type": "subheading", "text": "..."},
          {"type": "bullets", "items": ["...", "..."]},
          {"type": "numbered", "items": ["...", "..."]},
          {"type": "table", "headers": ["A","B"], "rows": [["1","2"]]},
          {"type": "signature", "name": "...", "title": "...", "company": "..."},
          {"type": "spacer"}
       ]
     }, ...
  ]
}
"""

import sys
import json
import shutil
import subprocess
import argparse
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from docx import Document
from docx.shared import Inches, Pt, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# --------------------------------------------------------------------------
# Low-level helpers (not in python-docx's public API)
# --------------------------------------------------------------------------

def _set_cell_shading(cell, hex_color):
    """Fill a table cell with a solid background color (hex, no '#')."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _set_paragraph_bottom_border(paragraph, hex_color, size=12):
    """Add a single bottom border/rule under a paragraph (banner-underline look)."""
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), hex_color)
    pBdr.append(bottom)
    pPr.append(pBdr)


def _set_column_widths(table, widths_in):
    """Force explicit column widths (inches) on every row -- Word ignores
    table-level widths unless every cell also states its width."""
    table.autofit = False
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            if idx < len(widths_in):
                cell.width = Inches(widths_in[idx])


def _add_toc_field(paragraph):
    """Insert a real Word TOC field. Word/LibreOffice compute page numbers
    for it automatically the first time the document is opened or converted,
    provided section titles use a Heading style (see add_section_title)."""
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-1" \\h \\z \\u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "Right-click here and choose \u2018Update Field\u2019 to generate the table of contents."
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r = run._r
    r.append(fld_begin)
    r.append(instr)
    r.append(fld_sep)
    r.append(placeholder)
    r.append(fld_end)


def _add_page_number_field(paragraph, cfg):
    """Insert 'Page X of Y' using Word field codes."""
    run = paragraph.add_run("Page ")
    _font(run, cfg, size=8)
    
    # PAGE field
    r = OxmlElement("w:r")
    fld = OxmlElement("w:fldChar")
    fld.set(qn("w:fldCharType"), "begin")
    r.append(fld)
    paragraph._p.append(r)
    
    r2 = OxmlElement("w:r")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    r2.append(instr)
    paragraph._p.append(r2)
    
    r3 = OxmlElement("w:r")
    fld3 = OxmlElement("w:fldChar")
    fld3.set(qn("w:fldCharType"), "end")
    r3.append(fld3)
    paragraph._p.append(r3)
    
    run_of = paragraph.add_run(" of ")
    _font(run_of, cfg, size=8)
    
    # NUMPAGES field
    r4 = OxmlElement("w:r")
    fld4 = OxmlElement("w:fldChar")
    fld4.set(qn("w:fldCharType"), "begin")
    r4.append(fld4)
    paragraph._p.append(r4)
    
    r5 = OxmlElement("w:r")
    instr5 = OxmlElement("w:instrText")
    instr5.set(qn("xml:space"), "preserve")
    instr5.text = " NUMPAGES "
    r5.append(instr5)
    paragraph._p.append(r5)
    
    r6 = OxmlElement("w:r")
    fld6 = OxmlElement("w:fldChar")
    fld6.set(qn("w:fldCharType"), "end")
    r6.append(fld6)
    paragraph._p.append(r6)


def _force_update_fields_on_open(doc):
    """Tell Word (and LibreOffice on conversion) to recompute fields --
    e.g. the TOC page numbers -- as soon as the file is opened/rendered."""
    settings = doc.settings.element
    upd = OxmlElement("w:updateFields")
    upd.set(qn("w:val"), "true")
    settings.append(upd)


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------

def _font(run, cfg, name=None, size: float = 11, bold=False, italic=False, color=None):
    # Use configured font or fall back gracefully
    font_name = name or cfg["brand"].get("body_font", "Calibri")
    # If font name has 'Light' or 'SemiBold' variants that Word may not recognise
    # as separate fonts (vs weight settings), strip the variant and use weight flags
    base_name = font_name.replace(" Light", "").replace(" SemiBold", "").replace(" Bold", "")
    is_semibold = "SemiBold" in font_name or "Bold" in font_name
    is_light = "Light" in font_name
    
    run.font.name = base_name
    run.font.size = Pt(size)
    run.font.bold = bold or is_semibold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    # Word looks up the East-Asian font slot separately; keep it in sync so
    # LibreOffice doesn't silently substitute a fallback font.
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), base_name)
    rFonts.set(qn("w:ascii"), base_name)
    rFonts.set(qn("w:hAnsi"), base_name)


def _accent(cfg):
    return cfg["brand"].get("accent_color", "1F3864")


def _muted(cfg):
    return cfg["brand"].get("muted_color", "595959")


# --------------------------------------------------------------------------
# Cover page
# --------------------------------------------------------------------------

def build_cover_page(doc, cfg):
    brand = cfg["brand"]
    prop = cfg["proposal"]

    graphic = brand.get("cover_graphic_path")
    if graphic and Path(graphic).exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(18)
        run = p.add_run()
        try:
            run.add_picture(graphic, width=Inches(6.5))
        except Exception as e:
            logger.warning(f"Could not load cover graphic image: {e}")

    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_after = Pt(6)
    _font(title_p.add_run(prop["title"]), cfg, name=brand["heading_font"],
          size=28, bold=True, color=_accent(cfg))

    subtitle_p = doc.add_paragraph()
    subtitle_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_p.paragraph_format.space_after = Pt(20)
    _font(subtitle_p.add_run(prop["subtitle"]), cfg, size=14)

    meta_items = [
        f"Prepared for: {prop['prepared_for']}",
        f"Prepared by: {prop['prepared_by']}",
        f"Engagement Reference: {prop['engagement_ref']}",
        f"Proposal Date: {prop['proposal_date']}",
        f"Validity: {prop['validity']}",
    ]
    meta_p = doc.add_paragraph()
    meta_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for i, item in enumerate(meta_items):
        if i > 0:
            _font(meta_p.add_run("  |  "), cfg, size=9.5, color=_muted(cfg))
        _font(meta_p.add_run(item), cfg, size=9.5, color=_muted(cfg))

    doc.add_page_break()


# --------------------------------------------------------------------------
# Table of contents + contact / confidentiality box
# --------------------------------------------------------------------------

def build_toc_page(doc, cfg):
    brand = cfg["brand"]
    toc_cfg = cfg.get("toc", {})

    heading = doc.add_paragraph()
    _font(heading.add_run(toc_cfg.get("heading", "Content")), cfg,
          name=brand["heading_font"], size=20, bold=True, color=_accent(cfg))
    heading.paragraph_format.space_after = Pt(10)

    table = doc.add_table(rows=0, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    for i, section in enumerate(cfg["sections"]):
        row = table.add_row()
        num_cell, title_cell = row.cells
        _font(num_cell.paragraphs[0].add_run(f"{i + 1:02d}"), cfg,
              bold=True, color=_accent(cfg))
        _font(title_cell.paragraphs[0].add_run(section["title"]), cfg)
    _set_column_widths(table, [0.6, 6.9])

    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    add_contact_confidentiality_box(doc, cfg)
    # Always end the TOC page with a page break so the first body section
    # starts at the very top of a fresh page, regardless of TOC length.
    doc.add_page_break()


def add_contact_confidentiality_box(doc, cfg):
    brand = cfg["brand"]
    table = doc.add_table(rows=2, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Row 1: contact details (left) / phone+website (right), light grey
    left, right = table.rows[0].cells
    for cell in (left, right):
        _set_cell_shading(cell, "F2F2F2")

    left.paragraphs[0].text = ""
    _font(left.paragraphs[0].add_run("Contact"), cfg, bold=True, size=10)
    for line in [brand.get("address_line1", ""), brand.get("address_line2", "")]:
        if line:
            p = left.add_paragraph()
            _font(p.add_run(line), cfg, size=10)

    right.paragraphs[0].text = ""
    r_para = right.paragraphs[0]
    r_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _font(r_para.add_run(f"Phone: {brand.get('phone', '')}"), cfg, size=10)
    site_p = right.add_paragraph()
    site_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _font(site_p.add_run(brand.get("website", "")), cfg, size=10)

    # Row 2: confidentiality notice, merged across both columns, darker grey
    conf_left, conf_right = table.rows[1].cells
    merged = conf_left.merge(conf_right)
    _set_column_widths(table, [3.75, 3.75])
    _set_cell_shading(merged, "D9D9D9")
    merged.paragraphs[0].text = ""
    text = cfg["proposal"].get("confidentiality_text", "")
    for i, para_text in enumerate(text.split("\n\n")):
        p = merged.paragraphs[0] if i == 0 else merged.add_paragraph()
        _font(p.add_run(para_text), cfg, size=8.5, color=_muted(cfg))
        p.paragraph_format.space_after = Pt(6)


# --------------------------------------------------------------------------
# Section body content
# --------------------------------------------------------------------------

def add_section_title(doc, cfg, text):
    p = doc.add_paragraph(style="Heading 1")
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(10)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    _font(run, cfg, name=cfg["brand"]["heading_font"], size=17, bold=True,
          color=_accent(cfg))
    _set_paragraph_bottom_border(p, _accent(cfg), size=10)
    return p


import re

def _add_formatted_runs(paragraph, cfg, text, size: float = 11, color=None, default_bold=False):
    # Split by markdown bold tags **...**
    parts = re.split(r"(\*\*.*?\*\*)", str(text))
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            _font(run, cfg, size=size, bold=True, color=color)
        else:
            if part:
                run = paragraph.add_run(part)
                _font(run, cfg, size=size, bold=default_bold, color=color)

def add_subheading(doc, cfg, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    clean_text = text.replace("**", "")
    _font(p.add_run(clean_text), cfg, name=cfg["brand"]["heading_font"], size=12.5,
          bold=True)
    return p


def add_body_paragraph(doc, cfg, text, justify=True):
    p = doc.add_paragraph()
    if justify:
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(8)
    _add_formatted_runs(p, cfg, text, size=11)
    return p


def add_bullets(doc, cfg, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(4)
        _add_formatted_runs(p, cfg, item, size=11)


def add_numbered(doc, cfg, items):
    for item in items:
        p = doc.add_paragraph(style="List Number")
        p.paragraph_format.space_after = Pt(4)
        _add_formatted_runs(p, cfg, item, size=11)


def add_table_block(doc, cfg, headers, rows, col_widths=None):
    if not headers or len(headers) == 0:
        return None

    # Add a small spacer before the table so it doesn't crowd the preceding element
    pre = doc.add_paragraph()
    pre.paragraph_format.space_before = Pt(2)
    pre.paragraph_format.space_after = Pt(2)

    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    hdr_cells = table.rows[0].cells
    for cell, text in zip(hdr_cells, headers):
        _set_cell_shading(cell, _accent(cfg))
        cell.paragraphs[0].text = ""
        _add_formatted_runs(cell.paragraphs[0], cfg, text, size=10.5, color="FFFFFF", default_bold=True)

    for row_idx, row_data in enumerate(rows):
        row = table.add_row()
        # Alternating row shading: light gray background for odd rows (1-indexed: 1st row data is index 0)
        bg_color = "F9F9F9" if row_idx % 2 == 1 else None
        for cell, text in zip(row.cells, row_data):
            if bg_color:
                _set_cell_shading(cell, bg_color)
            cell.paragraphs[0].text = ""
            _add_formatted_runs(cell.paragraphs[0], cfg, text, size=10)

    if col_widths:
        _set_column_widths(table, col_widths)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    return table


def add_signature_block(doc, cfg, name, title, company, salutation="Respectfully,"):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    _font(p.add_run(salutation + "\n\n"), cfg, size=11)
    _font(p.add_run(name), cfg, bold=True, size=11)
    for line in (title, company):
        lp = doc.add_paragraph()
        lp.paragraph_format.space_after = Pt(0)
        _font(lp.add_run(line), cfg, size=11)


_BLOCK_HANDLERS = {
    "paragraph": lambda doc, cfg, b: add_body_paragraph(doc, cfg, b["text"], b.get("justify", True)),
    "subheading": lambda doc, cfg, b: add_subheading(doc, cfg, b["text"]),
    "bullets": lambda doc, cfg, b: add_bullets(doc, cfg, b["items"]),
    "numbered": lambda doc, cfg, b: add_numbered(doc, cfg, b["items"]),
    "table": lambda doc, cfg, b: add_table_block(doc, cfg, b["headers"], b["rows"], b.get("col_widths")),
    "signature": lambda doc, cfg, b: add_signature_block(
        doc, cfg, b["name"], b["title"], b["company"], b.get("salutation", "Respectfully,")),
    "spacer": lambda doc, cfg, b: doc.add_paragraph(),
}


def add_section(doc, cfg, section, index=None):
    if section.get("page_break_before", False):
        doc.add_page_break()
    
    title = section["title"]
    if index is not None:
        # Check if the title already starts with a number like "1." or "1.0"
        import re
        if not re.match(r'^\d+(\.\d+)?\s', title):
            title = f"{index}.0 {title}"
            
    add_section_title(doc, cfg, title)
    for block in section.get("blocks", []):
        handler = _BLOCK_HANDLERS.get(block["type"])
        if handler is None:
            raise ValueError(f"Unknown block type: {block['type']}")
        handler(doc, cfg, block)


# --------------------------------------------------------------------------
# Header / footer (running content on every page)
# --------------------------------------------------------------------------

def setup_headers_footers(doc, cfg):
    brand = cfg["brand"]
    prop = cfg["proposal"]
    section = doc.sections[0]
    section.different_first_page_header_footer = True

    # ---- First page (cover) header: small logo, top-left ----
    fp_header = section.first_page_header
    fp_header.is_linked_to_previous = False
    fp_p = fp_header.paragraphs[0]
    logo = brand.get("logo_path")
    if logo and Path(logo).exists():
        fp_run = fp_p.add_run()
        try:
            fp_run.add_picture(logo, width=Inches(1.1))
        except Exception as e:
            logger.warning(f"Could not load cover header logo image: {e}")

    # First page footer: intentionally blank (matches cover page convention)
    fp_footer = section.first_page_footer
    fp_footer.is_linked_to_previous = False

    # ---- Default header (all other pages): "Customer | Proposal" ----
    header = section.header
    header.is_linked_to_previous = False
    htable = header.add_table(rows=1, cols=2, width=Inches(7.5))
    htable.autofit = False
    left, right = htable.rows[0].cells
    _set_column_widths(htable, [3.75, 3.75])

    left.paragraphs[0].text = ""
    run1 = left.paragraphs[0].add_run("Customer\n")
    _font(run1, cfg, name=brand["body_font"], size=10, bold=False)
    run2 = left.paragraphs[0].add_run(prop["prepared_for"])
    _font(run2, cfg, name=brand["heading_font"], size=10, bold=True)

    right.paragraphs[0].text = ""
    r_p = right.paragraphs[0]
    r_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run3 = r_p.add_run("Proposal\n")
    _font(run3, cfg, name=brand["heading_font"], size=10, bold=True)
    run4 = r_p.add_run(brand["company_name"])
    _font(run4, cfg, name=brand["body_font"], size=8, bold=False)

    # ---- Default footer (all other pages): logo left, company + website right ----
    footer = section.footer
    footer.is_linked_to_previous = False
    ftable = footer.add_table(rows=1, cols=2, width=Inches(7.5))
    ftable.autofit = False
    f_left, f_right = ftable.rows[0].cells
    _set_column_widths(ftable, [3.75, 3.75])

    f_left.paragraphs[0].text = ""
    logo = brand.get("logo_path")
    if logo and Path(logo).exists():
        f_left_run = f_left.paragraphs[0].add_run()
        try:
            f_left_run.add_picture(logo, width=Inches(1.1))
        except Exception:
            pass  # Logo file missing or corrupt — skip gracefully
    # Add page number below logo
    pn_para = f_left.add_paragraph()
    _add_page_number_field(pn_para, cfg)

    f_right.paragraphs[0].text = ""
    f_p = f_right.paragraphs[0]
    f_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run5 = f_p.add_run(brand["company_name"] + "\n")
    _font(run5, cfg, name=brand["body_font"], size=8, bold=False, color=_muted(cfg))
    run6 = f_p.add_run(brand.get("website", ""))
    _font(run6, cfg, name=brand["body_font"], size=10, bold=False, color=_muted(cfg))



# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------

def setup_page(doc):
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)
    section.top_margin = Inches(0.9)   # Slightly more top margin for header
    section.bottom_margin = Inches(0.9)  # Slightly more bottom margin for footer
    section.header_distance = Inches(0.35)
    section.footer_distance = Inches(0.35)
    # Enable widow/orphan control for cleaner pagination
    for style_name in ("Normal", "List Bullet", "List Number"):
        try:
            style = doc.styles[style_name]
            style.paragraph_format.widow_control = True
            # keep_with_next prevents a heading from being orphaned at page bottom
        except Exception:
            pass
    # Enable widow control at the document level via XML
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        settings_elem = doc.settings.element
        compat = OxmlElement("w:compat")
        no_extra_spacing = OxmlElement("w:compatSetting")
        no_extra_spacing.set(qn("w:name"), "useWord2013TrackBottomHyphenation")
        no_extra_spacing.set(qn("w:uri"), "http://schemas.microsoft.com/office/word")
        no_extra_spacing.set(qn("w:val"), "0")
        compat.append(no_extra_spacing)
        settings_elem.append(compat)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def generate(cfg: dict, output_docx: str) -> str:
    doc = Document()
    setup_page(doc)
    setup_headers_footers(doc, cfg)
    _force_update_fields_on_open(doc)

    build_cover_page(doc, cfg)
    build_toc_page(doc, cfg)

    for idx, section in enumerate(cfg["sections"], start=1):
        add_section(doc, cfg, section, index=idx)

    out_path = Path(output_docx)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return str(out_path)


def convert_to_pdf(docx_path: str, outdir: Optional[str] = None) -> str:
    import sys
    import os
    import shutil
    import subprocess
    from pathlib import Path

    outdir = outdir or str(Path(docx_path).parent)
    docx_abs = os.path.abspath(docx_path)
    pdf_path = str(Path(outdir) / (Path(docx_path).stem + ".pdf"))
    pdf_abs = os.path.abspath(pdf_path)

    # 1. On Windows, try Word COM if comtypes is available
    if sys.platform == "win32":
        try:
            import comtypes.client
            import threading
            logger.info("Attempting Word COM conversion to PDF...")
            
            result_holder: dict[str, str | None] = {"pdf_path": None, "error": None}
            
            def _com_convert():
                try:
                    comtypes.CoInitialize()
                    word = comtypes.client.CreateObject('Word.Application')
                    word.Visible = False
                    word.DisplayAlerts = 0
                    try:
                        doc = word.Documents.Open(docx_abs)
                        doc.SaveAs(pdf_abs, FileFormat=17)
                        doc.Close()
                        if os.path.exists(pdf_path):
                            result_holder["pdf_path"] = pdf_path
                    finally:
                        word.Quit()
                except Exception as e:
                    result_holder["error"] = str(e)
                finally:
                    try:
                        comtypes.CoUninitialize()
                    except Exception:
                        pass

            t = threading.Thread(target=_com_convert, daemon=True)
            t.start()
            t.join(timeout=60)  # 60 second timeout
            
            if t.is_alive():
                logger.warning("Word COM conversion timed out after 60s. Falling back to LibreOffice.")
            elif result_holder["pdf_path"]:
                logger.info(f"PDF created via Word COM: {result_holder['pdf_path']}")
                return result_holder["pdf_path"]
            elif result_holder["error"]:
                logger.warning(f"Word COM conversion failed: {result_holder['error']}. Trying LibreOffice...")
        except Exception as e:
            logger.warning(f"Word COM not available: {e}. Trying LibreOffice...")

    # 2. Try to find LibreOffice/soffice on PATH or in common directories
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        mac_soffice = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        common_paths = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            mac_soffice,
            "/usr/bin/soffice",
            "/usr/bin/libreoffice",
        ]
        for p in common_paths:
            if os.path.exists(p):
                soffice = p
                break

    if not soffice:
        logger.warning(
            "Neither Microsoft Word (via COM) nor LibreOffice ('soffice') was found. "
            "Returning generated DOCX document."
        )
        return docx_path

    logger.info(f"Attempting LibreOffice conversion using: {soffice}")
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_abs],
            check=True, capture_output=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("LibreOffice PDF conversion timed out after 60 seconds.")
    # LibreOffice saves it under the same stem with .pdf extension in outdir
    generated_pdf = Path(outdir) / (Path(docx_path).stem + ".pdf")
    if generated_pdf.exists():
        # Use normcase() to handle Windows drive-letter casing differences (E:\ vs e:\)
        gen_resolved = os.path.normcase(os.path.abspath(str(generated_pdf)))
        pdf_resolved = os.path.normcase(pdf_abs)
        if gen_resolved != pdf_resolved:
            try:
                shutil.move(str(generated_pdf), pdf_abs)
            except shutil.Error:
                pass  # Same file or move failed — the file exists at generated_pdf
        return pdf_path
    
    raise FileNotFoundError(f"LibreOffice succeeded but PDF was not found at {pdf_path}")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # Resolve asset paths relative to the config file's own directory so the
    # generator can be run from anywhere.
    base = Path(path).parent
    for key in ("logo_path", "cover_graphic_path"):
        val = cfg["brand"].get(key)
        if val and not Path(val).is_absolute():
            cfg["brand"][key] = str((base / val).resolve())
    return cfg


def main():
    parser = argparse.ArgumentParser(description="Generate a branded proposal document.")
    parser.add_argument("config", help="Path to config JSON file")
    parser.add_argument("output", help="Output path, without extension, e.g. output/MyProposal")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF conversion")
    args = parser.parse_args()

    cfg = load_config(args.config)
    docx_path = generate(cfg, args.output + ".docx")
    print(f"Created: {docx_path}")

    if not args.no_pdf:
        try:
            pdf_path = convert_to_pdf(docx_path)
            print(f"Created: {pdf_path}")
        except RuntimeError as e:
            print(f"[PDF skipped] {e}")


if __name__ == "__main__":
    main()
