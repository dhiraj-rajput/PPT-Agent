"""
bidforge/template_filler.py
----------------------------
Generates a branded proposal document by:
  1. Extracting branding assets (fonts, colors, logo, margins) from the
     user-uploaded .docx template using TemplateAnalyzer — template is
     NEVER modified or written to.
  2. Building a completely NEW document from scratch using proposal_generator.py,
     driven by the extracted brand profile.

WHY THIS APPROACH (not the old "inject content into template" approach):
  The previous implementation opened the user's template, found headings,
  and inserted paragraphs directly into the original file. This caused:
    - Content appended at the end for any unmatched section
    - Template headings duplicated alongside injected content
    - Fonts and paragraph styles from the template mixed with injected styles
    - The original template permanently modified/mangled

  The correct approach: treat the template as a READ-ONLY branding reference.
  Extract its visual identity, discard the rest, and generate a clean new
  document from scratch.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from utils.helpers import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Section titles (used when no template heading exists for a section)
# ---------------------------------------------------------------------------
_SECTION_TITLES = {
    "executive_summary": "Executive Summary",
    "scope_of_work": "Scope of Work",
    "pricing_table": "Pricing",
    "competitive_positioning": "Competitive Positioning",
    "timeline": "Implementation Timeline",
    "terms": "Terms & Conditions",
    "next_steps": "Next Steps",
}

# Ordered list of sections for consistent document structure
_SECTION_ORDER = [
    "executive_summary",
    "scope_of_work",
    "pricing_table",
    "competitive_positioning",
    "timeline",
    "terms",
    "next_steps",
]


def fill_template(template_path: str, sections: dict[str, Any], output_path: str) -> str:
    """
    Generate a professional proposal document using branding from an uploaded template.

    The template file is opened READ-ONLY — its visual identity (fonts, colors,
    logo, page margins) is extracted and used to style a completely new document.
    The original template is never modified.

    Args:
        template_path:  Path to the user's .docx branding template.
        sections:       Dict of section content from the AI/rule-based generator:
                        {
                          "executive_summary": "text...",
                          "scope_of_work": ["bullet", ...] or "text",
                          "pricing_table": {"headers": [...], "rows": [[...]]},
                          "competitive_positioning": "text",
                          "timeline": [{"phase": ..., "duration": ..., "focus": ...}],
                          "terms": ["term1", "term2", ...],
                          "next_steps": "text",
                        }
        output_path:    Where to save the generated .docx.

    Returns:
        output_path (str)
    """
    logger.info(f"[TemplateFiller] Extracting branding from: {template_path}")

    # 1. Extract branding from the uploaded template (read-only)
    brand_config = _extract_brand(template_path)

    # 2. Build the proposal metadata
    proposal_meta = _build_proposal_meta(sections, brand_config)

    # 3. Convert sections dict → proposal_generator section blocks
    sections_list = _build_sections_list(sections)

    # 4. Assemble config and generate a new document from scratch
    cfg = {
        "brand": brand_config,
        "proposal": proposal_meta,
        "sections": sections_list,
    }

    import importlib
    try:
        from backend.scripts import proposal_generator as pg
    except ImportError:
        pg = importlib.import_module("scripts.proposal_generator")
    pg.generate(cfg, output_path)

    logger.info(
        f"[TemplateFiller] Generated new document with extracted branding -> {output_path} "
        f"(font={brand_config.get('body_font')}, accent=#{brand_config.get('accent_color')})"
    )
    return output_path


# ---------------------------------------------------------------------------
# Brand extraction
# ---------------------------------------------------------------------------

def _extract_brand(template_path: str) -> dict[str, Any]:
    """
    Extract brand assets from the template using TemplateAnalyzer.
    Falls back to the default OrbitAvanya brand if extraction fails.
    """
    try:
        from documents.template_analyzer import (
            TemplateAnalyzer,
        )
        analyzer = TemplateAnalyzer(template_path)
        profile = analyzer.analyze()
        brand = profile.to_brand_config_dict()
        logger.info(
            f"[TemplateFiller] Brand extracted from template: "
            f"font={brand.get('body_font')}, heading_font={brand.get('heading_font')}, "
            f"accent=#{brand.get('accent_color')}, "
            f"logo={'yes' if brand.get('logo_path') else 'no'}"
        )
        return brand
    except Exception as e:
        logger.warning(f"[TemplateFiller] Template branding extraction failed ({e}), using defaults.")
        from documents.brand_config import get_brand_config
        return get_brand_config()


# ---------------------------------------------------------------------------
# Proposal metadata
# ---------------------------------------------------------------------------

def _build_proposal_meta(sections: dict[str, Any], brand: dict[str, Any]) -> dict[str, Any]:
    """Build the proposal-level metadata block for proposal_generator."""
    from documents.brand_config import DEFAULT_CONFIDENTIALITY_TEXT
    return {
        "title": "RFP Response Proposal",
        "subtitle": "Technical & Pricing Proposal",
        "prepared_for": "Prospective Client",
        "prepared_by": f"Ranjeet Kumar — Founder & CEO, {brand.get('company_name', 'OrbitAvanya Tech LLP')}",
        "engagement_ref": f"OAT-BIDFORGE-{datetime.now().strftime('%Y%m%d')}",
        "proposal_date": datetime.now().strftime("%B %d, %Y"),
        "validity": "90 days from proposal date",
        "confidentiality_text": DEFAULT_CONFIDENTIALITY_TEXT,
    }


# ---------------------------------------------------------------------------
# Section blocks builder
# ---------------------------------------------------------------------------

def _build_sections_list(sections: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Convert the AI/rule-based sections dict into the block-list format
    expected by proposal_generator.add_section().
    """
    result = []
    first_section = True

    for key in _SECTION_ORDER:
        content = sections.get(key)
        if not content:
            continue

        title = _SECTION_TITLES.get(key, key.replace("_", " ").title())
        blocks = _content_to_blocks(key, content)

        if not blocks:
            continue

        result.append({
            "title": title,
            "page_break_before": not first_section,
            "blocks": blocks,
        })
        first_section = False

    # Handle any extra keys not in _SECTION_ORDER
    for key, content in sections.items():
        if key not in _SECTION_ORDER and content:
            title = key.replace("_", " ").title()
            blocks = _content_to_blocks(key, content)
            if blocks:
                result.append({
                    "title": title,
                    "page_break_before": True,
                    "blocks": blocks,
                })

    return result


