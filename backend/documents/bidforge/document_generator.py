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

# Absolute floor -- below this, something has clearly gone wrong (empty
# provider response, etc.) regardless of how small the outline is. The real
# per-document minimum is computed from the outline's own word budgets (see
# _expected_min_chars below) so a genuinely short, simple RFP isn't forced
# to pad itself out to a size tuned for a 90-page tender, and a complex
# tender's minimum scales up instead of being capped at the same old 15k.
ABSOLUTE_MIN_MARKDOWN_LENGTH = 3000

# Roughly how many characters a well-written word ends up as once markdown
# formatting (tables, headers, bullets) is included. Used only to derive a
# sanity-check floor from the outline's word budgets, not to cap anything.
CHARS_PER_WORD_FLOOR = 4.0


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
    target_docx_path = str(out_dir / f"{output_name}.docx")

    brand_config = _load_brand_config(template_path, out_dir)
    company_name = brand_config.get("company_name", "OrbitAvanya Tech LLP")
    company_profile_summary = _company_profile_summary(template_path, brand_config)

    # Headings already present in the uploaded template's preserved front
    # matter (cover page, and anything before the template's own first body
    # heading -- see first_page_preserver.find_first_page_split_index). Used
    # to (a) tell every section-writer call up front which sections NOT to
    # write, and (b) drop the outline entries for them before spending an
    # LLM call generating content that would just get discarded later.
    preserved_headings: list[str] = []
    if template_path and Path(template_path).exists():
        try:
            from documents.bidforge.first_page_preserver import get_preserved_headings
            preserved_headings = get_preserved_headings(template_path)
            if preserved_headings:
                logger.info(
                    f"[BidForge:DocGen] Template already contains: {preserved_headings} -- "
                    f"these will NOT be regenerated."
                )
        except Exception as exc:
            logger.debug(f"[BidForge:DocGen] Could not preview preserved headings: {exc}")

    markdown_content, expected_min_chars = _generate_markdown(
        parsed_rfp, inventory, competitor_intel, strategy, company_name, wizard_config,
        company_profile_summary=company_profile_summary,
        preserving_first_page=bool(template_path),
        preserved_headings=preserved_headings,
    )

    min_length = max(ABSOLUTE_MIN_MARKDOWN_LENGTH, int(expected_min_chars * 0.4))
    if not markdown_content or len(markdown_content.strip()) < min_length:
        raise ValueError(
            f"[BidForge:DocGen] Generated proposal markdown was too short "
            f"({len(markdown_content.strip()) if markdown_content else 0} chars, "
            f"expected at least ~{min_length} for this outline). Refusing to ship a "
            f"stub document -- check the AI provider logs for the real failure "
            f"instead of silently falling back."
        )

    # When a template was uploaded, preserve its actual first/cover page
    # (registration details, contact info, etc.) verbatim -- only patching
    # stale dates -- and append the generated body after it, instead of
    # discarding the template and building a brand-new cover page.
    if template_path and Path(template_path).exists():
        try:
            from documents.markdown_renderer import _parse_markdown_into_sections
            from documents.bidforge.first_page_preserver import build_document_with_preserved_first_page

            _, sections = _parse_markdown_into_sections(markdown_content)
            docx_path = build_document_with_preserved_first_page(
                template_path, sections, brand_config, target_docx_path
            )
            import importlib
            try:
                from backend.scripts import proposal_generator as pg
            except ImportError:
                pg = importlib.import_module("scripts.proposal_generator")
            final_path = pg.convert_to_pdf(docx_path, str(out_dir)) or docx_path
            logger.info(
                f"[BidForge:DocGen] Generated final document preserving template first page: {final_path} "
                f"({len(markdown_content)} chars of markdown)"
            )
            return final_path
        except Exception as exc:
            logger.warning(
                f"[BidForge:DocGen] First-page-preserving render failed ({exc}); "
                f"falling back to brand-only template rendering."
            )

    from documents.markdown_renderer import render_markdown_to_pdf

    final_path = render_markdown_to_pdf(
        markdown_content, target_pdf_path, template_path=template_path, brand_override=brand_config
    )
    logger.info(f"[BidForge:DocGen] Generated final document: {final_path} "
                f"({len(markdown_content)} chars of markdown)")
    return final_path


def _company_profile_summary(template_path: Optional[str], brand_config: Dict[str, Any]) -> str:
    """Best-effort plain-language company profile (website, email, phone,
    leadership) extracted from the uploaded template, for use as AI context
    so generated content references real details instead of inventing them."""
    if not template_path:
        return ""
    try:
        from documents.template_analyzer import analyze_template
        profile = analyze_template(template_path)
        return profile.to_company_profile_summary()
    except Exception as exc:
        logger.debug(f"[BidForge:DocGen] Could not build company profile summary: {exc}")
        return ""


