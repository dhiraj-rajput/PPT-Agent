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

import concurrent.futures
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.helpers import setup_logger

logger = setup_logger(__name__)

# Minimum acceptable length for the generated markdown. Anything shorter than
# this almost certainly means the model returned a stub/error instead of a
# real proposal, and we should fail loudly rather than ship it.
MIN_MARKDOWN_LENGTH = 15000

# How many sections to generate concurrently. Each section is an independent
# LLM call (same inputs, different brief) -- there is no reason to run them
# one-at-a-time. This is the single biggest lever on wall-clock time for
# Step 5 (by far the longest step for any RFP with more than 2-3 sections).
# Capped modestly so a 15-section outline doesn't fire 15 simultaneous
# requests at whatever AI provider is configured and trip rate limits.
MAX_PARALLEL_SECTIONS = 4


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

    # The bidder's own company profile (UEI, CAGE, NAICS, address, contact,
    # capabilities, products) lives in MongoDB's `own_company_profile`
    # collection -- previously nothing in this pipeline ever read it, so the
    # model had no real values to use for cover-page/registration fields and
    # left placeholders like "[BIDDER TO INSERT: UEI]" in the output even
    # though the real UEI was sitting in the database the whole time.
    company_profile = _fetch_own_company_profile()
    company_name = _first_present(
        company_profile.get("company_name"),
        company_profile.get("legal_name"),
        brand_config.get("company_name"),
        "OrbitAvanya Tech LLP",
    )
    verified_company_block = _format_verified_company_block(company_profile)
    company_profile_summary = _company_profile_summary(template_path, brand_config)

    markdown_content = _generate_markdown(
        parsed_rfp, inventory, competitor_intel, strategy, company_name, wizard_config,
        company_profile_summary=company_profile_summary,
        verified_company_block=verified_company_block,
        preserving_first_page=bool(template_path),
    )

    if not markdown_content or len(markdown_content.strip()) < MIN_MARKDOWN_LENGTH:
        raise ValueError(
            f"[BidForge:DocGen] Generated proposal markdown was too short "
            f"({len(markdown_content.strip()) if markdown_content else 0} chars, "
            f"minimum {MIN_MARKDOWN_LENGTH}). Refusing to ship a stub document -- "
            f"check the AI provider logs for the real failure instead of silently "
            f"falling back."
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
                template_path, sections, brand_config, target_docx_path,
                company_profile=company_profile,
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
    so generated content references real details instead of inventing them.
    This is a secondary/stylistic source -- _fetch_own_company_profile()
    below is the authoritative one for factual fields like UEI/CAGE."""
    if not template_path:
        return ""
    try:
        from documents.template_analyzer import analyze_template
        profile = analyze_template(template_path)
        return profile.to_company_profile_summary()
    except Exception as exc:
        logger.debug(f"[BidForge:DocGen] Could not build company profile summary: {exc}")
        return ""


# Fields worth surfacing to the model by name, in a sensible reading order.
# Anything present in the Mongo document gets included even if not listed
# here (see the loop in _format_verified_company_block), this just controls
# ordering/labels for the common ones.
_PROFILE_FIELD_LABELS = [
    ("company_name", "Company Name"),
    ("legal_name", "Legal Entity Name"),
    ("uei", "UEI (Unique Entity ID)"),
    ("cage_code", "CAGE Code"),
    ("duns", "DUNS Number"),
    ("primary_naics", "Primary NAICS Code"),
    ("primary_naics_desc", "Primary NAICS Description"),
    ("size", "Business Size"),
    ("socioeconomic_status", "Socioeconomic Status / Set-Aside Certifications"),
    ("address", "Address"),
    ("website", "Website"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("poc_name", "Point of Contact"),
    ("poc_title", "Point of Contact Title"),
]


def _fetch_own_company_profile() -> Dict[str, Any]:
    """Fetches the bidder's own company profile from MongoDB
    (`own_company_profile` collection -- the same one the Proposal
    Builder / PreGenerationWizard flow already reads via
    app/routes/companies.py's /own-profile endpoint). Fails soft to an
    empty dict so a Mongo hiccup degrades to "no verified data" rather
    than crashing generation."""
    try:
        from utils.db_client import get_collection
        col = get_collection("own_company_profile")
        doc = col.find_one({}) or {}
        if "_id" in doc:
            doc = {k: v for k, v in doc.items() if k != "_id"}
        if doc:
            logger.info(
                f"[BidForge:DocGen] Loaded own_company_profile from MongoDB "
                f"({len(doc)} field(s): {', '.join(sorted(doc.keys()))})."
            )
        else:
            logger.warning(
                "[BidForge:DocGen] own_company_profile is empty in MongoDB -- "
                "generated content will fall back to template-derived details "
                "and may leave placeholders for fields like UEI/CAGE. Fill in "
                "Settings > Company Profile to fix this."
            )
        return doc
    except Exception as exc:
        logger.warning(f"[BidForge:DocGen] Could not load own_company_profile from MongoDB: {exc}")
        return {}


def _format_verified_company_block(profile: Dict[str, Any]) -> str:
    """Renders the fetched company profile into an explicit, unambiguous
    context block the model is told to treat as ground truth. This directly
    replaces the previous behavior of leaving "[BIDDER TO INSERT: UEI]"-style
    placeholders for data that was actually available the whole time."""
    if not profile:
        return ""

    lines: List[str] = []
    seen_keys = set()
    for key, label in _PROFILE_FIELD_LABELS:
        val = profile.get(key)
        if val:
            lines.append(f"- {label}: {val}")
            seen_keys.add(key)

    capabilities = profile.get("capabilities")
    if capabilities:
        if isinstance(capabilities, list):
            lines.append("- Core Capabilities: " + "; ".join(str(c) for c in capabilities))
        else:
            lines.append(f"- Core Capabilities: {capabilities}")
        seen_keys.add("capabilities")

    products = profile.get("products")
    if products:
        if isinstance(products, list):
            product_lines = []
            for p in products:
                if isinstance(p, dict):
                    product_lines.append(f"{p.get('name', '')} — {p.get('description', '')}".strip(" —"))
                else:
                    product_lines.append(str(p))
            lines.append("- Products/Services: " + "; ".join(product_lines))
        else:
            lines.append(f"- Products/Services: {products}")
        seen_keys.add("products")

    # Anything else in the document that isn't already covered above --
    # keeps this future-proof if new fields get added to the profile schema
    # without this file needing an update to surface them.
    for key, val in profile.items():
        if key in seen_keys or key in ("updatedAt", "id"):
            continue
        if not val or isinstance(val, (dict, list)):
            continue
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: {val}")

    if not lines:
        return ""

    return (
        "OUR VERIFIED COMPANY PROFILE (source of truth -- from our own company "
        "registration data, not the RFP):\n"
        + "\n".join(lines)
        + "\n\nUse these EXACT values wherever the proposal references our company's "
        "identity, registration numbers, contact info, or capabilities. Do NOT write "
        "a bracketed placeholder (e.g. \"[BIDDER TO INSERT: UEI]\") for ANY field "
        "listed above -- the real value is given. Only use a placeholder for "
        "information that is genuinely bidder-specific to THIS SPECIFIC opportunity "
        "and not a general company fact (e.g. a project-specific reference number, "
        "a client's own contract number, a price that depends on strategy decided "
        "elsewhere in this brief)."
    )


def _generate_markdown(
    parsed_rfp: Dict[str, Any],
    inventory: Dict[str, Any],
    competitor_intel: Dict[str, Any],
    strategy: Dict[str, Any],
    company_name: str,
    wizard_config: Optional[str | Dict[str, Any]],
    company_profile_summary: str = "",
    verified_company_block: str = "",
    preserving_first_page: bool = False,
) -> str:
    from pipeline.ai.client import get_ai_client
    from documents.prompts import SECTION_WRITER_PROMPT

    buyer_name = _first_present(
        (parsed_rfp.get("metadata", {}) or {}).get("buyer_name"),
        (parsed_rfp.get("metadata", {}) or {}).get("issuing_agency"),
        "Prospective Client",
    )

    config = _decode_wizard_config(wizard_config)
    sections = config.get("sections") if isinstance(config, dict) else None
    
    # If no sections are configured in the wizard config, fallback to default standard outline
    if not isinstance(sections, list) or not sections:
        sections = [
            {
                "key": "executive_summary",
                "title": "1. Executive Summary",
                "word_budget": 600,
                "included": True,
                "key_points": [
                    "Understanding of Agency mission & critical objectives",
                    "Summary of proposed solution & key discriminators",
                    "Commitment to schedule & compliance"
                ]
            },
            {
                "key": "scope_of_work",
                "title": "2. Scope of Work",
                "word_budget": 1200,
                "included": True,
                "key_points": [
                    "Detailed description of proposed services",
                    "Specific delivery methods & methodology",
                    "Quality assurance & compliance"
                ]
            },
            {
                "key": "pricing_table",
                "title": "3. Pricing Proposal & Deliverables",
                "word_budget": 500,
                "included": True,
                "key_points": [
                    "Breakdown of pricing by service/product item",
                    "Volume discounts or bundle incentives"
                ]
            },
            {
                "key": "implementation_timeline",
                "title": "4. Implementation & Schedule",
                "word_budget": 500,
                "included": True,
                "key_points": [
                    "Milestones and delivery dates",
                    "Resource allocation plan"
                ]
            },
            {
                "key": "terms_conditions",
                "title": "5. Terms and Conditions",
                "word_budget": 400,
                "included": True,
                "key_points": [
                    "Payment schedule & SLA parameters",
                    "Proposal validity period"
                ]
            }
        ]

    # SECTION 1 -- full parsed RFP requirements. raw_text trimmed from 25k to
    # 15k chars: this whole block gets repeated verbatim in every section's
    # own call, so trimming it cuts real latency/cost per call across N
    # sections without losing much (the structured requirements/compliance
    # lists right above it already carry the extracted substance).
    section1 = (
        f"COMPANY NAME (responding entity): {company_name}\n"
        f"BUYER / CUSTOMER: {buyer_name}\n\n"
        f"Parsed content:\n{parsed_rfp.get('parsed_content', '') or parsed_rfp.get('summary', '')}\n\n"
        f"Structured requirements:\n{json.dumps(parsed_rfp.get('requirements', []), indent=2)}\n\n"
        f"Compliance requirements:\n{json.dumps(parsed_rfp.get('compliance_requirements', []), indent=2)}\n\n"
        f"Missing/flagged fields:\n{json.dumps(parsed_rfp.get('missing_fields', []), indent=2)}\n\n"
        f"Raw source text (part):\n{(parsed_rfp.get('raw_text', '') or '')[:15000]}"
    )

    # SECTION 2 -- inventory + competitor data
    section2 = (
        f"INVENTORY ANALYSIS (our products/services available for delivery):\n"
        f"{json.dumps(inventory.get('items', []), indent=2)}\n\n"
        f"COMPETITOR / MARKET PRICING:\n"
        f"{json.dumps(competitor_intel.get('items', []), indent=2)}"
    )

    # SECTION 3 -- strategy
    section3 = (
        f"{json.dumps(strategy.get('items', []), indent=2)}\n\n"
        f"Overall strategic notes:\n{strategy.get('strategic_notes', '')}"
    )

    # Verified Mongo company profile is the PRIMARY/authoritative source for
    # factual company details (UEI, CAGE, address, contact, capabilities).
    # The template-derived summary is a secondary style/tone reference and
    # is explicitly told to defer to the verified block on any conflict.
    company_profile_block = ""
    if verified_company_block:
        company_profile_block += f"\n{verified_company_block}\n"
    if company_profile_summary:
        company_profile_block += f"""
ADDITIONAL COMPANY STYLE/TONE REFERENCE (extracted from the uploaded .docx
template -- use for tone and phrasing only; if it conflicts with OUR
VERIFIED COMPANY PROFILE above on any factual detail like a registration
number, contact info, or company name, the VERIFIED profile above wins):
{company_profile_summary}
"""

    cover_page_note = ""
    if preserving_first_page:
        cover_page_note = """
NOTE ON THE COVER / REGISTRATION PAGE: The uploaded template's own first
page (cover page, registration details, company info) will be kept exactly
as-is and placed before whatever you write here -- do NOT write a title
page, a "Prepared for / Prepared by" block, or restate registration/company
details. Start directly with the first section's substantive content.
"""

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
{company_profile_block}{cover_page_note}"""

    included_sections = [
        s for s in sections
        if isinstance(s, dict) and s.get("included") is not False and str(s.get("title") or s.get("key") or "").strip()
    ]

    def _generate_one(section: Dict[str, Any]) -> str:
        title = str(section.get("title") or section.get("key") or "").strip()
        description = str(section.get("description") or "").strip()
        key_points = section.get("key_points") or []
        if isinstance(key_points, str):
            key_points = [line.strip() for line in key_points.splitlines() if line.strip()]

        section_number = _extract_section_number(title)

        brief = f"SECTION BRIEF to generate:\n- Section Title: {title}\n"
        if section_number:
            brief += (
                f"- This section's number is \"{section_number}\". If you write any "
                f"subsection headings (### or ####), they MUST be numbered "
                f"\"{section_number}.1\", \"{section_number}.2\", \"{section_number}.3\" etc. "
                f"in that exact sequential order -- never a number disconnected from "
                f"\"{section_number}\" (do not invent an unrelated number like \"12.1\").\n"
            )
        if description:
            brief += f"- Focus: {description}\n"
        if key_points:
            brief += "- Key Points to address:\n"
            for kp in key_points:
                # Defensively strip any pre-existing "N.N " numbering from an
                # upstream-generated key_point string before it reaches the
                # model -- if the outline stage itself produced a wrongly
                # -numbered point (e.g. "12.1 Labor Category Mapping..."),
                # echoing it verbatim into the brief is exactly how that
                # wrong number ends up copied straight into the section's
                # own subheadings.
                cleaned_kp = re.sub(r"^\s*\d+(?:\.\d+)*\s+", "", str(kp))
                brief += f"    * {cleaned_kp}\n"
        brief += f"- Target Length: {section.get('word_budget', 500)} words."

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

        logger.info(f"[BidForge:DocGen] Generating section: {title}...")
        section_content = get_ai_client().chat_text(messages, json_mode=False)
        if not section_content:
            return ""
        section_content = section_content.strip()
        # Deterministic safety net: regardless of what the model wrote,
        # force every subsection heading in THIS section's own output to be
        # numbered sequentially under this section's real number. This is
        # what actually guarantees no more "6.0 ... 12.1 ..." jumps, rather
        # than relying on the model following the instruction above.
        if section_number:
            section_content = _renumber_subheadings(section_content, section_number)
        return section_content

    markdown_parts: List[str] = []
    if not preserving_first_page:
        title_line = f"# {company_name} — Response to {buyer_name}"
        markdown_parts.append(title_line)

    if included_sections:
        # Parallel section generation: each call is fully independent (same
        # shared context, different brief), so there is no reason to run
        # them one at a time. This is the single biggest lever on wall-clock
        # time for what was previously the longest-running pipeline step.
        results: List[Optional[str]] = [None] * len(included_sections)
        max_workers = min(MAX_PARALLEL_SECTIONS, len(included_sections))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(_generate_one, section): idx
                for idx, section in enumerate(included_sections)
            }
            for future in concurrent.futures.as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    title = str(included_sections[idx].get("title") or "").strip()
                    logger.error(f"[BidForge:DocGen] Section '{title}' failed to generate: {exc}")
                    results[idx] = ""

        for content in results:
            if content:
                markdown_parts.append(content)

    return "\n\n".join(markdown_parts)


_SECTION_NUMBER_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)")
_SUBHEADING_LINE_RE = re.compile(r"^(#{3,4})\s+(?:\d+(?:\.\d+)*\s+)?(.*)$")


