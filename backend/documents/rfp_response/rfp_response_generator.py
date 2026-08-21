"""
utils/rfp_response_generator.py
---------------------------------
LLM-powered RFP response section generator using Ollama (gemma4:31b-cloud).

Supports TWO modes:
  - "prime"       → Full LLM-generated RFP response where Orbit Avanya is the prime contractor
  - "subcontract" → Rule-based section builder using compacted JSON company profile

Mode A (prime):
  Uses Ollama gemma4:31b-cloud to generate all document sections based on:
    - RFP text / rfp_data dict
    - Orbit Avanya's company profile (private/orbit_avanya_detailed_profiles.json)
    - Competitor intelligence (optimized_profile from compactor)

Mode B (subcontract):
  Rule-based — uses:
    - pitch_data JSON (compiled by PitchCompiler)
    - winner company profile (compacted optimized_profile)
    - RFP requirements extracted by RFPParser
  No LLM call. Fast and deterministic.

Usage:
    from documents.rfp_response.rfp_response_generator import RFPResponseGenerator

    gen = RFPResponseGenerator(project_root=str(PROJECT_ROOT))

    # Mode A — Prime
    sections = gen.generate_prime_sections(
        rfp_data=rfp_data,
        optimized_profile=winner_profile,
    )

    # Mode B — Subcontract (rule-based, no LLM)
    sections = gen.generate_subcontract_sections(
        rfp_data=rfp_data,
        pitch_data=pitch_data,
        winner_profile=winner_profile,
    )
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from documents.company_profile import (
    get_company_id,
    get_company_name,
    get_company_short_name,
)
from documents.rfp_response.response_planner import build_response_plan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts — adapted from BidForge's FINAL_DOCUMENT_PROMPT
#
# The prompt constants below use two kinds of placeholders:
#   - {{COMPANY_NAME}} / {{COMPANY_SHORT}} / {{DOCUMENT_PLAN}} — substituted at
#     call time via _render_template() with whatever company this deployment
#     is configured for (documents/company_profile.py) and the per-RFP plan
#     built by response_planner.build_response_plan(). These use a distinct
#     "{{...}}" token instead of single braces because these templates also
#     contain a literal JSON schema and are NOT passed through str.format().
#   - {agency}, {solicitation_number}, etc. — real str.format() placeholders,
#     used only in the *_USER_PROMPT_TEMPLATE constants below.
# ---------------------------------------------------------------------------


def _render_template(template: str, company_name: str, company_short: str, document_plan: str = "") -> str:
    """Substitutes the {{...}} tokens described above. Deliberately NOT
    str.format() — these templates contain literal JSON braces."""
    return (
        template
        .replace("{{COMPANY_NAME}}", company_name)
        .replace("{{COMPANY_SHORT}}", company_short)
        .replace("{{DOCUMENT_PLAN}}", document_plan)
    )


def _requirement_lines(rfp_data: dict[str, Any], limit: int = 20) -> tuple[str, str]:
    """Formats RFPParser's ACTUAL output fields (`requirements`,
    `compliance_requirements`) into prompt-ready text blocks.

    Replaces a previous lookup against rfp_data["identified_components"]
    ["technical"/"security"] — a key RFPParser has never produced (it emits
    `requirements`/`compliance_requirements`/`structural_elements` — see
    rfp_parser.py). That meant this block silently fell back to a generic
    placeholder ("See RFP documents.") for every single RFP regardless of
    what was actually extracted from the RFP text, both in the AI prompt
    and in the rule-based fallback path.
    """
    requirements = rfp_data.get("requirements") or []
    compliance = rfp_data.get("compliance_requirements") or []

    def _fmt_requirement(r: Any) -> str:
        if isinstance(r, dict):
            name = str(r.get("name") or "").strip()
            desc = str(r.get("description") or "").strip()
            extra = []
            if r.get("quantity"):
                extra.append(f"qty {r['quantity']}")
            if r.get("timeline"):
                extra.append(f"timeline {r['timeline']}")
            if r.get("source_clause"):
                extra.append(f"ref {r['source_clause']}")
            tail = f" ({', '.join(extra)})" if extra else ""
            if name and desc and name != desc:
                return f"  - {name}: {desc}{tail}"
            return f"  - {name or desc}{tail}"
        return f"  - {r}"

    technical_reqs = "\n".join(_fmt_requirement(r) for r in requirements[:limit]) or "  See RFP documents."
    security_reqs = (
        "\n".join(f"  - {c}" for c in compliance[:limit])
        or "  No explicit compliance/certification requirements were extracted — apply standard applicable requirements."
    )
    return technical_reqs, security_reqs


def _pricing_and_submission_text(rfp_data: dict[str, Any]) -> tuple[str, str]:
    """Derives pricing-structure and mandatory-submission text from
    RFPParser's `structural_elements` — the field that actually carries this
    information. Replaces a previous lookup against rfp_data["pricing_periods"]
    / rfp_data["submission_requirements"], keys RFPParser has never produced,
    which meant these blocks always silently fell back to placeholder text."""
    structural = [s for s in (rfp_data.get("structural_elements") or []) if isinstance(s, dict)]

    pricing_items = [s for s in structural if str(s.get("type", "")).lower() == "pricing_format"]
    if pricing_items:
        pricing_periods_text = "\n".join(
            f"  - {s.get('name', '')}: {s.get('description', '')}" for s in pricing_items
        )
    else:
        pricing_periods_text = (
            "  Not explicitly structured in the solicitation — propose pricing appropriate to the scope, "
            "or omit the pricing table if the RFP defers pricing to a separate submission."
        )

    submission_items = [
        s for s in structural
        if str(s.get("type", "")).lower() in (
            "submission_format", "bid_security", "mandatory_form", "annexure", "proforma", "form", "evaluation_criterion",
        )
    ]
    if submission_items:
        submission_requirements_text = "\n".join(
            f"  - [{s.get('type', '')}] {s.get('name', '')}: {s.get('description', '')}" for s in submission_items
        )
    else:
        submission_requirements_text = "  None explicitly extracted — rely on the requirements above."

    return pricing_periods_text, submission_requirements_text

_SYSTEM_PROMPT = """\
You are an expert proposal writer preparing a professional government RFP response on behalf of the
company described in "OUR COMPANY PROFILE" below.

Do not assume or assert any fixed industry specialty. Base every capability, technical, and solution claim
strictly on (a) the actual scope of work / requirements in this specific solicitation, and (b) the real
capabilities listed in the company profile provided to you. If the solicitation's required services fall
outside the company's usual specialty, respond honestly and specifically to what THIS solicitation asks
for — do not force an unrelated pitch, and do not editorialize about the mismatch anywhere in the output.

=======================================================
DOCUMENT PLAN — what belongs on each page/section, and how much
=======================================================
The section list below is the fixed OUTPUT SCHEMA (every document has these fields) — but HOW MUCH each
section says, whether the pricing table is populated at all, and which compliance items need an explicit
call-out is NOT fixed. It is determined per-solicitation from the plan below, built from what RFPParser
actually extracted from THIS RFP's text (its rfp_type, requirements, and structural_elements) — read it
before writing anything:

{{DOCUMENT_PLAN}}

Apply that plan to every section as you write it:

1. COVER / EXECUTIVE SUMMARY — sets the tone for the entire evaluation. Must state plainly: what is being
   proposed, to whom, why this offeror is qualified, and the core value proposition. An evaluator should be
   able to read only this section and understand the whole bid. Length follows the plan's complexity tier.
2. STRATEGIC CONTEXT + KEY HIGHLIGHTS — frames why this engagement matters to the agency's mission, then a
   scannable list of the single most compelling, decision-relevant facts (not generic marketing lines).
3. FINDINGS / REQUIREMENTS UNDERSTANDING — demonstrates genuine comprehension of the solicitation, one
   finding per distinct requirement theme actually extracted, each with supporting detail — this is where
   evaluators check whether the offeror actually read the SOW, not just template-filled it.
4. SCOPE OF WORK + DELIVERABLES — a complete, literal mapping of every deliverable the SOW/PWS implies.
   Missing a stated deliverable here is an automatic weakness in a real evaluation.
5. TECHNICAL APPROACH / PROPOSED SOLUTION + TECHNICAL ALIGNMENT — the methodology, staffing/execution
   approach, and an explicit requirement-by-requirement alignment table. This is normally the single most
   heavily weighted evaluation factor — treat it with matching depth.
6. CAPABILITIES / RELEVANT EXPERIENCE — only the services/capabilities from the company profile that are
   actually relevant to this scope, each with enough description to substantiate the claim.
7. TIMELINE / IMPLEMENTATION PLAN — a real phased plan (kickoff, execution milestones, delivery, closeout)
   with durations that add up to a coherent total, not placeholder phase names.
8. PRICING — follow the plan's PRICING instruction exactly (whether to include a table at all, and what
   structure to use) rather than defaulting to a generic price list.
9. TERMS, SLAs & COMPLIANCE — concrete commitments (response times, warranty period, reporting cadence).
   Explicitly cover any BID SECURITY / MANDATORY FORMS / SUBMISSION FORMAT / EVALUATION CRITERIA call-outs
   the plan lists — these are compliance-critical and must never be silently skipped.
