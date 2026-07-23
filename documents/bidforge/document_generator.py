"""
documents/bidforge/document_generator.py
-----------------------------------------
Stage 4 of the BidForge pipeline: builds a client-ready proposal.

REWRITE NOTE (matches original Node.js BidForge's document-generator.ts):
Earlier versions of this file assembled the document from a fixed, hardcoded
Python section skeleton (Executive Summary / Requirements / Scope / Pricing /
Competitive / Timeline / Terms), each populated with short tables and mostly
boilerplate connector text. That produced short (~15-20 page), generic output
because most of the document text was NOT derived from the RFP at all, and
a "no rows -> section vanishes" filter silently dropped sections whenever an
upstream stage returned thin data.

This version restores the original approach: hand ONE LLM call the full
parsed RFP + explore output + pricing strategy, and let it freely author the
entire proposal as Markdown (FINAL_DOCUMENT_PROMPT, ported verbatim from
BidForge). There is no section cap, no row cap, and no "drop empty section"
logic -- the model decides how much each part of the RFP deserves, which is
what produces long, RFP-specific, professional output instead of a generic
skeleton.

The resulting Markdown is rendered through documents/markdown_renderer.py
(WeasyPrint primary, DOCX/proposal_generator fallback), which already knows
how to pull brand colors/logo from an uploaded .docx template.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from utils.helpers import setup_logger

logger = setup_logger(__name__)

# Minimum acceptable length for the generated markdown. Anything shorter than
# this almost certainly means the model returned a stub/error instead of a
# real proposal, and we should fail loudly rather than ship it.
MIN_MARKDOWN_LENGTH = 15000


def generate_final_document(
    parsed_rfp: Dict[str, Any],
    inventory: Dict[str, Any],
    competitor_intel: Dict[str, Any],
    strategy: Dict[str, Any],
    output_name: str,
    template_path: Optional[str] = None,
    wizard_config: Optional[str | Dict[str, Any]] = None,
) -> str:
    """Generate the final proposal document for the BidForge workflow."""
    out_dir = Path(__file__).resolve().parent.parent.parent / "output" / "rfp_respond"
    out_dir.mkdir(parents=True, exist_ok=True)
    target_pdf_path = str(out_dir / f"{output_name}.pdf")

    brand_config = _load_brand_config(template_path, out_dir)
    company_name = brand_config.get("company_name", "OrbitAvanya Tech LLP")

    markdown_content = _generate_markdown(
        parsed_rfp, inventory, competitor_intel, strategy, company_name, wizard_config
    )

    if not markdown_content or len(markdown_content.strip()) < MIN_MARKDOWN_LENGTH:
        raise ValueError(
            f"[BidForge:DocGen] Generated proposal markdown was too short "
            f"({len(markdown_content.strip()) if markdown_content else 0} chars, "
            f"minimum {MIN_MARKDOWN_LENGTH}). Refusing to ship a stub document -- "
            f"check the AI provider logs for the real failure instead of silently "
            f"falling back."
        )

    from documents.markdown_renderer import render_markdown_to_pdf

    final_path = render_markdown_to_pdf(
        markdown_content, target_pdf_path, template_path=template_path, brand_override=brand_config
    )
    logger.info(f"[BidForge:DocGen] Generated final document: {final_path} "
                f"({len(markdown_content)} chars of markdown)")
    return final_path


def _generate_markdown(
    parsed_rfp: Dict[str, Any],
    inventory: Dict[str, Any],
    competitor_intel: Dict[str, Any],
    strategy: Dict[str, Any],
    company_name: str,
    wizard_config: Optional[str | Dict[str, Any]],
) -> str:
    from pipeline.ai.client import get_ai_client
    from documents.prompts import FINAL_DOCUMENT_PROMPT

    buyer_name = _first_present(
        (parsed_rfp.get("metadata", {}) or {}).get("buyer_name"),
        (parsed_rfp.get("metadata", {}) or {}).get("issuing_agency"),
        "Prospective Client",
    )

    # SECTION 1 -- full parsed RFP requirements, not just the short summary.
    section1 = (
        f"COMPANY NAME (use this as the responding/proposing entity throughout): {company_name}\n"
        f"BUYER / CUSTOMER: {buyer_name}\n\n"
        f"Parsed content:\n{parsed_rfp.get('parsed_content', '') or parsed_rfp.get('summary', '')}\n\n"
        f"Structured requirements:\n{json.dumps(parsed_rfp.get('requirements', []), indent=2)}\n\n"
        f"Compliance requirements:\n{json.dumps(parsed_rfp.get('compliance_requirements', []), indent=2)}\n\n"
        f"Missing/flagged fields:\n{json.dumps(parsed_rfp.get('missing_fields', []), indent=2)}\n\n"
        f"Raw source text (for anything not captured above):\n{(parsed_rfp.get('raw_text', '') or '')[:20000]}"
    )

    # SECTION 2 -- inventory + competitor data, as full structured data (not
    # capped, not flattened into a table row).
    section2 = (
        f"INVENTORY ANALYSIS (what we can deliver, generated via '{inventory.get('generated_via', 'unknown')}'):\n"
        f"{json.dumps(inventory.get('items', []), indent=2)}\n\n"
        f"COMPETITOR / MARKET PRICING (generated via '{competitor_intel.get('generated_via', 'unknown')}'):\n"
        f"{json.dumps(competitor_intel.get('items', []), indent=2)}"
    )

    # SECTION 3 -- full pricing strategy including every option + rationale +
    # the thorough per-item "data" field the summariser produces.
    section3 = (
        f"{json.dumps(strategy.get('items', []), indent=2)}\n\n"
        f"Overall strategic notes:\n{strategy.get('strategic_notes', '')}"
    )

    wizard_instructions = _wizard_instructions(wizard_config)

    user_message = f"""\
