"""
documents/markdown_renderer.py
------------------------------
Converts Markdown proposal documents into styled, professional PDF and DOCX documents.
Uses WeasyPrint when available, with a full-featured fallback parser that extracts
tables, subheadings, bullet lists, and template styling.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    from utils.helpers import setup_logger
except ImportError:
    from backend.utils.helpers import setup_logger

logger = setup_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Check WeasyPrint support
try:
    import weasyprint
    _WEASYPRINT_AVAILABLE = True
except Exception:
    _WEASYPRINT_AVAILABLE = False


_BASE_CSS = """
@page {
    size: A4;
    margin: 20mm 15mm 20mm 15mm;
    @bottom-right {
        content: counter(page);
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 9pt;
        color: #718096;
    }
    @bottom-left {
        content: "Confidential — Prepared by OrbitAvanya";
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 9pt;
        color: #718096;
    }
}

body {
    font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.6;
    color: #2D3748;
}

h1 {
    font-size: 22pt;
    color: #1A365D;
    border-bottom: 2px solid #3182CE;
    padding-bottom: 8px;
    margin-top: 0;
    margin-bottom: 20px;
    font-weight: 700;
}

h2 {
    font-size: 15pt;
    color: #2B6CB0;
    margin-top: 24px;
    margin-bottom: 12px;
    border-bottom: 1px solid #E2E8F0;
    padding-bottom: 4px;
    page-break-before: always;
    page-break-after: avoid;
}

h3 {
    font-size: 12pt;
    color: #2D3748;
    margin-top: 16px;
    margin-bottom: 8px;
    page-break-after: avoid;
    font-weight: 600;
}

p {
    margin-bottom: 12px;
}

ul, ol {
    margin-top: 4px;
    margin-bottom: 12px;
    padding-left: 24px;
}

li {
    margin-bottom: 4px;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 16px;
    margin-bottom: 20px;
    page-break-inside: avoid;
}

th {
    background-color: #2B6CB0;
    color: #FFFFFF;
    font-weight: 600;
    text-align: left;
    padding: 8px 12px;
    font-size: 10pt;
}

td {
    padding: 8px 12px;
    border-bottom: 1px solid #E2E8F0;
    font-size: 9.5pt;
}

tr:nth-child(even) td {
    background-color: #F7FAFC;
}

blockquote {
    border-left: 4px solid #3182CE;
    background-color: #EBF8FF;
    margin: 16px 0;
    padding: 12px 16px;
    color: #2C5282;
    border-radius: 0 4px 4px 0;
}