10. PAST PERFORMANCE — real, relevant prior work only; never invented client names or projects.

Your output must be a JSON object with the following keys:
{
  "executive_summary": "<thorough executive summary — several full paragraphs covering what is proposed, to whom, why this offeror is qualified, and the core value proposition; do not compress a complex engagement into a couple of sentences>",
  "key_highlights": ["<one bullet per genuinely distinct, decision-relevant highlight — specific facts an evaluator would weigh, not generic marketing lines; do not pad or artificially cap; a complex RFP may justify 6-12>"],
  "strategic_context_intro": "<1-3 paragraphs framing why this engagement matters to the agency's actual mission/operations as described in the solicitation>",
  "findings": [
    {"title": "<a distinct requirement theme from the solicitation>", "body": "<demonstrates specific understanding of that requirement, referencing the solicitation's own language>", "bullets": ["<supporting specifics>", "..."]}
  ],
  "scope_intro": "<1-3 paragraph scope overview that maps directly onto the solicitation's own SOW/PWS structure>",
  "deliverables": ["<one entry per real deliverable implied anywhere in the requirements — treat a missing deliverable as a defect; list every one, not just a token few>"],
  "technical_alignment": [
    {"requirement": "<a specific, individually-stated requirement from the solicitation>", "solution": "<exactly how this offeror's approach satisfies it>", "alignment": "Full / Partial"}
  ],
  "proposed_solution": "<a full approach narrative, several paragraphs, covering methodology, staffing/execution approach, quality control, and how it satisfies the stated requirements in depth — this is normally the most heavily weighted section, treat it accordingly>",
  "capabilities": [{"name": "<a real capability/service from the company profile relevant to this scope>", "description": "<enough detail to substantiate the claim>"}],
  "tech_stack": ["<only include this field, and only list actual tools/equipment/technology relevant to THIS solicitation's scope — omit entirely if not applicable>"],
  "timeline_intro": "<1 paragraph intro framing the implementation approach — kickoff through closeout>",
  "phases": [
    {"phase": "<a real phase name matching this engagement's actual work breakdown>", "duration": "<realistic duration>", "focus": "<what happens in this phase>", "deliverables": "<what's delivered by the end of this phase>"}
  ],
  "total_duration": "<must equal the sum of the phase durations above, expressed to match the solicitation's own period-of-performance framing>",
  "investment_intro": "<1-2 paragraph intro to pricing, referencing the solicitation's own pricing structure if it defines one>",
  "pricing": [
    {"item": "...", "unit": "Fixed", "qty": "1", "unit_price": "$XX,XXX", "total": "$XX,XXX"}
  ],
  "sla_terms": ["<concrete commitments — response times, warranty period, reporting cadence — not vague reassurance>"],
  "past_performance": [
    {"project": "...", "client": "...", "period": "...", "relevance": "<specifically how this prior project relates to the current scope>"}
  ]
}

RULES:
- Write in a professional, formal government proposal tone.
- Ground every claim in the RFP requirements and the company profile provided — never in an assumed industry.
- Do NOT invent client names or fabricated references.
- Keep deliverables specific and actionable.
- The pricing table is optional — include if the RFP has pricing requirements, else use empty list.
- The array fields above ("findings", "deliverables", "technical_alignment", "capabilities", "phases",
  "sla_terms", "past_performance") are NOT capped at a fixed count. Generate one entry per distinct,
  substantive point the requirements and your solution genuinely support. A simple RFP may only justify
  a handful of items; a complex, multi-requirement solicitation should produce a proportionally thorough
  document. Do not pad with filler, and do not artificially truncate real content just to keep the
  document short — match the depth of a real federal proposal for a solicitation of this complexity.
- Highlight key metrics, vendor names, technical specifications, and critical requirements by wrapping them
  in double asterisks (e.g. **15% workshare**, real product/service names from the company profile, **NIST compliance**).
- Every field's value must be final, client-ready proposal prose only — never markdown headers (#, ##, ###),
  never meta-commentary about the RFP or about how you approached writing it, never internal analysis or
  reasoning. If it wouldn't belong in a printed proposal document, it does not belong in any field's value.
- Output ONLY valid JSON. No markdown, no preamble.
"""

_USER_PROMPT_TEMPLATE = """\
=======================================================
RFP DETAILS
=======================================================
Solicitation Number: {solicitation_number}
Issuing Agency:      {agency}
Project Title:       {project_title}
NAICS Code:          {naics}
Deadline:            {deadline}
Set-Aside:           {set_aside}

Requirements Summary:
{requirements_summary}

Technical Requirements:
{technical_reqs}

Security Requirements:
{security_reqs}

Pricing Periods / Line Items Defined By The Solicitation:
{pricing_periods}

Mandatory Submission Requirements (offeror must address these to be considered responsive):
{submission_requirements}

=======================================================
COMPETITOR / WINNER INTELLIGENCE
=======================================================
{competitor_profile}

=======================================================
OUR COMPANY PROFILE
=======================================================
{our_company_profile}

=======================================================
INSTRUCTIONS
=======================================================
Generate a complete, professional RFP response document on behalf of {company_name}.
Respond as the PRIME CONTRACTOR submitting directly to {agency}.
Use the RFP requirements to shape the scope of work and technical approach sections.
If "Pricing Periods / Line Items" above lists specific periods, the "pricing" array must contain exactly
one row per period listed, using its description/qty/unit. For unit_price/total: if a period's scope maps to
a service in the "Real Add-on/Premium Pricing" list in OUR COMPANY PROFILE, use that real starting price as
the basis and say so (e.g. "$25,000+ (per published rate card)"); otherwise use the literal string
"[TBD — pricing input required]" rather than inventing a number. If no periods are listed, use your judgment
on whether a pricing table is appropriate for this solicitation.
Explicitly address every item in "Mandatory Submission Requirements" somewhere in the proposal (e.g. in
findings, deliverables, or a dedicated note) — do not silently omit a compliance requirement the solicitation
states as mandatory, even if it's something we'd normally supply as a separate attachment (say so explicitly,
e.g. "Reference project details are provided as a separate attachment per the solicitation's instructions").
Use the competitor intelligence to position our solution effectively.
Return ONLY the JSON object described in the system prompt.
"""

_SUBCONTRACT_SYSTEM_PROMPT = """\
You are an expert proposal writer for {{COMPANY_NAME}}, a technology services company.
You are drafting a professional B2B subcontracting teaming proposal to a prime contractor who has won (or is bidding on) a government RFP.

{{COMPANY_NAME}} proposes to serve as a subcontractor, contributing a specific workshare percentage of the scope (typically 10-20%) centered around our technology products and capabilities.

Your output must be a JSON object with the following keys:
{
  "executive_summary": "<thorough multi-paragraph summary proposing a teaming partnership — do not compress artificially>",
  "key_highlights": ["<one bullet per genuinely distinct highlight — no fixed cap>"],
  "strategic_context_intro": "<1-2 paragraph framing the cooperative context between us and the prime>",
  "findings": [
    {"title": "...", "body": "...", "bullets": ["...", "..."]},
    {"title": "...", "body": "...", "bullets": ["...", "..."]},
    {"title": "...", "body": "...", "bullets": ["...", "..."]}
  ],
  "scope_intro": "<1-2 paragraph subcontract scope overview>",
  "deliverables": ["<list of subcontract deliverables>"],
  "technical_alignment": [
    {"requirement": "...", "solution": "...", "alignment": "Full / Partial"}
  ],
  "proposed_solution": "<a full narrative, several paragraphs, describing our matched product contribution and how it integrates with the prime's offering>",
  "capabilities": [{"name": "...", "description": "..."}],
  "tech_stack": ["Technology1", "Technology2"],
  "timeline_intro": "<1 paragraph timeline intro>",
  "phases": [
    {"phase": "Phase 1", "duration": "Week 1", "focus": "...", "deliverables": "..."}
  ],
  "total_duration": "8–10 Weeks",
  "investment_intro": "<1-2 paragraph investment intro (e.g. milestones, T&M or fixed pricing for our share)>",
  "pricing": [
    {"item": "...", "unit": "Fixed", "qty": "1", "unit_price": "$XX,XXX", "total": "$XX,XXX"}
  ],
  "sla_terms": ["<list of teaming SLA commitments>"],
  "past_performance": [
    {"project": "...", "client": "...", "period": "...", "relevance": "..."}
  ]
}

RULES:
- Write in a professional B2B teaming proposal tone.
- Address the prime contractor directly in the executive summary and strategic context.
- Keep deliverables specific and aligned with the subcontract workshare.
- Highlight key metrics, vendor names, technical specifications, and critical requirements by wrapping them
  in double asterisks (e.g. **15% workshare**, real product/service names from the company profile, **NIST compliance**).
- Do not artificially limit length or list sizes to keep the document short — generate content proportional to the real complexity of the opportunity; the document template supports any number of pages.
- Every field's value must be final, client-ready proposal prose only — never markdown headers (#, ##, ###),
  never meta-commentary, never internal analysis or reasoning.