def _resolve_sections(
    wizard_config: Dict[str, Any],
    parsed_rfp: Dict[str, Any],
    company_profile_summary: str,
) -> tuple[list[Dict[str, Any]], str]:
    """Decides the section outline to generate from, in priority order:
      1. Sections explicitly supplied in wizard_config (the user reviewed/
         edited these in the UI after calling /rfp-respond/analyze).
      2. Freshly built via documents.bidforge.outline.build_outline, which
         reads THIS RFP's parsed structure (including mandatory annexures/
         forms) instead of using a fixed skeleton. This is the path taken
         when generation is triggered without going through the wizard
         (e.g. the CLI, or an API caller that skips /analyze).
    Returns (sections, outline_notes).
    """
    sections = wizard_config.get("sections") if isinstance(wizard_config, dict) else None
    if isinstance(sections, list) and sections:
        return sections, str(wizard_config.get("outline_notes") or "")

    from documents.bidforge.outline import build_outline
    outline = build_outline(parsed_rfp, company_context=company_profile_summary)
    return outline.get("sections", []), str(outline.get("notes") or "")


def _section_max_tokens(word_budget: int) -> int:
    """Scales the per-call output token budget to what THIS section actually
    needs instead of every section call inheriting the same flat 8192-token
    default regardless of whether it was asked for 400 words or 4000. ~2.3
    tokens/word covers markdown overhead (tables, headers, bullets) with
    headroom; clamped to a sane floor/ceiling."""
    return max(1200, min(int(word_budget * 2.3) + 400, 16000))