code {
    background-color: #EDF2F7;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'Consolas', monospace;
    font-size: 9.5pt;
}
"""

def render_markdown_to_pdf(
    markdown_content: str,
    output_pdf_path: str,
    template_path: Optional[str] = None,
    brand_override: Optional[Dict[str, Any]] = None
) -> str:
    """Converts a Markdown string to a PDF using markdown + WeasyPrint or docx fallback."""
    output_pdf = Path(output_pdf_path)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    # Extract template brand if template file is provided
    brand_cfg = None
    if template_path and Path(template_path).exists():
        try:
            from documents.bidforge.template_profile import extract_template_brand
            brand_cfg = extract_template_brand(template_path, output_dir=str(output_pdf.parent))
        except Exception as e:
            logger.warning(f"[MarkdownRenderer] Failed to extract template brand from {template_path}: {e}")

    if not brand_cfg:
        if brand_override:
            brand_cfg = brand_override
        else:
            import importlib
            try:
                from backend.documents.brand_config import get_brand_config
            except ImportError:
                get_brand_config = importlib.import_module("documents.brand_config").get_brand_config
            brand_cfg = get_brand_config()

    if _WEASYPRINT_AVAILABLE:
        try:
            import importlib
            markdown = importlib.import_module("markdown")
            html_body = markdown.markdown(
                markdown_content,
                extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists']
            )

            accent_val = str(brand_cfg.get('accent_color') or '2B6CB0').strip()
            accent_hex = accent_val if accent_val.startswith('#') else f"#{accent_val}"
            custom_css = _BASE_CSS.replace('#2B6CB0', accent_hex).replace('#3182CE', accent_hex)

            full_html = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{custom_css}</style></head><body>{html_body}</body></html>"
            weasyprint.HTML(string=full_html).write_pdf(target=str(output_pdf))
            logger.info(f"[MarkdownRenderer] Rendered PDF using WeasyPrint: {output_pdf}")
            return str(output_pdf)
        except Exception as e:
            logger.warning(f"[MarkdownRenderer] WeasyPrint rendering failed: {e}. Trying docx fallback.")

    # Fallback to markdown -> docx -> pdf via proposal_generator
    return _fallback_markdown_to_pdf(markdown_content, str(output_pdf), brand_cfg)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_THEMATIC_BREAK_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")
_BULLET_RE = re.compile(r"^([-\*+])\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\d+[.)]\s+(.*)$")
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")


def _parse_markdown_into_sections(markdown_content: str) -> tuple[str, List[Dict[str, Any]]]:
    """Robust Markdown parser for converting arbitrary Markdown into proposal_generator
    sections/blocks. Handles heading levels 1-6, thematic breaks (---), and blockquotes
    (> ...) as their own block types instead of leaking the raw markdown characters into
    the rendered document, and leaves inline formatting (**bold**, *italic*, `code`)
    untouched so it can be rendered consistently downstream by proposal_generator's
    shared inline-formatting tokenizer -- the same one used for bullets and tables."""
    lines = markdown_content.splitlines()
    doc_title = "RFP Response Proposal"
    sections: List[Dict[str, Any]] = []
    current_section: Dict[str, Any] = {"title": "Executive Summary", "page_break_before": False, "blocks": []}
    table_buffer: List[str] = []
    quote_buffer: List[str] = []

    def flush_table():
        nonlocal table_buffer
        if not table_buffer or not current_section:
            table_buffer = []
            return

        headers = []
        rows = []
        for row_line in table_buffer:
            # Strip outer pipes and split respecting escaped pipes
            cleaned = row_line.strip().strip('|')
            cells = [c.replace('\\|', '|').strip() for c in re.split(r'(?<!\\)\|', cleaned)]

            # Skip delimiter line (e.g. |---|---|)
            if all(re.match(r"^:?-+:?$", cell) for cell in cells):
                continue

            if not headers:
                headers = cells
            else:
                rows.append(cells)

        if headers:
            current_section["blocks"].append({
                "type": "table",
                "headers": headers,
                "rows": rows
            })
        table_buffer = []

    def flush_quote():
        nonlocal quote_buffer
        if quote_buffer and current_section:
            current_section["blocks"].append({
                "type": "quote",
                "text": " ".join(line.strip() for line in quote_buffer if line.strip())
            })
        quote_buffer = []

    for line in lines:
        stripped = line.strip()

        # Table row check
        if stripped.startswith("|") and stripped.endswith("|") and "|" in stripped[1:-1]:
            flush_quote()
            table_buffer.append(stripped)
            continue
        elif table_buffer:
            flush_table()

        # Blockquote lines accumulate until a non-quote line breaks the run
        bq_match = _BLOCKQUOTE_RE.match(stripped) if stripped else None
        if bq_match:
            quote_buffer.append(bq_match.group(1))
            continue
        elif quote_buffer:
            flush_quote()

        heading_match = _HEADING_RE.match(line) or (_HEADING_RE.match(stripped) if stripped else None)

        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            if level == 1:
                doc_title = text
            elif level == 2:
                if current_section and (current_section["blocks"] or current_section["title"] != "Executive Summary"):
                    sections.append(current_section)
                current_section = {
                    "title": text,
                    "page_break_before": len(sections) > 0,
                    "blocks": []
                }
            else:
                # Levels 3-6 all become subheadings within the current section,
                # sized by level instead of falling through to plain-text
                # paragraphs (which used to leak raw "####" into the document).
                if current_section is None:
                    current_section = {"title": text, "page_break_before": False, "blocks": []}
                current_section["blocks"].append({
                    "type": "subheading",
                    "text": text,
                    "level": level,
                })
            continue

        if _THEMATIC_BREAK_RE.match(stripped):
            if current_section:
                current_section["blocks"].append({"type": "divider"})
            continue

        if current_section:
            if not stripped:
                continue

            bullet_match = _BULLET_RE.match(stripped)
            numbered_match = _NUMBERED_RE.match(stripped)
            if bullet_match:
                bullet_text = bullet_match.group(2)
                if not current_section["blocks"] or current_section["blocks"][-1]["type"] != "bullets":
                    current_section["blocks"].append({"type": "bullets", "items": []})
                current_section["blocks"][-1]["items"].append(bullet_text)
            elif numbered_match:
                item_text = numbered_match.group(1)
                if not current_section["blocks"] or current_section["blocks"][-1]["type"] != "numbered":
                    current_section["blocks"].append({"type": "numbered", "items": []})
                current_section["blocks"][-1]["items"].append(item_text)
            else:
                # Inline Markdown (**bold**, *italic*, `code`) is left as-is;
                # proposal_generator's shared formatter renders it consistently
                # with bullets/tables/subheadings instead of stripping it here.
                current_section["blocks"].append({"type": "paragraph", "text": stripped})

    if table_buffer:
        flush_table()
    if quote_buffer:
        flush_quote()
    if current_section and (current_section["blocks"] or current_section["title"] != "Executive Summary"):
        sections.append(current_section)

    # Drop any section that ended up with no real content. Each level-2
    # ("## ") heading forces a page break before it (see above) -- if the
    # model ever emits a stray extra "## " heading partway through what
    # should be one continuous section (which happens occasionally: a
    # leftover transition line, an accidentally-duplicated heading, etc.),
    # that stray heading previously became its own "section" with zero
    # blocks, which still got a hard page break and rendered as a blank or
    # near-blank page in the final document. A truly contentless heading
    # contributes nothing worth a page of its own regardless of why it
    # appeared, so it's dropped here rather than rendered.
    def _is_effectively_empty(section: Dict[str, Any]) -> bool:
        blocks = section.get("blocks") or []
        if not blocks:
            return True
        real_content = [b for b in blocks if b.get("type") != "subheading"]
        if real_content:
            return False
        # Only subheading block(s) and nothing else -- still not a real page.
        total_text = sum(len(str(b.get("text", ""))) for b in blocks)
        return total_text < 5

    non_empty_sections = [s for s in sections if not _is_effectively_empty(s)]
    if len(non_empty_sections) != len(sections):
        dropped = [s.get("title", "?") for s in sections if _is_effectively_empty(s)]
        logger.info(f"[MarkdownRenderer] Dropped {len(dropped)} content-less section(s) that would have "
                    f"rendered as blank/near-blank pages: {dropped}")
    sections = non_empty_sections

    return doc_title, sections


def _fallback_markdown_to_pdf(
    markdown_content: str,
    output_pdf_path: str,
    brand_cfg: Dict[str, Any]
) -> str:
    """Converts Markdown to DOCX via proposal_generator and then to PDF."""
    import importlib
    try:
        from backend.scripts import proposal_generator as pg
    except ImportError:
        pg = importlib.import_module("scripts.proposal_generator")

    out_pdf = Path(output_pdf_path)
    docx_path = out_pdf.with_suffix(".docx")

    doc_title, sections = _parse_markdown_into_sections(markdown_content)

    cfg = {
        "brand": brand_cfg,
        "proposal": {
            "title": doc_title,
            "subtitle": "Proposal & Response Document",
            "prepared_for": "Prospective Client",
            "prepared_by": "OrbitAvanya Tech LLP",
            "engagement_ref": "OAT-PROPOSAL-2026",
            "proposal_date": "2026",
            "validity": "90 days",
            "confidentiality_text": "CONFIDENTIAL — This document contains proprietary information."
        },
        "sections": sections
    }

    pg.generate(cfg, str(docx_path))
    pdf_res = pg.convert_to_pdf(str(docx_path), str(out_pdf.parent))
    return pdf_res or str(docx_path)