- Output ONLY valid JSON. No markdown, no preamble.
"""

_SUBCONTRACT_USER_PROMPT_TEMPLATE = """\
=======================================================
RFP DETAILS
=======================================================
Solicitation Number: {solicitation_number}
Issuing Agency:      {agency}
Project Title:       {project_title}
NAICS Code:          {naics}

Requirements Summary:
{requirements_summary}

Technical Requirements:
{technical_reqs}

Security Requirements:
{security_reqs}

=======================================================
PRIME CONTRACTOR (WINNER) DETAILS
=======================================================
Prime Contractor: {prime_name}
Prime Profile:
{prime_profile}

=======================================================
OUR SUBCONTRACTOR PROFILE ({company_name})
=======================================================
Matched Product: {product_name} ({domain})
Our Profile:
{our_profile}

Our Matched Capabilities:
{matched_capabilities}

Proposed Work Share: {workshare_pct}%

=======================================================
INSTRUCTIONS
=======================================================
Generate a complete, highly detailed subcontracting proposal on behalf of {company_name} to {prime_name}.
Position our {product_name} product as the perfect technical contribution to {prime_name}'s team to meet {agency}'s requirements under Solicitation {solicitation_number}.
Return ONLY the JSON object described in the system prompt.
"""

_PARTNERSHIP_SYSTEM_PROMPT = """\
You are an expert business development director at {{COMPANY_NAME}}, a premier technology services and product development company.
You are drafting a professional B2B Partnership and Joint Value Proposition Proposal to a potential partner company.

{{COMPANY_NAME}} offers cutting-edge software engineering, custom technical solutions, and proprietary products —
use the real product/service names provided in OUR COMPANY PROFILE below, never invented ones.

Your goal is to propose a strategic collaboration between {{COMPANY_NAME}} and the target partner company, explaining how we can complement their business, what joint solutions we can offer, and the mutual value of this partnership.

Your output must be a JSON object with the following keys:
{
  "executive_summary": "<thorough multi-paragraph executive summary proposing a strategic partnership — do not compress artificially>",
  "key_highlights": ["<one bullet per genuinely distinct synergy — no fixed cap>"],
  "strategic_context_intro": "<1-2 paragraph framing the partnership vision and market opportunity>",
  "findings": [
    {"title": "...", "body": "...", "bullets": ["...", "..."]},
    {"title": "...", "body": "...", "bullets": ["...", "..."]}
  ],
  "scope_intro": "<1-2 paragraph detailing the proposed collaborative areas and joint services>",
  "deliverables": ["<list of joint offerings or cooperation milestones>"],
  "technical_alignment": [
    {"requirement": "Partner Capability Gap / Need", "solution": "{{COMPANY_SHORT}} Complementary Offering", "alignment": "Full Synergy"}
  ],
  "proposed_solution": "<a full narrative, several paragraphs, detailing the joint technology/service solution and value proposition>",
  "capabilities": [{"name": "...", "description": "..."}],
  "tech_stack": ["Technology1", "Technology2"],
  "timeline_intro": "<1 paragraph timeline/roadmap intro>",
  "phases": [
    {"phase": "Phase 1", "duration": "Month 1", "focus": "Initial Alignment & Joint Offering Definition", "deliverables": "..."}
  ],
  "total_duration": "3-6 Months (Phase 1)",
  "investment_intro": "<1-2 paragraph cost-sharing, resource-allocation, or revenue-sharing model overview>",
  "pricing": [
    {"item": "...", "unit": "Co-Investment / RevShare", "qty": "N/A", "unit_price": "N/A", "total": "N/A"}
  ],
  "sla_terms": ["<list of mutual cooperation guidelines and partner commitments>"],
  "past_performance": [
    {"project": "...", "client": "...", "period": "...", "relevance": "..."}
  ]
}

RULES:
- Write in a professional, persuasive B2B business development tone.
- Ground the value proposition in the target partner's profile and {{COMPANY_SHORT}}'s product capabilities.
- Do NOT invent fake client names. Use the actual name of {{COMPANY_NAME}} and the partner.
- Highlight key metrics, partner benefits, and synergistic capabilities by wrapping them in double asterisks
  (e.g. **increased market reach**, a real {{COMPANY_SHORT}} product name, **seamless API integration**).
- Do not artificially limit length or list sizes to keep the document short — generate content proportional to the real complexity of the opportunity; the document template supports any number of pages.
- Every field's value must be final, client-ready proposal prose only — never markdown headers (#, ##, ###),
  never meta-commentary, never internal analysis or reasoning.
- Output ONLY valid JSON. No markdown, no preamble.
"""

_PARTNERSHIP_USER_PROMPT_TEMPLATE = """\
=======================================================
OUR COMPANY PROFILE ({company_name})
=======================================================
Company Name: {company_name}
Our Profile:
{our_profile}

=======================================================
TARGET PARTNER COMPANY PROFILE
=======================================================
Partner Company: {partner_name}
Partner Profile:
{partner_profile}