def _content_to_blocks(key: str, content: Any) -> list[dict[str, Any]]:
    """Convert a section's content to a list of proposal_generator block dicts."""
    blocks: list[dict[str, Any]] = []

    # Pricing table dict
    if isinstance(content, dict) and "headers" in content and "rows" in content:
        if content["headers"] and len(content["headers"]) > 0:
            blocks.append({
                "type": "table",
                "headers": content["headers"],
                "rows": content.get("rows", []),
            })
        return blocks

    # String content (split on double newlines for paragraph breaks)
    if isinstance(content, str):
        for para_text in content.split("\n\n"):
            para_text = para_text.strip()
            if para_text:
                blocks.append({"type": "paragraph", "text": para_text})
        return blocks

    # List content
    if isinstance(content, list):
        if not content:
            return blocks

        # Timeline: list of phase dicts
        if all(isinstance(item, dict) and "phase" in item for item in content):
            headers = ["Phase", "Duration", "Focus"]
            rows = [
                [
                    str(item.get("phase", "")),
                    str(item.get("duration", "")),
                    str(item.get("focus", "")),
                ]
                for item in content
            ]
            if rows:
                blocks.append({"type": "table", "headers": headers, "rows": rows})
            return blocks

        # Generic list of dicts — render as "key: value" bullets
        if all(isinstance(item, dict) for item in content):
            items = []
            for item in content:
                line = " — ".join(f"{k}: {v}" for k, v in item.items() if v)
                if line:
                    items.append(line)
            if items:
                blocks.append({"type": "bullets", "items": items})
            return blocks

        # Plain list of strings → bullet list
        str_items = [str(item).strip() for item in content if item]
        if str_items:
            blocks.append({"type": "bullets", "items": str_items})
        return blocks

    return blocks
