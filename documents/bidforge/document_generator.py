"""
documents/bidforge/document_generator.py
-----------------------------------------
Stage 4 of the BidForge pipeline: builds a client-ready DOCX response.

The upload flow accepts an optional Word template. We treat that template as a
read-only brand source (logo, colors, fonts), then generate a clean proposal
document from structured pipeline data. This avoids the old markdown-to-PDF path
that ignored uploaded templates and produced weak layout control.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.helpers import setup_logger

logger = setup_logger(__name__)


def generate_final_document(
    parsed_rfp: Dict[str, Any],
    inventory: Dict[str, Any],
    competitor_intel: Dict[str, Any],
    strategy: Dict[str, Any],
    output_name: str,
    template_path: Optional[str] = None,
) -> str:
    """Generate the final editable proposal document for the BidForge workflow."""
    out_dir = Path(__file__).resolve().parent.parent.parent / "output" / "rfp_respond"
    out_dir.mkdir(parents=True, exist_ok=True)
    target_docx_path = str(out_dir / f"{output_name}.docx")

    brand_config = _load_brand_config(template_path, out_dir)
    proposal_meta = _build_proposal_meta(parsed_rfp, brand_config)
    sections = _build_document_sections(parsed_rfp, inventory, competitor_intel, strategy)

    cfg = {
        "brand": brand_config,
        "proposal": proposal_meta,
        "toc": {"heading": "Proposal Contents"},
        "sections": sections,
    }

    from scripts import proposal_generator as pg

    docx_path = pg.generate(cfg, target_docx_path)
    logger.info(f"[BidForge:DocGen] Generated final DOCX document: {docx_path}")
    return docx_path


def _load_brand_config(template_path: Optional[str], out_dir: Path) -> Dict[str, Any]:
    if template_path:
        try:
            from documents.bidforge.template_profile import extract_template_brand

            return extract_template_brand(template_path, output_dir=str(out_dir))
        except Exception as exc:
            logger.warning(f"[BidForge:DocGen] Template brand extraction failed: {exc}")

    from documents.brand_config import get_brand_config

    return get_brand_config()


def _build_proposal_meta(parsed_rfp: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    from documents.brand_config import DEFAULT_CONFIDENTIALITY_TEXT

    metadata = parsed_rfp.get("metadata", {}) or {}
    buyer = _first_present(
        metadata.get("buyer_name"),
        metadata.get("issuing_agency"),
        "Prospective Client",
    )
    solicitation = _first_present(
        parsed_rfp.get("solicitation_number"),
        metadata.get("solicitation_number"),
        "BIDFORGE",
    )
    title = _first_present(
        metadata.get("project_title"),
        parsed_rfp.get("source_filename"),
        "RFP Response Proposal",
    )

    return {
        "title": f"Response to {title}",
        "subtitle": "Technical, Commercial, and Compliance Proposal",
        "prepared_for": buyer,
        "prepared_by": brand.get("company_name", "OrbitAvanya Tech LLP"),
        "engagement_ref": solicitation,
        "proposal_date": datetime.now().strftime("%B %d, %Y"),
        "validity": "90 days from proposal date unless otherwise stated in the solicitation",
        "confidentiality_text": DEFAULT_CONFIDENTIALITY_TEXT,
    }


def _build_document_sections(
    parsed_rfp: Dict[str, Any],
    inventory: Dict[str, Any],
    competitor_intel: Dict[str, Any],
    strategy: Dict[str, Any],
) -> list[Dict[str, Any]]:
    metadata = parsed_rfp.get("metadata", {}) or {}
    requirements = parsed_rfp.get("requirements", []) or []
    compliance = parsed_rfp.get("compliance_requirements", []) or []
    inventory_items = inventory.get("items", []) or []
    strategy_items = strategy.get("items", []) or []
    strategic_notes = strategy.get("strategic_notes") or ""

    buyer = _first_present(metadata.get("buyer_name"), metadata.get("issuing_agency"), "the buyer")
    summary = parsed_rfp.get("summary") or parsed_rfp.get("parsed_content") or "The uploaded RFP was reviewed and converted into this response."

    sections: list[Dict[str, Any]] = [
        {
            "title": "Executive Summary",
            "page_break_before": False,
            "blocks": [
                {
                    "type": "paragraph",
                    "text": (
                        f"We are pleased to submit this response for {buyer}. {summary} "
                        "Our response is structured around the exact requirements extracted from the uploaded RFP, "
                        "the offerings available in our company inventory, and the pricing strategy selected during analysis."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "The proposal emphasizes a practical delivery approach, clear scope ownership, transparent pricing assumptions, "
                        "and compliance commitments so the evaluation team can quickly understand what is included and where any open items require clarification."
                    ),
                },
            ],
        },
        {
            "title": "Understanding of Requirements",
            "page_break_before": True,
            "blocks": _requirements_blocks(requirements, parsed_rfp.get("missing_fields", []) or []),
        },
        {
            "title": "Scope of Work",
            "page_break_before": True,
            "blocks": _scope_blocks(inventory_items, requirements),
        },
        {
            "title": "Pricing Strategy",
            "page_break_before": True,
            "blocks": _pricing_blocks(strategy_items),
        },
        {
            "title": "Competitive Positioning",
            "page_break_before": True,
            "blocks": _competitor_blocks(competitor_intel, strategic_notes),
        },
        {
            "title": "Implementation Timeline",
            "page_break_before": True,
            "blocks": [
                {
                    "type": "table",
                    "headers": ["Phase", "Duration", "Focus"],
                    "rows": [
                        ["1. Kickoff and Clarification", "Week 1", "Confirm final scope, stakeholders, compliance obligations, and acceptance criteria."],
                        ["2. Delivery Planning", "Weeks 1-2", "Finalize work breakdown, staffing, schedule, risk register, and communication cadence."],
                        ["3. Execution", "Primary contract period", "Deliver the products or services mapped in the scope section with regular status reporting."],
                        ["4. Acceptance and Closeout", "Final delivery window", "Support review, corrections, knowledge transfer, and formal closeout documentation."],
                    ],
                    "col_widths": [1.7, 1.4, 4.4],
                }
            ],
        },
        {
            "title": "Terms, Compliance, and Next Steps",
            "page_break_before": True,
            "blocks": _terms_blocks(compliance),
        },
    ]

    return [section for section in sections if section.get("blocks")]


def _requirements_blocks(requirements: list[Any], missing_fields: list[Any]) -> list[Dict[str, Any]]:
    blocks: list[Dict[str, Any]] = []
    rows = []
    for req in requirements[:20]:
        if isinstance(req, dict):
            rows.append([
                str(req.get("name") or "Requirement"),
                str(req.get("description") or req.get("status") or ""),
                str(req.get("quantity") or "Not specified"),
                str(req.get("timeline") or "Not specified"),
            ])
        else:
            rows.append([str(req), "", "Not specified", "Not specified"])

    if rows:
        blocks.append({
            "type": "table",
            "headers": ["Requirement", "Description", "Quantity", "Timeline"],
            "rows": rows,
            "col_widths": [1.7, 3.4, 1.1, 1.3],
        })
    else:
        blocks.append({"type": "paragraph", "text": "No individual line-item requirements were extracted from the uploaded RFP. The response is based on the available summary and source document text."})

    if missing_fields:
        blocks.append({"type": "subheading", "text": "Clarifications Required"})
        blocks.append({"type": "bullets", "items": [str(item) for item in missing_fields[:12]]})

    return blocks


def _scope_blocks(inventory_items: list[Any], requirements: list[Any]) -> list[Dict[str, Any]]:
    blocks: list[Dict[str, Any]] = [
        {
            "type": "paragraph",
            "text": (
                "The scope below maps the extracted customer requirements to our available inventory and delivery capabilities. "
                "Items marked partial or unavailable should be reviewed before final submission so the commercial response stays accurate."
            ),
        }
    ]

    rows = []
    for item in inventory_items[:20]:
        rows.append([
            str(item.get("name") or "Scope Item"),
            str(item.get("present") or "PARTIAL"),
            str(item.get("availability") or "Not listed"),
            str(item.get("notes") or ""),
        ])

    if rows:
        blocks.append({
            "type": "table",
            "headers": ["Scope Item", "Fit", "Availability", "Notes"],
            "rows": rows,
            "col_widths": [2.0, 0.9, 1.4, 3.2],
        })
    elif requirements:
        blocks.append({"type": "bullets", "items": [str(r.get("name", r)) if isinstance(r, dict) else str(r) for r in requirements[:12]]})

    return blocks


def _pricing_blocks(strategy_items: list[Any]) -> list[Dict[str, Any]]:
    rows = []
    for item in strategy_items:
        options = item.get("options") or []
        rec_idx = item.get("recommended_option_index", 0)
        try:
            recommended = options[int(rec_idx)]
        except Exception:
            recommended = options[0] if options else item.get("current_price", "To be discussed")

        rows.append([
            str(item.get("name") or "Item"),
            str(item.get("current_price") or "Not listed"),
            str(item.get("avg_competitor_price") or "Not listed"),
            str(recommended or "To be discussed"),
        ])

    blocks: list[Dict[str, Any]] = [
        {
            "type": "paragraph",
            "text": "Pricing is based on the available inventory records and market-intelligence snippets. Where source data is missing, the proposal preserves that uncertainty instead of inventing figures.",
        }
    ]
    if rows:
        blocks.append({
            "type": "table",
            "headers": ["Item", "Our Listed Price", "Market Reference", "Recommended Proposal Position"],
            "rows": rows,
            "col_widths": [1.7, 1.4, 1.4, 3.0],
        })
    else:
        blocks.append({"type": "paragraph", "text": "No reliable pricing items were extracted. Final pricing should be confirmed before submission."})
    return blocks


def _competitor_blocks(competitor_intel: Dict[str, Any], strategic_notes: str) -> list[Dict[str, Any]]:
    blocks: list[Dict[str, Any]] = []
    if strategic_notes:
        blocks.append({"type": "paragraph", "text": strategic_notes})

    rows = []
    for item in competitor_intel.get("items", []) or []:
        competitors = item.get("competitors") or []
        rows.append([
            str(item.get("item_name") or "Item"),
            "; ".join(str(c.get("name", "Source")) for c in competitors[:3]) or "No named competitor found",
            str(item.get("avg_price") or "Not listed"),
            str(item.get("market_summary") or "Use best-value positioning and avoid unsupported competitor claims."),
        ])

    if rows:
        blocks.append({
            "type": "table",
            "headers": ["Item", "Market Sources", "Observed Price", "Positioning Note"],
            "rows": rows,
            "col_widths": [1.6, 2.0, 1.2, 2.7],
        })
    else:
        blocks.append({"type": "paragraph", "text": "No competitor pricing could be confirmed from available sources. The response should focus on fit, delivery confidence, and transparent assumptions."})
    return blocks


def _terms_blocks(compliance: list[Any]) -> list[Dict[str, Any]]:
    items = [
        "Final pricing is subject to validation against the buyer's final statement of work, quantities, and contractual terms.",
        "Any items marked as not specified or to be discussed require buyer clarification before contract award or execution.",
        "Project governance will include kickoff alignment, regular status reporting, risk tracking, and formal acceptance checkpoints.",
        "Warranty, support, and service-level commitments will be finalized in accordance with the solicitation and negotiated agreement.",
    ]
    if compliance:
        items.extend(f"Compliance requirement to address: {c}" for c in compliance[:10])

    return [
        {"type": "bullets", "items": items},
        {"type": "subheading", "text": "Next Steps"},
        {"type": "numbered", "items": [
            "Review this generated response against the solicitation instructions and attachment checklist.",
            "Confirm any open pricing, compliance, or delivery assumptions with the proposal owner.",
            "Finalize attachments, signatures, representations, and submission packaging required by the buyer.",
        ]},
    ]


def _first_present(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() not in {"not specified", "none", "n/a", "unknown"}:
            return text
    return ""