=======================================================
INSTRUCTIONS
=======================================================
Generate a complete, highly detailed B2B Partnership and Joint Value Proposition Proposal between {company_name} and {partner_name}.
Analyze {partner_name}'s profile to identify capability gaps, synergies, or market opportunities where {company_short}'s products and services can deliver significant value.
Return ONLY the JSON object described in the system prompt.
"""



# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class RFPResponseGenerator:
    """
    Generates RFP response document sections for both modes.

    Mode A (prime):   LLM-powered via Ollama gemma4:31b-cloud
    Mode B (subcontract): Rule-based using pitch_data JSON
    """

    def __init__(self, project_root: str | None = None) -> None:
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parent.parent.parent
        self._our_profile: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_prime_sections(
        self,
        rfp_data: dict[str, Any],
        optimized_profile: dict[str, Any] | None = None,
        solicitation_number: str = "",
    ) -> dict[str, Any]:
        """
        Mode A — Prime contractor response.
        Uses Ollama LLM to generate all document sections.

        Args:
            rfp_data:           From RFPParser.parse_requirements()
            optimized_profile:  Compacted competitor/winner profile (OptimizedCompanyProfile)
            solicitation_number: RFP solicitation ID

        Returns:
            Dict of document sections ready for RFPResponsePDF.generate()
        """
        logger.info("[RFPResponseGen] Generating PRIME response sections")
        our_profile = self._load_our_profile()
        prompt = self._build_prime_prompt(rfp_data, optimized_profile, our_profile, solicitation_number)

        # Build the per-RFP plan (rfp_type/complexity/pricing/compliance call-outs)
        # from what RFPParser actually extracted, instead of applying the same
        # fixed instructions to every solicitation. Logged so it's visible which
        # plan drove a given generated document.
        plan = build_response_plan(rfp_data)
        logger.info(
            f"[RFPResponseGen] Response plan: rfp_type={plan['rfp_type']} complexity={plan['complexity']} "
            f"requirements={plan['requirement_count']} pricing_table={plan['include_pricing_table']}"
        )

        from pipeline.ai.mode import run_with_fallback
        sections, path_used = run_with_fallback(
            "rfp_response",
            ai_fn=lambda: self._call_ollama(prompt, plan) or (_ for _ in ()).throw(RuntimeError("empty AI response")),
            rule_fn=lambda: self._build_prime_sections_rules(rfp_data, optimized_profile, our_profile),
        )
        logger.info(f"[RFPResponseGen] PRIME sections generated via '{path_used}' path.")
        return self._validate_and_fill_defaults(sections, rfp_data)

    def generate_subcontract_sections(
        self,
        rfp_data: dict[str, Any],
        pitch_data: dict[str, Any],
        winner_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Mode B — Subcontract teaming proposal.
        LLM-powered by default (Ollama gemma4:31b-cloud) with a programmatic rule-based fallback.
        """
        logger.info("[RFPResponseGen] Generating SUBCONTRACT sections")
        our_profile = self._load_our_profile()
        prompt = self._build_subcontract_prompt(rfp_data, pitch_data, winner_profile, our_profile)

        from pipeline.ai.mode import run_with_fallback

        def _ai_fn():
            result = self._call_ollama_subcontract(prompt)
            if not result:
                raise RuntimeError("empty AI response")
            return result

        sections, path_used = run_with_fallback(
            "rfp_response",
            ai_fn=_ai_fn,
            rule_fn=lambda: self._build_subcontract_sections(rfp_data, pitch_data, winner_profile),
        )
        logger.info(f"[RFPResponseGen] SUBCONTRACT sections generated via '{path_used}' path.")
        if path_used == "rule_based":
            return sections  # already fully-formed from _build_subcontract_sections
        return self._validate_and_fill_defaults(sections, rfp_data)

    def generate_partnership_sections(
        self,
        partner_profile: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Mode C — B2B Partnership and Joint Value Proposition.
        LLM-powered via Ollama gemma4:31b-cloud.
        """
        logger.info("[RFPResponseGen] Generating B2B PARTNERSHIP sections")
        our_profile = self._load_our_profile()
        prompt = self._build_partnership_prompt(partner_profile, our_profile)
        dummy_rfp = {"metadata": {"issuing_agency": partner_profile.get("company_name", "Target Partner")}}

        from pipeline.ai.mode import run_with_fallback

        def _ai_fn():
            result = self._call_ollama_partnership(prompt)
            if not result:
                raise RuntimeError("empty AI response")
            return result

        sections, path_used = run_with_fallback(
            "rfp_response",
            ai_fn=_ai_fn,
            rule_fn=lambda: self._build_partnership_sections_rules(partner_profile, our_profile),
        )
        logger.info(f"[RFPResponseGen] PARTNERSHIP sections generated via '{path_used}' path.")
        return self._validate_and_fill_defaults(sections, dummy_rfp)

    def _build_subcontract_prompt(
        self,
        rfp_data: dict[str, Any],
        pitch_data: dict[str, Any],
        winner_profile: dict[str, Any] | None,
        our_profile: dict[str, Any]
    ) -> str:
        meta = rfp_data.get("metadata", {})

        technical_reqs, security_reqs = _requirement_lines(rfp_data, limit=15)

        requirements_summary = rfp_data.get("summary", "") or "See technical and security requirements above."

        # Prime winner profile summary
        prime_name = winner_profile.get("company_name") if winner_profile else None
        if not prime_name:
            prime_name = pitch_data.get("prime_contractor", {}).get("company_name", "Prime Contractor")

        prime_summary = ""
        if winner_profile:
            prime_summary = (
                f"Company: {prime_name}\n"
                f"Products: {', '.join((winner_profile.get('products') or [])[:5])}\n"
                f"Services: {', '.join((winner_profile.get('services') or [])[:5])}\n"
                f"Industry: {winner_profile.get('industry', '')}\n"
                f"RFP Strengths: {', '.join((winner_profile.get('rfp_strengths') or [])[:4])}\n"
            )
        if not prime_summary:
            prime_summary = f"Company Name: {prime_name}"

        # Subcontractor profile summary
        sub = pitch_data.get("subcontractor", {})
        product_name = sub.get("product_name", "our technology platform")
        domain = sub.get("industry_domain", "technology services")

        tech_list = self._get_flat_tech_stack(our_profile)
        company_name = get_company_name()
        our_summary = (
            f"Company: {company_name}\n"
            f"Products: {', '.join((our_profile.get('products', []))[:6])}\n"
            f"Services: {', '.join((our_profile.get('services', []))[:6])}\n"
            f"Tech Stack: {', '.join(tech_list[:8])}\n"
            f"Certifications: {', '.join((our_profile.get('certifications', []))[:4])}\n"
        )

        # Matched capabilities alignment summary
        alignments = pitch_data.get("alignment_matrices", {})
        tech_aligns = alignments.get("technical_capabilities", [])
        sec_aligns = alignments.get("security_compliance", [])

        matched_caps = ""
        for t in tech_aligns[:5]:
            matched_caps += f"  - Requirement: {t.get('rfp_required_capability')}\n    Our Matched Capability: {t.get('our_matched_capability')}\n    Description: {t.get('how_it_aligns')}\n"
        for s in sec_aligns[:5]:
            matched_caps += f"  - Security Requirement: {s.get('rfp_security_requirement')}\n    Our Matched Standard: {s.get('our_matched_standard')}\n    Description: {s.get('how_it_aligns')}\n"

        workshare = pitch_data.get("proposal_settings", {}).get("proposed_workshare_pct", 15.0)

        return _SUBCONTRACT_USER_PROMPT_TEMPLATE.format(
            solicitation_number=meta.get("solicitation_number", "N/A"),
            agency=meta.get("issuing_agency", "Federal Agency"),
            project_title=meta.get("project_title", "Technology Services"),
            naics=meta.get("naics_code", "541511"),
            requirements_summary=requirements_summary,
            technical_reqs=technical_reqs,
            security_reqs=security_reqs,
            prime_name=prime_name,
            prime_profile=prime_summary,
            product_name=product_name,
            domain=domain,
            our_profile=our_summary,
            matched_capabilities=matched_caps,
            workshare_pct=workshare,
            company_name=company_name,
            company_short=get_company_short_name(),
        )

    def _call_ollama_subcontract(self, user_prompt: str) -> dict[str, Any]:
        """Calls the shared Ollama Cloud client using the subcontract system prompt."""
        from pipeline.ai.client import get_ai_client
        system_prompt = _render_template(_SUBCONTRACT_SYSTEM_PROMPT, get_company_name(), get_company_short_name())
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            return get_ai_client().chat_json(messages)
        except Exception as exc:
            logger.warning(f"[RFPResponseGen] AI subcontract generation failed: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Mode A — LLM
    # ------------------------------------------------------------------

    def _build_prime_prompt(
        self,
        rfp_data: dict[str, Any],
        competitor_profile: dict[str, Any] | None,
        our_profile: dict[str, Any],
        solicitation_number: str,
    ) -> str:
        """Build the user-facing prompt for Ollama."""
        meta = rfp_data.get("metadata", {})

        technical_reqs, security_reqs = _requirement_lines(rfp_data, limit=20)

        # Summarize requirements text — rfp_data["summary"] is the parser's actual
        # plain-English description of what's being solicited; requirements_text
        # was never populated by the parser, so this previously always fell back
        # to a placeholder and the AI never saw what was actually being requested.
        requirements_summary = rfp_data.get("summary") or rfp_data.get("requirements_text") or "See technical and security requirements above."

        pricing_periods_text, submission_requirements_text = _pricing_and_submission_text(rfp_data)

        # Summarize competitor profile
        comp_summary = ""
        if competitor_profile:
            comp_summary = (
                f"Winner/Prime: {competitor_profile.get('company_name', 'Unknown')}\n"
                f"Products: {', '.join((competitor_profile.get('products') or [])[:5])}\n"
                f"Services: {', '.join((competitor_profile.get('services') or [])[:5])}\n"
                f"Industry: {competitor_profile.get('industry', '')}\n"
                f"RFP Strengths: {', '.join((competitor_profile.get('rfp_strengths') or [])[:4])}\n"
                f"Competitors: {', '.join((competitor_profile.get('competitors') or [])[:4])}\n"
            )
        if not comp_summary:
            comp_summary = "No competitor profile available."

        # Our profile summary — full real catalog (services + descriptions + real
        # add-on pricing), not a truncated name-only list, so the AI can select
        # genuinely relevant, real services/prices instead of inventing generic ones.
        tech_list = self._get_flat_tech_stack(our_profile)
        catalog_detail = our_profile.get("catalog_detail") or []
        if catalog_detail:
            by_category: dict[str, list[str]] = {}
            for item in catalog_detail:
                by_category.setdefault(item.get("category", "General"), []).append(
                    f"{item.get('service_name', '')} — {item.get('description', '')}"
                )
            catalog_lines = []
            for cat, lines in by_category.items():
                catalog_lines.append(f"{cat}:")
                catalog_lines.extend(f"  - {l}" for l in lines)
            services_block = "\n".join(catalog_lines)
        else:
            services_block = ", ".join((our_profile.get("services", []))[:20]) or "See services list."

        addon_pricing = our_profile.get("addon_pricing") or []
        addon_block = (
            "\n".join(f"  - {a.get('service_name', '')}: {a.get('price', '')}" for a in addon_pricing[:25])
            if addon_pricing
            else "  No premium add-on pricing on file — use investment_intro to note pricing will follow a discovery call."
        )

        our_summary = (
            f"Company: {get_company_name()}\n"
            f"NAICS Codes: {', '.join(our_profile.get('naics_codes', []) or ['541511'])}\n"
            f"Full Service Catalog (select only what's genuinely relevant to this solicitation):\n{services_block}\n\n"
            f"Real Add-on/Premium Pricing (use as anchors — never invent numbers not derivable from these):\n{addon_block}\n\n"
            f"Tech Stack: {', '.join(tech_list[:12]) if tech_list else 'See service catalog above.'}\n"
            f"Certifications: {', '.join((our_profile.get('certifications', []))[:6]) or 'See past performance.'}\n"
        )

        return _USER_PROMPT_TEMPLATE.format(
            solicitation_number=solicitation_number or meta.get("solicitation_number", "N/A"),
            agency=meta.get("issuing_agency", "Issuing Agency"),
            project_title=meta.get("project_title", "Technology Services"),
            naics=meta.get("naics_code", "541511"),
            deadline=meta.get("deadline", "N/A"),
            set_aside=meta.get("set_aside", "N/A"),
            requirements_summary=requirements_summary,
            technical_reqs=technical_reqs,
            security_reqs=security_reqs,
            pricing_periods=pricing_periods_text,
            submission_requirements=submission_requirements_text,
            competitor_profile=comp_summary,
            our_company_profile=our_summary,
            company_name=get_company_name(),
        )

    def _call_ollama(self, user_prompt: str, plan: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call the shared Ollama Cloud client and parse the JSON response.

        `plan` is the per-RFP plan from response_planner.build_response_plan()
        -- its plan_text is substituted into the system prompt's DOCUMENT PLAN
        block so section depth/pricing/compliance guidance is tailored to
        THIS solicitation instead of the old fixed instructions.
        """
        from pipeline.ai.client import get_ai_client
        document_plan = (plan or {}).get("plan_text", "") or "- No structured RFP plan available; use judgment scaled to the requirements provided below."
        system_prompt = _render_template(_SYSTEM_PROMPT, get_company_name(), get_company_short_name(), document_plan)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            return get_ai_client().chat_json(messages)
        except Exception as exc:
            logger.error(f"[RFPResponseGen] AI prime generation failed: {exc}")
            return {}

    def _parse_json(self, text: str) -> dict[str, Any]:
        """Parse JSON from Ollama response, stripping markdown fences if present."""
        text = text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            match = re.search(r"(\{.*\})", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
        logger.warning("[RFPResponseGen] Could not parse LLM JSON response.")
        return {}

    # ------------------------------------------------------------------
    # Mode B — Rule-based subcontract sections builder
    # ------------------------------------------------------------------

    def _build_subcontract_sections(
        self,
        rfp_data: dict[str, Any],
        pitch_data: dict[str, Any],
        winner_profile: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Builds all document sections deterministically from structured data.
        No LLM required.
        """
        meta         = rfp_data.get("metadata", {})
        prime        = pitch_data.get("prime_contractor", {})
        sub          = pitch_data.get("subcontractor", {})
        alignments   = pitch_data.get("alignment_matrices", {})
        settings_p   = pitch_data.get("proposal_settings", {})
        outreach     = pitch_data.get("pitch_outreach", {})

        company_name = get_company_name()
        company_short = get_company_short_name()
        agency_name    = meta.get("issuing_agency", "the issuing agency")
        project_title  = meta.get("project_title", "IT Services")
        prime_name     = prime.get("company_name", "Prime Contractor")
        workshare_pct  = settings_p.get("proposed_workshare_pct", 15.0)
        product_name   = sub.get("product_name", "our technology platform")
        domain         = sub.get("industry_domain", "technology services")

        # Executive summary
        executive_summary = (
            f"{company_name} is pleased to present this formal subcontracting teaming proposal to "
            f"{prime_name} in response to Solicitation {meta.get('solicitation_number', '')} issued by "
            f"{agency_name}.\n\n"
            f"We propose to serve as a key subcontractor, contributing {workshare_pct}% of the total "
            f"contract scope, with a specific focus on {domain}. Our {product_name} platform directly "
            f"addresses the core technical and operational requirements outlined in the solicitation.\n\n"
            f"{company_name} brings extensive experience in enterprise software delivery, cloud-native "
            f"architectures, and government-facing digital transformation initiatives. We are positioned to "
            f"add measurable value to {prime_name}'s delivery capability for this engagement."
        )

        key_highlights = [
            f"Proposed work share: {workshare_pct}% of total contract value",
            f"Core offering: {product_name} for {domain}",
            "Demonstrated track record in enterprise digital transformation",
            "Cloud-native, security-compliant architecture",
            "Experienced delivery team with government sector expertise",
            "Committed to on-time, on-budget delivery with SLA guarantees",
        ]

        # Strategic context findings — pulled from RFPParser's actual `requirements`
        # and `compliance_requirements` fields (see _requirement_lines' docstring
        # for why this used to silently fall back to placeholder text instead).
        technical_reqs_text, security_reqs_text = _requirement_lines(rfp_data, limit=6)
        tech_reqs = [l.lstrip("- ").strip() for l in technical_reqs_text.splitlines() if l.strip() and l.strip() != "See RFP documents."][:6]
        sec_reqs = [l.lstrip("- ").strip() for l in security_reqs_text.splitlines() if l.strip() and "No explicit" not in l][:4]
        findings = [
            {
                "title": f"{agency_name} requires specialized technology capabilities",
                "body": (
                    f"The solicitation from {agency_name} outlines a comprehensive set of technical "
                    f"and operational requirements that demand deep domain expertise in {domain}. "
                    f"{prime_name}, as the prime contractor, can significantly strengthen its delivery "
                    f"capability by partnering with {company_name}."
                ),
                "bullets": tech_reqs or [
                    "Enterprise-grade software development",
                    "Cloud-native and scalable architecture",
                    "Compliance and security standards alignment",
                ],
            },
            {
                "title": f"{company_short}'s capabilities directly address the solicitation requirements",
                "body": (
                    f"Our {product_name} platform and delivery framework have been purpose-built for "
                    f"engagements of this type. We bring proven methodologies, reusable components, "
                    f"and a track record of successful delivery in similar government and enterprise contexts."
                ),
                "bullets": [
                    f"Direct alignment with: {', '.join(tech_reqs[:3])}" if tech_reqs else
                    "Full technical requirements alignment",
                    "Rapid onboarding and integration with prime contractor processes",
                    "Dedicated program management and technical leadership",
                ],
            },
            {
                "title": "Structured delivery minimizes risk and ensures compliance",
                "body": (
                    "Our phased delivery approach, milestone-based tracking, and robust quality assurance "
                    "processes ensure that all deliverables meet the standards expected by the government "
                    "agency and the prime contractor."
                ),
                "bullets": sec_reqs or [
                    "Security and compliance standards met from Day 1",
                    "Regular reporting and milestone reviews",
                    "Dedicated QA and UAT support",
                ],
            },
        ]

        # Scope of work from alignment matrices
        tech_cap_alignments = alignments.get("technical_capabilities", [])
        sec_alignments      = alignments.get("security_compliance", [])
        work_breakdown      = alignments.get("subcontractor_work_share_breakdown", [])

        deliverables = (
            [t.get("rfp_required_capability", "") for t in tech_cap_alignments if t.get("rfp_required_capability")]
            or ["Enterprise application development", "System integration", "Testing & QA", "Technical documentation"]
        )

        technical_alignment = [
            {
                "requirement": t.get("rfp_required_capability", ""),
                "solution":    t.get("our_matched_capability", ""),
                "alignment":   "✓ Full",
            }
            for t in tech_cap_alignments[:8]
        ] + [
            {
                "requirement": s.get("rfp_security_requirement", ""),
                "solution":    s.get("our_matched_standard", ""),
                "alignment":   "✓ Full",
            }
            for s in sec_alignments[:4]
        ]

        # Proposed solution
        proposed_solution = (
            f"{company_name} proposes to deliver the {product_name} as our core contribution "
            f"to the {prime_name} team for the {project_title} engagement.\n\n"
            f"Our platform is built on a modern, cloud-native architecture designed for the "
            f"scale, security, and compliance requirements of government and enterprise engagements. "
            f"It integrates seamlessly with existing infrastructure and can be rapidly deployed "
            f"within the timeline requirements of this solicitation.\n\n"
            f"The solution leverages industry-leading technologies and best practices, ensuring "
            f"full alignment with the technical and operational requirements outlined in {meta.get('solicitation_number', 'the RFP')}."
        )

        our_profile = self._load_our_profile()
        tech_list = self._get_flat_tech_stack(our_profile)
        tech_stack = tech_list[:8] if tech_list else [
            "React", "Node.js", "Python", "AWS", "Azure", "PostgreSQL",
            "Docker", "Kubernetes"
        ]

        capabilities = (
            [{"name": t.get("rfp_required_capability", ""), "description": t.get("how_it_aligns", "")}
             for t in tech_cap_alignments[:6]]
            or [
                {"name": "Enterprise Software Development", "description": "Full-stack application development using modern frameworks"},
                {"name": "Cloud Architecture",              "description": "Scalable, secure cloud-native infrastructure design and implementation"},
                {"name": "System Integration",              "description": "API design, middleware, and third-party system integration"},
                {"name": "QA & Testing",                    "description": "Automated testing, UAT support, and performance validation"},
            ]
        )

        # Timeline from work breakdown
        phases = []
        for task in (work_breakdown[:6] or []):
            phases.append({
                "phase":       f"Task: {task.get('task', '')}",
                "duration":    f"{task.get('proposed_share', 15)}% scope",
                "focus":       task.get("task", ""),
                "deliverables": task.get("deliverables", ""),
            })
        if not phases:
            phases = [
                {"phase": "Phase 1", "duration": "Week 1",   "focus": "Onboarding & Requirements Review",  "deliverables": "Kickoff report, requirements matrix"},
                {"phase": "Phase 2", "duration": "Week 2–3", "focus": "Architecture & Design",             "deliverables": "System design document, UI/UX prototypes"},
                {"phase": "Phase 3", "duration": "Week 4–7", "focus": "Development & Integration",         "deliverables": "Working software modules, API integrations"},
                {"phase": "Phase 4", "duration": "Week 8",   "focus": "Testing & Quality Assurance",       "deliverables": "Test reports, defect log, UAT sign-off"},
                {"phase": "Phase 5", "duration": "Week 9",   "focus": "Deployment & Handover",             "deliverables": "Deployed solution, documentation, training"},
            ]

        # Investment — for subcontract, no exact pricing, just workshare
        investment_intro = (
            f"{company_name} proposes to assume {workshare_pct}% of the total contract value "
            f"as our subcontract work share under {prime_name}'s prime contract. "
            f"Our pricing is competitive, transparent, and structured to ensure maximum value "
            f"delivery within the contract budget framework."
        )

        sla_terms = [
            "100% milestone-based delivery with written sign-offs at each phase",
            "Response time SLA: 4-hour initial response for critical issues during delivery",
            "90-day post-deployment warranty and bug-fix commitment at no additional cost",
            "Dedicated project manager and technical lead throughout engagement",
            "Weekly progress reports and bi-weekly steering committee updates",
            "All deliverables subject to acceptance testing prior to payment milestone",
        ]

        return {
            "executive_summary":      executive_summary,
            "key_highlights":         key_highlights,
            "strategic_context_intro": (
                f"This teaming proposal outlines {company_name}'s qualifications and commitment "
                f"to supporting {prime_name} in delivering a successful outcome for {agency_name} "
                f"under Solicitation {meta.get('solicitation_number', '')}."
            ),
            "findings":               findings,
            "scope_intro":            (
                f"As the proposed subcontractor for this engagement, {company_name} will be "
                f"responsible for delivering the following scope of work as part of the prime team:"
            ),
            "deliverables":           deliverables,
            "technical_alignment":    technical_alignment,
            "proposed_solution":      proposed_solution,
            "capabilities":           capabilities,
            "tech_stack":             tech_stack,
            "timeline_intro":         (
                f"The following phased delivery plan reflects {company_short}'s structured approach "
                f"to executing our {workshare_pct}% work share within the prime contractor's "
                f"overall project timeline."
            ),
            "phases":                 phases,
            "total_duration":         "8–10 Weeks",
            "investment_intro":       investment_intro,
            "pricing":                [],  # no itemized pricing in subcontract mode
            "sla_terms":              sla_terms,
            "workshare_pct":          workshare_pct,
            "past_performance":       self._load_past_performance(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_partnership_prompt(
        self,
        partner_profile: dict[str, Any],
        our_profile: dict[str, Any]
    ) -> str:
        partner_name = partner_profile.get("company_name", "Target Partner")
        
        # Format partner profile summary
        products = partner_profile.get("products") or []
        services = partner_profile.get("services") or []
        partner_summary = (
            f"Company Name: {partner_name}\n"
            f"Products: {', '.join(products[:6]) if isinstance(products, list) else products}\n"
            f"Services: {', '.join(services[:6]) if isinstance(services, list) else services}\n"
            f"Industry: {partner_profile.get('industry', 'Technology/Services')}\n"
            f"About: {partner_profile.get('about', '')}\n"
            f"Business Model: {partner_profile.get('business_model', '')}\n"
        )
        
        # Format our profile summary
        tech_list = self._get_flat_tech_stack(our_profile)
        our_products = our_profile.get("products") or []
        our_services = our_profile.get("services") or []
        our_certs = our_profile.get("certifications") or []
        our_summary = (
            f"Company: {get_company_name()}\n"
            f"Products: {', '.join(our_products[:6]) if isinstance(our_products, list) else our_products}\n"
            f"Services: {', '.join(our_services[:6]) if isinstance(our_services, list) else our_services}\n"
            f"Tech Stack: {', '.join(tech_list[:8])}\n"
            f"Certifications: {', '.join(our_certs[:4]) if isinstance(our_certs, list) else our_certs}\n"
            f"About: {our_profile.get('about', '')}\n"
        )
        
        return _PARTNERSHIP_USER_PROMPT_TEMPLATE.format(
            partner_name=partner_name,
            partner_profile=partner_summary,
            our_profile=our_summary,
            company_name=get_company_name(),
            company_short=get_company_short_name(),
        )

    def _call_ollama_partnership(self, user_prompt: str) -> dict[str, Any]:
        """Calls the shared Ollama Cloud client using the B2B partnership system prompt."""
        from pipeline.ai.client import get_ai_client
        system_prompt = _render_template(_PARTNERSHIP_SYSTEM_PROMPT, get_company_name(), get_company_short_name())
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return get_ai_client().chat_json(messages)

    def _load_our_profile(self) -> dict[str, Any]:
        """Load this deployment's own company profile. Priority order:
        1. private/active_bidding_company.json (dynamically selected bidding profile)
        2. MongoDB `own_company_profile` collection — the live, DB-editable source
           of truth (Settings > Company Profile), highest priority for real data
        3. app.core.company_catalog (services/pricing, itself Mongo-backed)
        4. private/<company_id>_detailed_profiles.json (static seed/backup)
        5. A generic placeholder, only if none of the above have anything.
        """
        if self._our_profile is not None:
            return self._our_profile or {}

        # Load dynamically selected bidding profile if present
        active_bidding_path = self.project_root / "private" / "active_bidding_company.json"
        if active_bidding_path.exists():
            try:
                with open(active_bidding_path, encoding="utf-8") as f:
                    self._our_profile = json.load(f)
                    logger.info("[RFPResponseGen] Loaded active bidding company profile from active_bidding_company.json")
                    return self._our_profile or {}
            except Exception as exc:
                logger.warning(f"[RFPResponseGen] Could not load active bidding profile: {exc}")

        profile: dict[str, Any] = {}

        # First, try fetching user's saved company profile from MongoDB
        try:
            from utils.db_client import get_collection
            col = get_collection("own_company_profile")
            db_profile = col.find_one({}, {"_id": 0})
            if db_profile:
                profile.update(db_profile)
                logger.info("[RFPResponseGen] Loaded company profile from MongoDB own_company_profile collection.")
        except Exception as exc:
            logger.debug(f"[RFPResponseGen] MongoDB own_company_profile fetch note: {exc}")

        try:
            from app.core.company_catalog import load_services_catalog
            catalog = load_services_catalog()
            services = catalog.get("services") or []
            addons = catalog.get("addons") or []
            if services:
                profile["services"] = sorted({s["service_name"] for s in services})
                profile["service_categories"] = sorted(catalog.get("categories", {}).keys())
                profile["naics_codes"] = sorted({s["naics_code"] for s in services if s.get("naics_code")})
                profile["catalog_detail"] = services  # full {category, service_name, description} rows
                profile["addon_pricing"] = addons
                logger.info(f"[RFPResponseGen] Loaded {len(services)} real catalog services for company profile.")
        except Exception as exc:
            logger.warning(f"[RFPResponseGen] Could not load company catalog: {exc}")

        profile_path = self.project_root / "private" / f"{get_company_id()}_detailed_profiles.json"
        if not profile_path.exists():
            # Backward-compat: keep reading the old fixed filename too, so
            # existing OrbitAvanya deployments don't need to rename a file.
            legacy_path = self.project_root / "private" / "orbit_avanya_detailed_profiles.json"
            if legacy_path.exists():
                profile_path = legacy_path
        if profile_path.exists():
            try:
                with open(profile_path, encoding="utf-8") as f:
                    raw_data = json.load(f)
                    if isinstance(raw_data, list) and raw_data:
                        raw_data = raw_data[0]
                    if isinstance(raw_data, dict):
                        # Layer JSON profile fields (certifications, past_performance, etc.)
                        # on top without overwriting the real catalog-derived services list.
                        for k, v in raw_data.items():
                            profile.setdefault(k, v)
                        logger.info("[RFPResponseGen] Layered additional profile fields from private/ JSON.")
            except Exception as exc:
                logger.warning(f"[RFPResponseGen] Could not load own profile JSON: {exc}")

        if not profile.get("services"):
            # Only reached if BOTH the MongoDB own_company_profile document AND
            # the company_catalog are completely unavailable — i.e. this
            # deployment hasn't been configured with real company data yet.
            # This stub is intentionally generic (no invented product names)
            # so it's obviously a placeholder rather than looking like a real
            # company profile if it ever surfaces in output.
            logger.warning(
                "[RFPResponseGen] No company profile found in MongoDB own_company_profile or the "
                "services catalog — using a generic placeholder. Configure Settings > Company Profile "
                "(or seed own_company_profile / run scripts/import_company_catalog.py) for real output."
            )
            profile.update({
                "products":         [f"{get_company_short_name()} Platform"],
                "services":         ["Enterprise Software Development", "Cloud Architecture", "AI/ML Solutions",
                                     "System Integration", "DevOps & CI/CD"],
                "technology_stack": ["React", "Node.js", "Python", "FastAPI", "PostgreSQL", "AWS", "Docker"],
                "certifications":   [],
            })

        self._our_profile = profile
        return profile

    def _get_flat_tech_stack(self, profile: dict[str, Any]) -> list[str]:
        """Helper to flatten the tech stack if it is a dictionary, or return the list."""
        ts = profile.get("technology_stack")
        if not ts:
            return []
        if isinstance(ts, list):
            return ts
        if isinstance(ts, dict):
            flat = []
            for category, items in ts.items():
                if isinstance(items, list):
                    flat.extend(items)
                elif isinstance(items, str):
                    flat.append(items)
            return flat
        return []

    def _load_past_performance(self) -> list[dict[str, str]]:
        """Load past performance records from private/ or return defaults."""
        profile = self._load_our_profile()
        pp = profile.get("past_performance", [])
        if pp:
            return pp[:5]
        # Defaults from the DOCX template content
        return [
            {
                "project":   "Contractor Management System (CMS)",
                "client":    "Irrigation Department",
                "period":    "Sep 2024",
                "relevance": "Full-stack government e-governance platform development",
            },
            {
                "project":   "Enterprise Data Platform",
                "client":    "Confidential (Government)",
                "period":    "2024",
                "relevance": "Cloud-native data warehouse and analytics dashboard",
            },
        ]

    def _validate_and_fill_defaults(
        self, sections: dict[str, Any], rfp_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Ensure all required section keys exist with sensible, domain-neutral
        defaults, and strip any leaked markdown headers / meta-commentary from
        every string value regardless of whether the AI followed the prompt."""
        meta = rfp_data.get("metadata", {})
        project_title = meta.get("project_title", "the solicited scope of work")
        company_name = get_company_name()

        defaults = {
            "executive_summary":      f"{company_name} is pleased to submit this response to {meta.get('issuing_agency', 'the issuing agency')}.",
            "key_highlights":         [],
            "strategic_context_intro": "This proposal addresses the core requirements of the solicitation.",
            "findings":               [
                {"title": "Requirements alignment", "body": f"Our proposed approach directly addresses the requirements of {project_title}.", "bullets": []},
            ],
            "scope_intro":            "The following scope of work describes our proposed deliverables.",
            "deliverables":           [],
            "technical_alignment":    [],
            "proposed_solution":      f"{company_name} proposes a comprehensive approach addressing all stated requirements of {project_title}.",
            "capabilities":           [],
            "tech_stack":             [],
            "timeline_intro":         "The following phased plan outlines our implementation approach.",
            "phases":                 [],
            "total_duration":         "Per solicitation period of performance",
            "investment_intro":       "Our pricing is competitive and structured to deliver maximum value.",
            "pricing":                [],
            "sla_terms":              ["Weekly status reporting", "Dedicated project manager"],
            "past_performance":       self._load_past_performance(),
        }

        for key, default in defaults.items():
            if not sections.get(key):
                sections[key] = default

        return self._sanitize_sections(sections)

    def _sanitize_sections(self, sections: dict[str, Any]) -> dict[str, Any]:
        """Recursively strips markdown headers/code fences that occasionally leak
        into an otherwise-valid JSON string value (the AI puts prose where it
        should put only plain text — this is a content-quality defense, not a
        JSON-parsing fix, since the JSON itself parses fine in that case)."""

        def _clean_str(s: str) -> str:
            if not isinstance(s, str):
                return s
            # Strip markdown code fences
            s = re.sub(r"```(?:json|markdown)?\s*", "", s)
            s = s.replace("```", "")
            # Strip leading markdown headers on their own line (#, ##, ### ...)
            s = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", s)
            return s.strip()

        def _walk(value: Any) -> Any:
            if isinstance(value, str):
                return _clean_str(value)
            if isinstance(value, list):
                return [_walk(v) for v in value]
            if isinstance(value, dict):
                return {k: _walk(v) for k, v in value.items()}
            return value

        return {k: _walk(v) for k, v in sections.items()}


    # ------------------------------------------------------------------
    # Rule-based fallback builders (used when AI call fails / is disabled)
    # ------------------------------------------------------------------

    def _build_prime_sections_rules(
        self,
        rfp_data: dict[str, Any],
        optimized_profile: dict[str, Any] | None,
        our_profile: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build a structured prime-contractor proposal deterministically from
        RFP data and the company profile — used when the LLM call fails.
        """
        meta = rfp_data.get("metadata", {})
        agency = meta.get("issuing_agency", "the issuing agency")
        sol_num = meta.get("solicitation_number", "")
        title = meta.get("project_title", "Technical Proposal")
        naics = meta.get("naics", "")
        deadline = meta.get("deadline", "Per RFP instructions")

        company_name = get_company_name()
        company_short = get_company_short_name()

        # Pulled from RFPParser's actual `requirements`/`compliance_requirements`
        # fields — see _requirement_lines' docstring for why this used to
        # silently fall back to placeholder text for every RFP.
        technical_reqs_text, security_reqs_text = _requirement_lines(rfp_data, limit=8)
        tech_reqs = [l.lstrip("- ").strip() for l in technical_reqs_text.splitlines() if l.strip() and l.strip() != "See RFP documents."]
        security_reqs = [l.lstrip("- ").strip() for l in security_reqs_text.splitlines() if l.strip() and "No explicit" not in l][:5]

        services = our_profile.get("services", ["Enterprise Software Development", "Cloud Architecture", "AI/ML Solutions"])
        products = our_profile.get("products", [f"{company_short} Platform"])
        tech_stack = self._get_flat_tech_stack(our_profile)[:10] or ["React", "Node.js", "Python", "AWS", "Docker"]
        certs = our_profile.get("certifications", [])

        tech_req_bullets = [f"{req}" for req in tech_reqs] if tech_reqs else ["To be detailed per the solicitation requirements."]
        sec_req_bullets = [f"{req}" for req in security_reqs] if security_reqs else []

        findings = [
            {
                "title": "Technical Capability Alignment",
                "body": f"{company_name}'s core service portfolio in {', '.join(services[:3])} directly aligns with the requirements of Solicitation {sol_num}.",
                "bullets": tech_req_bullets[:5],
            },
            {
                "title": "Security & Compliance",
                "body": "Our development practices adhere to applicable security standards and industry best practices.",
                "bullets": sec_req_bullets[:4] or ["Data encryption in transit and at rest", "Role-based access control (RBAC)", "Regular security review cadence"],
            },
            {
                "title": "Proven Technology Stack",
                "body": "Our technology choices are driven by scalability, maintainability, and suitability for this engagement.",
                "bullets": [f"Core stack: {', '.join(tech_stack[:6])}"] + [f"Certification: {c}" for c in certs[:2]],
            },
        ]

        technical_alignment = [
            {"requirement": req, "solution": f"Addressed via {company_short}'s enterprise delivery methodology", "alignment": "Full"}
            for req in tech_reqs[:5]
        ]

        return {
            "executive_summary": (
                f"{company_name} is pleased to submit this Technical and Management Proposal in response to {agency}'s "
                f"Solicitation {sol_num} — {title}. We bring a proven track record in {', '.join(services[:3])}, "
                f"backed by a highly skilled team of engineers and domain experts.\n\n"
                f"Our proposed solution leverages our platforms ({', '.join(products[:2])}) "
                f"and an industry-standard technology stack ({', '.join(tech_stack[:4])}) to deliver a scalable, "
                f"secure, and maintainable system that meets all stated requirements. {company_short} is committed to "
                f"delivering on-time, on-budget, and in full compliance with {agency}'s technical and security standards."
                + (f"\n\nWith certifications including {', '.join(certs)} and a focus on delivery excellence, "
                   f"we are uniquely positioned to serve as a reliable partner for this engagement." if certs else "")
            ),
            "key_highlights": [
                f"Direct capability alignment with Solicitation {sol_num} requirements",
                f"Core expertise: {', '.join(services[:4])}",
                f"Platforms: {', '.join(products[:2])}",
                f"Technology stack: {', '.join(tech_stack[:5])}",
            ] + ([f"Certifications & registrations: {', '.join(certs)}"] if certs else []) + [
                "Dedicated project manager and weekly status reporting",
                "90-day post-delivery warranty and SLA guarantees",
            ],
            "strategic_context_intro": (
                f"The solicitation issued by {agency}" + (f" under NAICS {naics}" if naics else "") +
                f" represents a critical technology modernization initiative. "
                f"{company_name} has prepared this proposal to demonstrate our deep technical expertise and commitment to "
                f"delivering high-impact solutions. Our approach is rooted in Agile delivery, applicable compliance "
                f"standards, and strong stakeholder collaboration."
            ),
            "findings": findings,
            "scope_intro": (
                f"The scope of this proposal encompasses the full lifecycle of delivery for the requirements outlined in "
                f"Solicitation {sol_num}. Our team will execute an iterative, milestone-driven engagement from requirements "
                f"gathering through deployment, training, and post-launch support."
            ),
            "deliverables": [
                "Project Kickoff & Requirements Finalization Document",
                "System Architecture Design & Review",
                "Development Sprints with bi-weekly demos",
                "Security Assessment & Compliance Review",
                "User Acceptance Testing (UAT) & Sign-Off",
                "Production Deployment & Go-Live Support",
                "Knowledge Transfer & User Training Sessions",
                "Post-Deployment Support (90 days)",
                "Final Project Closeout Report",
            ],
            "technical_alignment": technical_alignment,
            "proposed_solution": (
                f"{company_name} proposes a cloud-native, microservices-based architecture leveraging "
                f"{', '.join(tech_stack[:6])}. The solution will be deployed on a compliant cloud environment "
                f"with built-in CI/CD pipelines for continuous delivery.\n\n"
                f"Our {products[0] if products else company_short + ' Platform'} will serve as the core application framework, "
                f"providing pre-built modules for workflow management, data integration, and reporting — reducing "
                f"custom development time by an estimated 30-40%.\n\n"
                f"Security is integrated at every layer: from secure coding practices reviewed against OWASP guidelines, "
                f"to network-level isolation, audit logging, and encryption of all data at rest and in transit."
            ),
            "capabilities": [
                {"name": svc, "description": f"End-to-end delivery of {svc} for government and enterprise clients."}
                for svc in services[:6]
            ],
            "tech_stack": tech_stack,
            "timeline_intro": "Our phased delivery approach ensures early value delivery and risk mitigation.",
            "phases": [
                {"phase": "Phase 1", "duration": "Weeks 1-2", "focus": "Kickoff, requirements gathering, architecture design", "deliverables": "Project plan, architecture document"},
                {"phase": "Phase 2", "duration": "Weeks 3-6", "focus": "Iterative development sprints", "deliverables": "Working software increments, sprint reviews"},
                {"phase": "Phase 3", "duration": "Weeks 7-8", "focus": "Testing, security review, UAT", "deliverables": "Test reports, security assessment, UAT sign-off"},
                {"phase": "Phase 4", "duration": "Weeks 9-10", "focus": "Deployment, training, handover", "deliverables": "Production system, training materials, closeout report"},
            ],
            "total_duration": "8–10 Weeks",
            "investment_intro": "Our pricing is structured to provide maximum value within the available budgetary parameters. Fixed-price milestones provide cost predictability.",
            "pricing": [],
            "sla_terms": [
                "99.9% system uptime (excluding scheduled maintenance)",
                "Critical bug resolution within 24 hours",
                "All deliverables subject to agency review and approval",
                "Weekly status reports and bi-weekly stakeholder demos",
                "90-day post-go-live warranty support included",
                f"Proposal validity: 90 days from submission (deadline: {deadline})",
            ],
            "past_performance": self._load_past_performance(),
        }

    def _build_partnership_sections_rules(
        self,
        partner_profile: dict[str, Any],
        our_profile: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build structured B2B partnership sections deterministically from
        the two company profiles — used when the LLM call fails.
        """
        partner_name = partner_profile.get("company_name", "the Partner Company")
        partner_industry = partner_profile.get("industry", "technology services")
        partner_services = partner_profile.get("products_and_services", partner_profile.get("services", []))
        partner_hq = partner_profile.get("headquarters", "")

        company_name = get_company_name()
        company_short = get_company_short_name()
        our_services = our_profile.get("services", ["Enterprise Software Development", "AI/ML Solutions", "Cloud Architecture"])
        our_products = our_profile.get("products", [f"{company_short} Platform"])
        our_tech_stack = self._get_flat_tech_stack(our_profile)[:8] or ["React", "Node.js", "Python", "AWS"]

        # Find synergies: look for overlapping service keywords
        synergy_areas = []
        overlap_keywords = ["cloud", "ai", "data", "government", "enterprise", "digital", "analytics", "security"]
        partner_text = " ".join(str(s) for s in partner_services).lower()
        for kw in overlap_keywords:
            if kw in partner_text:
                synergy_areas.append(kw.title())
        if not synergy_areas:
            synergy_areas = ["Digital Transformation", "Cloud Modernization", "Enterprise Software"]

        return {
            "executive_summary": (
                f"{company_name} is pleased to present this Strategic Partnership Proposal to {partner_name}. "
                f"As a technology services and product company specializing in {', '.join(our_services[:3])}, "
                f"we have identified significant opportunities for a mutually beneficial collaboration.\n\n"
                f"Our analysis of {partner_name}'s capabilities and market position reveals strong complementarity "
                f"with {company_short}'s platforms ({', '.join(our_products[:2])}) and engineering expertise. "
                f"Together, we can deliver comprehensive solutions that neither organization could offer independently, "
                f"expanding our collective market reach and enhancing value delivery for shared clients.\n\n"
                f"This proposal outlines a phased partnership roadmap, from initial joint offering definition through "
                f"co-marketing and co-delivery, with clear milestones and mutual commitments."
            ),
            "key_highlights": [
                f"Strategic alignment in {', '.join(synergy_areas[:3])}",
                f"Complementary capabilities: {partner_name} + {company_name}",
                f"Joint product offerings leveraging {', '.join(our_products[:2])}",
                "Expanded market reach through combined client networks",
                "Revenue sharing and co-investment model",
                "Dedicated partnership management team",
                "Phased collaboration roadmap with clear milestones",
            ],
            "strategic_context_intro": (
                f"The {partner_industry} market is undergoing rapid transformation driven by digital modernization, "
                f"cloud adoption, and AI-powered automation. {partner_name}{' (headquartered in ' + partner_hq + ')' if partner_hq else ''} "
                f"and {company_name} are uniquely positioned to co-create solutions that address these market dynamics. "
                f"This partnership will combine {partner_name}'s domain expertise and market relationships with "
                f"{company_short}'s technology platforms and engineering capabilities."
            ),
            "findings": [
                {
                    "title": "Market Synergy",
                    "body": "Both organizations operate in complementary market segments, creating a natural partnership opportunity.",
                    "bullets": [
                        f"{partner_name} brings domain depth in {partner_industry}",
                        f"{company_short} brings proven platforms: {', '.join(our_products[:3])}",
                        f"Joint addressable market spans {', '.join(synergy_areas[:3])}",
                    ],
                },
                {
                    "title": "Technology Complementarity",
                    "body": "Our technology stacks are designed to integrate seamlessly via open APIs and standard protocols.",
                    "bullets": [
                        f"{company_short} core stack: {', '.join(our_tech_stack[:4])}",
                        "RESTful API integration layer for rapid onboarding",
                        "Shared cloud infrastructure support (AWS / Azure)",
                    ],
                },
                {
                    "title": "Commercial Model",
                    "body": "We propose a flexible partnership model structured around co-selling, co-delivery, and revenue sharing.",
                    "bullets": [
                        "Co-selling agreement with lead registration and deal protection",
                        "Revenue sharing: negotiated per engagement type",
                        "Joint marketing and conference presence",
                    ],
                },
            ],
            "scope_intro": (
                "The initial phase of the partnership focuses on defining our joint go-to-market offering, "
                "establishing integration between our platforms, and executing on 1-2 pilot client engagements "
                "to validate the business model before scaling."
            ),
            "deliverables": [
                "Joint Partnership Agreement (JPA) signed",
                "Technical integration blueprint and API design",
                "Pilot client identification and joint proposal",
                "Co-branded marketing collateral and case studies",
                "Joint solution demonstration environment",
                "Revenue sharing and deal registration process documentation",
                "Quarterly business review (QBR) cadence established",
            ],
            "technical_alignment": [
                {
                    "requirement": f"{partner_name} client need: {area}",
                    "solution": f"{company_short} {our_products[i % len(our_products)] if our_products else 'Platform'} integration",
                    "alignment": "Full Synergy",
                }
                for i, area in enumerate(synergy_areas[:4])
            ],
            "proposed_solution": (
                f"{company_name} proposes a phased integration of our {our_products[0] if our_products else 'platform'} "
                f"with {partner_name}'s existing offerings via a RESTful API gateway. This allows both platforms to "
                f"maintain their independent roadmaps while presenting a unified solution to joint clients.\n\n"
                f"Phase 1 will focus on API integration and a joint pilot engagement. Phase 2 will expand to co-selling "
                f"motions and co-branded service packages. Phase 3 will explore deeper product integration and potential "
                f"joint development of new IP targeting the {', '.join(synergy_areas[:2])} space."
            ),
            "capabilities": [
                {"name": svc, "description": f"{company_short}'s {svc} capability available to joint engagements."}
                for svc in our_services[:5]
            ],
            "tech_stack": our_tech_stack,
            "timeline_intro": "The partnership roadmap is structured in three phases to minimize risk and validate value early.",
            "phases": [
                {"phase": "Phase 1", "duration": "Month 1-2", "focus": "Partnership agreement, technical integration planning, pilot client identification", "deliverables": "JPA, integration blueprint, pilot proposal"},
                {"phase": "Phase 2", "duration": "Month 3-4", "focus": "Pilot delivery, co-marketing launch, deal registration process", "deliverables": "Pilot delivery, case study, marketing materials"},
                {"phase": "Phase 3", "duration": "Month 5-6", "focus": "Scale co-selling, explore joint product development", "deliverables": "Expanded pipeline, QBR, joint product roadmap"},
            ],
            "total_duration": "6 Months (Phase 1–3)",
            "investment_intro": "The partnership is structured as a mutual co-investment with costs and revenues shared proportionally to contribution.",
            "pricing": [],
            "sla_terms": [
                "Monthly partnership sync meetings",
                "Quarterly business reviews (QBRs)",
                "Lead registration and deal protection policy",
                "Joint escalation path for client issues",
                "Dedicated partnership manager from each organization",
                "90-day renegotiation option after Phase 1 completion",
            ],
            "past_performance": self._load_past_performance(),
        }


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def generate_prime_sections(
    rfp_data: dict[str, Any],
    optimized_profile: dict[str, Any] | None = None,
    solicitation_number: str = "",
    project_root: str | None = None,
) -> dict[str, Any]:
    """Generate LLM-powered prime response sections."""
    gen = RFPResponseGenerator(project_root=project_root)
    return gen.generate_prime_sections(rfp_data, optimized_profile, solicitation_number)


def generate_subcontract_sections(
    rfp_data: dict[str, Any],
    pitch_data: dict[str, Any],
    winner_profile: dict[str, Any] | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Generate rule-based subcontract teaming sections."""
    gen = RFPResponseGenerator(project_root=project_root)
    return gen.generate_subcontract_sections(rfp_data, pitch_data, winner_profile)


def generate_partnership_sections(
    partner_profile: dict[str, Any],
    project_root: str | None = None,
) -> dict[str, Any]:
    """Generate LLM-powered partnership sections."""
    gen = RFPResponseGenerator(project_root=project_root)
    return gen.generate_partnership_sections(partner_profile)
