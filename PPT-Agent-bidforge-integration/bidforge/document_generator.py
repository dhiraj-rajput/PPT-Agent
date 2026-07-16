"""
bidforge/document_generator.py
--------------------------------
Stage 4 of the BidForge pipeline: turn parsed + inventory + competitor +
summarise output into a final proposal document.

Two modes:
  - Template mode: if the user uploaded a .docx template, populate it via
    bidforge/template_filler.py (preserves the template's own headers,
    footers, branding, and imposes no page-count cap).
  - Default mode: no template uploaded -> reuse proposal_generator.py (the
    same OrbitAvanya-branded engine respond_to_rfp.py already uses) so
    output is visually consistent with the rest of the project.

Content generation itself is governed by the master AI_MODE toggle
(BIDFORGE_MODE override), with a deterministic rule-based fallback that
builds the same section shape directly from the summarise-stage data.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.helpers import setup_logger

logger = setup_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def generate_final_document(
    parsed_rfp: Dict[str, Any],
    inventory: Dict[str, Any],
    competitor_intel: Dict[str, Any],
    strategy: Dict[str, Any],
    output_name: str,
    template_path: Optional[str] = None,
) -> str:
    """Returns the path to the generated .docx (and .pdf, if LibreOffice is
    available on the host)."""
    from ai.mode import run_with_fallback

    sections, path_used = run_with_fallback(
        "bidforge",
        ai_fn=lambda: _generate_sections_ai(parsed_rfp, inventory, competitor_intel, strategy),
        rule_fn=lambda: _generate_sections_rules(parsed_rfp, inventory, competitor_intel, strategy),
    )
    logger.info(f"[BidForge:DocGen] Section content generated via '{path_used}' path.")

    out_dir = PROJECT_ROOT / "output" / "bidforge"
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / f"{output_name}.docx"

    if template_path:
        from bidforge.template_filler import fill_template
        fill_template(template_path, sections, str(docx_path))
        logger.info(f"[BidForge:DocGen] Filled uploaded template -> {docx_path}")
    else:
        _generate_with_default_template(sections, parsed_rfp, str(docx_path))
        logger.info(f"[BidForge:DocGen] Built with default OrbitAvanya template -> {docx_path}")

    pdf_path = _try_convert_to_pdf(str(docx_path), str(out_dir))
    return pdf_path or str(docx_path)


# ---------------------------------------------------------------------------
# Content generation (AI path mirrors BidForge's FINAL_DOCUMENT_PROMPT)
# ---------------------------------------------------------------------------

def _generate_sections_ai(
    parsed_rfp: Dict[str, Any], inventory: Dict[str, Any], competitor_intel: Dict[str, Any], strategy: Dict[str, Any]
) -> Dict[str, Any]:
    from ai.client import get_ai_client

    strategy_text = json.dumps(strategy.get("items", []), indent=2)[:8000]
    inventory_text = json.dumps(inventory.get("items", []), indent=2)[:4000]
    requirements_text = parsed_rfp.get("summary", "") or (parsed_rfp.get("raw_text", "") or "")[:4000]

    messages = [
        {
            "role": "system",
            "content": (
                "You are a professional RFP Response Document Generator. Given parsed requirements, "
                "inventory analysis, and a per-item pricing strategy, produce the content for a "
                "customer-facing proposal. Respond ONLY with a JSON object with keys: "
                'executive_summary (str, several thorough paragraphs), '
                'scope_of_work (array of strings, one per deliverable/scope item — no fixed cap), '
                'pricing_table ({"headers": ["Item","Description","Unit Price","Qty","Total"], "rows": [[...]]}), '
                'competitive_positioning (str, several paragraphs — do not name competitors directly), '
                'timeline (array of {"phase": str, "duration": str, "focus": str}), '
                'terms (array of strings — payment/warranty/SLA/validity terms), '
                'next_steps (str). '
                "Use the recommended pricing option (recommended_option_index) from the strategy data for "
                "the pricing table. Never invent prices, quantities, or facts not present in the source data. "
                "Do not artificially shorten sections to keep the document brief — write with the depth a "
                "real proposal for this opportunity deserves; the document has no page limit."
            ),
        },
        {
            "role": "user",
            "content": (
                f"RFP Requirements Summary:\n{requirements_text}\n\n"
                f"Inventory Analysis:\n{inventory_text}\n\n"
                f"Pricing Strategy:\n{strategy_text}"
            ),
        },
    ]
    result = get_ai_client().chat_json(messages)
    if not result.get("executive_summary"):
        raise ValueError("AI document generation returned incomplete content")
    return result


def _generate_sections_rules(
    parsed_rfp: Dict[str, Any], inventory: Dict[str, Any], competitor_intel: Dict[str, Any], strategy: Dict[str, Any]
) -> Dict[str, Any]:
    logger.info("[BidForge:DocGen] Building sections via rule-based template (no AI).")
    items = strategy.get("items", [])

    scope = [f"{it.get('name')} — {it.get('data', '')[:200]}" for it in items] or ["Scope to be defined based on RFP requirements."]

    rows = []
    for it in items:
        idx = it.get("recommended_option_index", 0)
        options = it.get("options", [])
        chosen = options[idx] if idx < len(options) else (options[0] if options else "Price TBD")
        price = chosen.split(":")[-1].strip() if ":" in chosen else chosen
        rows.append([it.get("name", "Item"), it.get("data", "")[:80], price, "1", price])

    return {
        "executive_summary": (
            f"This proposal responds to the requirements identified in {parsed_rfp.get('source_filename', 'the submitted RFP')}. "
            f"It outlines our proposed scope, pricing, and delivery approach based on our current capabilities."
        ),
        "scope_of_work": scope,
        "pricing_table": {"headers": ["Item", "Description", "Unit Price", "Qty", "Total"], "rows": rows},
        "competitive_positioning": "Our offering is positioned to meet the stated requirements at a competitive, market-informed price point.",
        "timeline": [{"phase": "Phase 1", "duration": "TBD", "focus": "Kickoff and requirements confirmation"}],
        "terms": ["Payment terms: Net 30", "Proposal valid for 90 days from date of issue"],
        "next_steps": "Please reach out to schedule a follow-up discussion to finalize scope and timeline.",
    }


# ---------------------------------------------------------------------------
# Default (no-template) rendering via the existing proposal_generator engine
# ---------------------------------------------------------------------------

def _generate_with_default_template(sections: Dict[str, Any], parsed_rfp: Dict[str, Any], output_docx: str) -> str:
    import proposal_generator as pg

    brand = {
        "company_name": "OrbitAvanya Tech LLP",
        "company_short": "OrbitAvanya",
        "logo_path": "assets/logo.png",
        "cover_graphic_path": "assets/cover_graphic.png",
        "body_font": "Fira Sans Light",
        "heading_font": "Fira Sans SemiBold",
        "accent_color": "1F3864",
        "muted_color": "595959",
        "address_line1": "13352 Kettle Camp Rd",
        "address_line2": "Frisco, Texas 75035",
        "phone": "+917021950643",
        "website": "www.orbitavanyatech.com",
    }
    proposal = {
        "title": "RFP Response Proposal",
        "subtitle": "Technical & Pricing Proposal",
        "prepared_for": parsed_rfp.get("metadata", {}).get("issuing_agency", "Prospective Client"),
        "prepared_by": "Ranjeet Kumar — Founder & CEO, OrbitAvanya Tech LLP (AvanyaEdge)",
        "engagement_ref": f"OAT-BIDFORGE-{datetime.now().strftime('%Y%m%d')}",
        "proposal_date": datetime.now().strftime("%B %d, %Y"),
        "validity": "90 days from proposal date",
        "confidentiality_text": (
            "This document contains confidential information of OrbitAvanya Tech LLP. "
            "It is intended solely for the use of the addressed recipient(s)."
        ),
    }

    sections_list = [
        {
            "title": "Executive Summary",
            "page_break_before": True,
            "blocks": [{"type": "paragraph", "text": p} for p in sections.get("executive_summary", "").split("\n\n") if p.strip()],
        },
        {
            "title": "Scope of Work",
            "page_break_before": True,
            "blocks": [{"type": "bullets", "items": sections.get("scope_of_work", [])}],
        },
        {
            "title": "Pricing",
            "page_break_before": True,
            "blocks": [{
                "type": "table",
                "headers": sections.get("pricing_table", {}).get("headers", []),
                "rows": sections.get("pricing_table", {}).get("rows", []),
            }],
        },
        {
            "title": "Competitive Positioning",
            "page_break_before": True,
            "blocks": [{"type": "paragraph", "text": p} for p in sections.get("competitive_positioning", "").split("\n\n") if p.strip()],
        },
        {
            "title": "Implementation Timeline",
            "page_break_before": True,
            "blocks": [{
                "type": "table",
                "headers": ["Phase", "Duration", "Focus"],
                "rows": [[t.get("phase", ""), t.get("duration", ""), t.get("focus", "")] for t in sections.get("timeline", [])],
            }],
        },
        {
            "title": "Terms & Conditions",
            "page_break_before": True,
            "blocks": [{"type": "bullets", "items": sections.get("terms", [])}],
        },
        {
            "title": "Next Steps",
            "page_break_before": True,
            "blocks": [
                {"type": "paragraph", "text": sections.get("next_steps", "")},
                {"type": "signature", "name": "Ranjeet Kumar Singh", "title": "Founder & CEO", "company": "OrbitAvanya Tech LLP (AvanyaEdge)"},
            ],
        },
    ]

    cfg = {"brand": brand, "proposal": proposal, "sections": sections_list}
    return pg.generate(cfg, output_docx)


def _try_convert_to_pdf(docx_path: str, outdir: str) -> Optional[str]:
    try:
        import proposal_generator as pg
        return pg.convert_to_pdf(docx_path, outdir)
    except Exception as exc:
        logger.warning(f"[BidForge:DocGen] PDF conversion unavailable ({exc}). Returning .docx only.")
        return None