=======================================================
SECTION 1: PARSED RFP REQUIREMENTS
=======================================================

{section1}

=======================================================
SECTION 2: EXPLORE OUTPUT (Inventory + Competitor Data)
=======================================================

{section2}

=======================================================
SECTION 3: SUMMARISE OUTPUT (Strategic Pricing Decisions)
=======================================================

{section3}

=======================================================
INSTRUCTIONS
=======================================================
Generate the full RFP response document on behalf of "{company_name}".
Use the company name "{company_name}" throughout the document as the responding/proposing entity.
Use the recommended pricing option for each item unless the data clearly indicates otherwise.
{wizard_instructions}
======================================================="""

    messages = [
        {"role": "system", "content": FINAL_DOCUMENT_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # Deliberately NOT routed through run_with_fallback()/rule_fn: there is no
    # sane rule-based substitute for "write a 40-page proposal", so a failure
    # here should raise and be visible, not silently degrade to boilerplate.
    return get_ai_client().chat_text(messages, json_mode=False)


def _wizard_instructions(wizard_config: Optional[str | Dict[str, Any]]) -> str:
    """Turns the pre-generation wizard's section choices into plain-language
    guidance appended to the prompt, instead of a hard post-generation filter
    that could silently delete sections the model already wrote."""
    config = _decode_wizard_config(wizard_config)
    sections = config.get("sections") if isinstance(config, dict) else None
    if not isinstance(sections, list) or not sections:
        return ""

    lines = ["Additionally, honor this section outline requested by the user:"]
    for section in sections:
        if not isinstance(section, dict) or section.get("included") is False:
            continue
        title = str(section.get("title") or section.get("key") or "").strip()
        if not title:
            continue
        description = str(section.get("description") or "").strip()
        key_points = section.get("key_points") or []
        if isinstance(key_points, str):
            key_points = [line.strip() for line in key_points.splitlines() if line.strip()]
        line = f"- Include a section for \"{title}\"."
        if description:
            line += f" Focus: {description}"
        lines.append(line)
        for kp in key_points:
            lines.append(f"    * {kp}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _decode_wizard_config(wizard_config: Optional[str | Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(wizard_config, dict):
        return wizard_config
    if not wizard_config:
        return {}
    try:
        decoded = json.loads(wizard_config)
        return decoded if isinstance(decoded, dict) else {}
    except Exception as exc:
        logger.warning(f"[BidForge:DocGen] Could not parse wizard config: {exc}")
        return {}


def _load_brand_config(template_path: Optional[str], out_dir: Path) -> Dict[str, Any]:
    if template_path:
        try:
            from documents.bidforge.template_profile import extract_template_brand

            return extract_template_brand(template_path, output_dir=str(out_dir))
        except Exception as exc:
            logger.warning(f"[BidForge:DocGen] Template brand extraction failed: {exc}")

    from documents.brand_config import get_brand_config

    return get_brand_config()


def _first_present(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() not in {"not specified", "none", "n/a", "unknown"}:
            return text
    return ""