def _extract_section_number(title: str) -> str:
    """Pulls the leading number off a section title, e.g. '6.0 Labor Rate...'
    -> '6', '4.2 Compliance Matrix' -> '4.2'. Returns '' if the title has no
    leading number (in which case subsection renumbering is skipped rather
    than guessing)."""
    match = _SECTION_NUMBER_RE.match(title or "")
    if not match:
        return ""
    num = match.group(1)
    # Normalize "6.0" -> "6" so subsections read "6.1" not "6.0.1".
    if num.endswith(".0"):
        num = num[:-2]
    return num


def _renumber_subheadings(markdown_text: str, section_number: str) -> str:
    """Forces every ### / #### heading within a single generated section's
    markdown to be numbered sequentially under section_number, regardless of
    whatever number (if any) the model wrote. This is what guarantees a
    document can never again jump from section "6.0" straight to a
    subheading "12.1" -- the actual number in the output no longer depends
    on the model getting it right.

    Level-3 (###) headings get "{section_number}.{n}"; a run of level-4
    (####) headings nested under the most recent level-3 heading get
    "{section_number}.{n}.{m}". If the model didn't write any level-3
    headings before a level-4 one, that level-4 heading is numbered directly
    off section_number instead.
    """
    lines = markdown_text.splitlines()
    out_lines: List[str] = []
    h3_counter = 0
    h4_counter = 0
    for line in lines:
        match = _SUBHEADING_LINE_RE.match(line)
        if not match:
            out_lines.append(line)
            continue
        hashes, text = match.groups()
        text = text.strip()
        if len(hashes) == 3:
            h3_counter += 1
            h4_counter = 0
            out_lines.append(f"{hashes} {section_number}.{h3_counter} {text}")
        else:  # #### 
            if h3_counter == 0:
                h3_counter += 1
            h4_counter += 1
            out_lines.append(f"{hashes} {section_number}.{h3_counter}.{h4_counter} {text}")
    return "\n".join(out_lines)


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