def _generate_markdown(
    parsed_rfp: Dict[str, Any],
    inventory: Dict[str, Any],
    competitor_intel: Dict[str, Any],
    strategy: Dict[str, Any],
    company_name: str,
    wizard_config: Optional[str | Dict[str, Any]],
    company_profile_summary: str = "",
    preserving_first_page: bool = False,
    preserved_headings: Optional[list[str]] = None,
) -> tuple[str, int]:
    """Returns (markdown_text, expected_min_chars) -- the latter is derived
    from the resolved outline's own word budgets so the caller's stub-detection
    floor scales with what THIS document was actually asked to contain."""
    from pipeline.ai.client import get_ai_client
    from documents.prompts import SECTION_WRITER_PROMPT
    from documents.bidforge.first_page_preserver import dedupe_sections_against_preserved
    from documents.bidforge.clarify import answers_to_context_block

    preserved_headings = preserved_headings or []

    buyer_name = _first_present(
        (parsed_rfp.get("metadata", {}) or {}).get("buyer_name"),
        (parsed_rfp.get("metadata", {}) or {}).get("issuing_agency"),
        "Prospective Client",
    )

    config = _decode_wizard_config(wizard_config)
    sections, outline_notes = _resolve_sections(config, parsed_rfp, company_profile_summary)

    # Drop any section that duplicates something already in the preserved
    # template region BEFORE spending an LLM call on it -- not just after.
    sections = dedupe_sections_against_preserved(sections, preserved_headings)
    sections = [s for s in sections if isinstance(s, dict) and s.get("included") is not False and str(s.get("title") or s.get("key") or "").strip()]

    if not sections:
        logger.warning("[BidForge:DocGen] No sections resolved after dedupe -- outline stage may have failed.")

    expected_min_chars = int(sum(int(s.get("word_budget", 500)) for s in sections) * CHARS_PER_WORD_FLOOR)

    # SECTION 1 -- full parsed RFP requirements, including structural
    # elements (mandatory annexures/forms/submission format) so every
    # section call can see the whole compliance picture, not just a flat
    # requirements list.
    section1 = (
        f"COMPANY NAME (responding entity): {company_name}\n"
        f"BUYER / CUSTOMER: {buyer_name}\n"
        f"RFP TYPE: {parsed_rfp.get('rfp_type', 'capability_tender')}\n\n"
        f"Parsed content:\n{parsed_rfp.get('parsed_content', '') or parsed_rfp.get('summary', '')}\n\n"
        f"Structured requirements:\n{json.dumps(parsed_rfp.get('requirements', []), indent=2)}\n\n"
        f"Compliance requirements:\n{json.dumps(parsed_rfp.get('compliance_requirements', []), indent=2)}\n\n"
        f"Structural elements (submission format, mandatory forms/annexures, bid security, pricing format):\n"
        f"{json.dumps(parsed_rfp.get('structural_elements', []), indent=2)}\n\n"
        f"Missing/flagged fields:\n{json.dumps(parsed_rfp.get('missing_fields', []), indent=2)}\n\n"
        f"Raw source text (reference only -- do not quote large verbatim blocks):\n"
        f"{(parsed_rfp.get('raw_text', '') or '')[:40000]}"
    )

    # SECTION 2 -- inventory + competitor data. Only meaningful for
    # product-catalog-style RFPs; for capability-based tenders (construction/
    # EPC/services) these will legitimately be empty, which is fine.
    section2 = (
        f"INVENTORY ANALYSIS (our products/services available for delivery, if applicable to this RFP type):\n"
        f"{json.dumps(inventory.get('items', []), indent=2)}\n\n"
        f"COMPETITOR / MARKET PRICING (if applicable):\n"
        f"{json.dumps(competitor_intel.get('items', []), indent=2)}"
    )

    # SECTION 3 -- strategy
    section3 = (
        f"{json.dumps(strategy.get('items', []), indent=2)}\n\n"
        f"Overall strategic notes:\n{strategy.get('strategic_notes', '')}"
    )

    company_profile_block = ""
    if company_profile_summary:
        company_profile_block = f"""
COMPANY PROFILE (extracted from the uploaded .docx template -- use these
real details whenever you reference contact info, website, or leadership;
never invent different ones):
{company_profile_summary}
"""

    answers_block = answers_to_context_block(config.get("answers") or [])
    answers_section = f"\n{answers_block}\n" if answers_block else ""

    cover_page_note = ""
    if preserving_first_page:
        headings_list = "\n".join(f"  - {h}" for h in preserved_headings) if preserved_headings else "  (none detected -- treat the whole template as front matter)"
        cover_page_note = f"""
NOTE ON THE COVER / REGISTRATION PAGE: The uploaded template's own front
matter will be kept exactly as-is and placed before whatever you write here.
The following heading(s) ALREADY EXIST in that preserved region -- do NOT
write a section with the same or a substantially similar title to any of
these (this includes not writing a title page or a "Prepared for/by" block):
{headings_list}
Start directly with substantive content for the section you were asked to write.
"""

    if outline_notes:
        cover_page_note += f"\nOUTLINE NOTES FROM THE PROPOSAL ARCHITECT STAGE: {outline_notes}\n"

    # Prepare common background for all calls
    common_context = f"""=======================================================
RFP CONTEXT & INPUTS
=======================================================
SECTION 1: PARSED RFP REQUIREMENTS:
{section1}

SECTION 2: EXPLORE OUTPUT (Inventory & Competitor Data):
{section2}

SECTION 3: SUMMARISE OUTPUT (Strategic Pricing Decisions):
{section3}
{company_profile_block}{answers_section}{cover_page_note}"""

    markdown_parts = []

    if not preserving_first_page:
        # Only write our own title line when there is no template cover page
        # to preserve -- otherwise this duplicates the template's own title.
        title_line = f"# {company_name} — Response to {buyer_name}"
        markdown_parts.append(title_line)

    for section in sections:
        title = str(section.get("title") or section.get("key") or "").strip()

        description = str(section.get("description") or "").strip()
        key_points = section.get("key_points") or []
        if isinstance(key_points, str):
            key_points = [line.strip() for line in key_points.splitlines() if line.strip()]
        word_budget = int(section.get("word_budget", 500) or 500)

        brief = f"SECTION BRIEF to generate:\n- Section Title: {title}\n"
        if section.get("is_mandatory_form"):
            brief += (
                "- THIS SECTION IS A MANDATORY RFP FORM/ANNEXURE the bidder must complete "
                "and return, not free-form prose. Reproduce its required fields/structure "
                "and fill in every value you can determine from the RFP context, the company "
                "profile, or the human-confirmed answers above. For any value that is "
                "genuinely bidder-specific and unknown (e.g. a bank guarantee number), leave "
                "a clearly marked placeholder like \"[BIDDER TO INSERT: ...]\" rather than "
                "inventing one.\n"
            )
        if section.get("source_clause"):
            brief += f"- Maps to RFP clause/annexure: {section.get('source_clause')}\n"
        if description:
            brief += f"- Focus: {description}\n"
        if key_points:
            brief += "- Key Points to address:\n"
            for kp in key_points:
                brief += f"    * {kp}\n"
        brief += f"- Target Length: {word_budget} words."

        user_message = f"""{common_context}
=======================================================
INSTRUCTIONS FOR THIS CALL
=======================================================
{brief}
"""

        messages = [
            {"role": "system", "content": SECTION_WRITER_PROMPT},
            {"role": "user", "content": user_message},
        ]

        logger.info(f"[BidForge:DocGen] Generating section: {title} (~{word_budget} words)...")
        section_content = get_ai_client().chat_text(
            messages, json_mode=False, max_tokens=_section_max_tokens(word_budget)
        )
        if section_content:
            markdown_parts.append(section_content.strip())

    return "\n\n".join(markdown_parts), expected_min_chars


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
