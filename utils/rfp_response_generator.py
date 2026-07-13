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
    from utils.rfp_response_generator import RFPResponseGenerator

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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts — adapted from BidForge's FINAL_DOCUMENT_PROMPT
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert proposal writer for OrbitAvanya Tech LLP, a technology services company.
You are drafting a professional government RFP response document.

OrbitAvanya Tech LLP specializes in:
- Enterprise software development (React, Node.js, Python, .NET)
- AI/ML systems and data platforms
- Cloud-native architectures (AWS, Azure, GCP)
- e-Governance digital transformation platforms
- Cybersecurity and compliance solutions
- Mobile applications and UX design
- DevOps, CI/CD, and system integration

Your output must be a JSON object with the following keys:
{
  "executive_summary": "<3-5 paragraph summary of the engagement>",
  "key_highlights": ["<up to 6 bullet point highlights>"],
  "strategic_context_intro": "<1-2 paragraph framing the engagement context>",
  "findings": [
    {"title": "...", "body": "...", "bullets": ["...", "..."]},
    {"title": "...", "body": "...", "bullets": ["...", "..."]},
    {"title": "...", "body": "...", "bullets": ["...", "..."]}
  ],
  "scope_intro": "<1-2 paragraph scope overview>",
  "deliverables": ["<list of deliverables>"],
  "technical_alignment": [
    {"requirement": "...", "solution": "...", "alignment": "Full / Partial"}
  ],
  "proposed_solution": "<3-4 paragraphs describing our technical solution>",
  "capabilities": [{"name": "...", "description": "..."}],
  "tech_stack": ["Technology1", "Technology2"],
  "timeline_intro": "<1 paragraph intro to timeline>",
  "phases": [
    {"phase": "Phase 1", "duration": "Week 1", "focus": "...", "deliverables": "..."}
  ],
  "total_duration": "8–10 Weeks",
  "investment_intro": "<1-2 paragraph intro to pricing>",
  "pricing": [
    {"item": "...", "unit": "Fixed", "qty": "1", "unit_price": "$XX,XXX", "total": "$XX,XXX"}
  ],
  "sla_terms": ["<list of SLA commitments>"],
  "past_performance": [
    {"project": "...", "client": "...", "period": "...", "relevance": "..."}
  ]
}

RULES:
- Write in a professional, formal government proposal tone.
- Ground every claim in the RFP requirements and our capabilities.
- Do NOT invent client names or fabricated references.
- Keep deliverables specific and actionable.
- The pricing table is optional — include if the RFP has pricing requirements, else use empty list.
- Highlight key metrics, vendor names, technical specifications, and critical requirements by wrapping them in double asterisks (e.g. **15% workshare**, **OrbitAvanya ERP**, **NIST compliance**).
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
Generate a complete, professional RFP response document on behalf of OrbitAvanya Tech LLP.
Respond as the PRIME CONTRACTOR submitting directly to {agency}.
Use the RFP requirements to shape the scope of work and technical approach sections.
Use the competitor intelligence to position our solution effectively.
Return ONLY the JSON object described in the system prompt.
"""

_SUBCONTRACT_SYSTEM_PROMPT = """\
You are an expert proposal writer for OrbitAvanya Tech LLP, a technology services company.
You are drafting a professional B2B subcontracting teaming proposal to a prime contractor who has won (or is bidding on) a government RFP.

OrbitAvanya Tech LLP proposes to serve as a subcontractor, contributing a specific workshare percentage of the scope (typically 10-20%) centered around our technology products and capabilities.

Your output must be a JSON object with the following keys:
{
  "executive_summary": "<3-5 paragraph summary proposing a teaming partnership to the prime winner>",
  "key_highlights": ["<up to 6 bullet point highlights of our teaming value proposition>"],
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
  "proposed_solution": "<3-4 paragraphs describing our matched product contribution and how it integrates with the prime's offering>",
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
- Highlight key metrics, vendor names, technical specifications, and critical requirements by wrapping them in double asterisks (e.g. **15% workshare**, **OrbitAvanya ERP**, **NIST compliance**).
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
OUR SUBCONTRACTOR PROFILE (OrbitAvanya Tech LLP)
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
Generate a complete, highly detailed subcontracting proposal on behalf of OrbitAvanya Tech LLP to {prime_name}.
Position our {product_name} product as the perfect technical contribution to {prime_name}'s team to meet {agency}'s requirements under Solicitation {solicitation_number}.
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

    def __init__(self, project_root: Optional[str] = None) -> None:
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parent.parent
        self._our_profile: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_prime_sections(
        self,
        rfp_data: Dict[str, Any],
        optimized_profile: Optional[Dict[str, Any]] = None,
        solicitation_number: str = "",
    ) -> Dict[str, Any]:
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
        logger.info("[RFPResponseGen] Generating PRIME response sections via Ollama LLM")
        our_profile = self._load_our_profile()
        prompt = self._build_prime_prompt(rfp_data, optimized_profile, our_profile, solicitation_number)
        sections = self._call_ollama(prompt)
        return self._validate_and_fill_defaults(sections, rfp_data)

    def generate_subcontract_sections(
        self,
        rfp_data: Dict[str, Any],
        pitch_data: Dict[str, Any],
        winner_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Mode B — Subcontract teaming proposal.
        LLM-powered by default (Ollama gemma4:31b-cloud) with a programmatic rule-based fallback.
        """
        logger.info("[RFPResponseGen] Generating SUBCONTRACT sections via Ollama LLM")
        try:
            our_profile = self._load_our_profile()
            prompt = self._build_subcontract_prompt(rfp_data, pitch_data, winner_profile, our_profile)
            sections = self._call_ollama_subcontract(prompt)
            if sections:
                return self._validate_and_fill_defaults(sections, rfp_data)
        except Exception as exc:
            logger.warning(f"[RFPResponseGen] Ollama subcontract generation failed: {exc}. Falling back to rule-based.")

        # Fallback to rule-based
        logger.info("[RFPResponseGen] Falling back to SUBCONTRACT sections (rule-based)")
        return self._build_subcontract_sections(rfp_data, pitch_data, winner_profile)

    def _build_subcontract_prompt(
        self,
        rfp_data: Dict[str, Any],
        pitch_data: Dict[str, Any],
        winner_profile: Optional[Dict[str, Any]],
        our_profile: Dict[str, Any]
    ) -> str:
        meta = rfp_data.get("metadata", {})
        reqs = rfp_data.get("identified_components", {})

        technical_reqs = "\n".join(
            f"  - {r}" for r in reqs.get("technical", [])[:15]
        ) or "  See RFP documents."

        security_reqs = "\n".join(
            f"  - {r}" for r in reqs.get("security", [])[:8]
        ) or "  Standard federal security requirements apply."

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
        our_summary = (
            f"Company: OrbitAvanya Tech LLP\n"
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
            workshare_pct=workshare
        )

    def _call_ollama_subcontract(self, user_prompt: str, max_retries: int = 3) -> Dict[str, Any]:
        """Calls Ollama chat API using the subcontract system prompt."""
        try:
            import ollama as _ollama
        except ImportError:
            raise RuntimeError("ollama package not installed. Run: pip install ollama>=0.4.0")

        from config.settings import settings
        model = settings.ollama_model or "gemma4:31b-cloud"
        host = settings.ollama_host or ""
        api_key = settings.ollama_api_key or ""

        messages = [
            {"role": "system", "content": _SUBCONTRACT_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ]

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                client_kwargs: Dict[str, Any] = {}
                if host:
                    client_kwargs["host"] = host

                headers = {}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                    client_kwargs["headers"] = headers

                if client_kwargs or headers:
                    client = _ollama.Client(**client_kwargs)
                    response = client.chat(
                        model=model,
                        messages=messages,
                        format="json",
                        options={"temperature": 0.2},
                    )
                else:
                    response = _ollama.chat(
                        model=model,
                        messages=messages,
                        format="json",
                        options={"temperature": 0.2},
                    )

                content = response.message.content
                if not content:
                    raise ValueError("Ollama returned empty response.")

                return self._parse_json(content)

            except Exception as exc:
                last_error = exc
                wait = 3.0 * (1.5 ** attempt)
                logger.warning(
                    f"[RFPResponseGen] Ollama attempt {attempt + 1}/{max_retries} failed: {exc} "
                    f"(retrying in {wait:.1f}s)"
                )
                if attempt < max_retries - 1:
                    time.sleep(wait)

        logger.error(f"[RFPResponseGen] All Ollama attempts failed: {last_error}")
        return {}

    # ------------------------------------------------------------------
    # Mode A — LLM
    # ------------------------------------------------------------------

    def _build_prime_prompt(
        self,
        rfp_data: Dict[str, Any],
        competitor_profile: Optional[Dict[str, Any]],
        our_profile: Dict[str, Any],
        solicitation_number: str,
    ) -> str:
        """Build the user-facing prompt for Ollama."""
        meta = rfp_data.get("metadata", {})
        reqs = rfp_data.get("identified_components", {})

        technical_reqs = "\n".join(
            f"  - {r}" for r in reqs.get("technical", [])[:15]
        ) or "  See RFP documents."

        security_reqs = "\n".join(
            f"  - {r}" for r in reqs.get("security", [])[:8]
        ) or "  Standard federal security requirements apply."

        # Summarize requirements text
        req_text = rfp_data.get("requirements_text", "") or ""
        requirements_summary = req_text[:2000] if req_text else "See technical and security requirements above."

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

        # Our profile summary
        tech_list = self._get_flat_tech_stack(our_profile)
        our_summary = (
            f"Company: OrbitAvanya Tech LLP\n"
            f"Products: {', '.join((our_profile.get('products', []))[:6])}\n"
            f"Services: {', '.join((our_profile.get('services', []))[:6])}\n"
            f"Tech Stack: {', '.join(tech_list[:8])}\n"
            f"Certifications: {', '.join((our_profile.get('certifications', []))[:4])}\n"
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
            competitor_profile=comp_summary,
            our_company_profile=our_summary,
        )

    def _call_ollama(self, user_prompt: str, max_retries: int = 3) -> Dict[str, Any]:
        """Call Ollama gemma4:31b-cloud and parse the JSON response."""
        try:
            import ollama as _ollama
        except ImportError:
            raise RuntimeError("ollama package not installed. Run: pip install ollama>=0.4.0")

        from config.settings import settings
        model = settings.ollama_model or "gemma4:31b-cloud"
        host = settings.ollama_host or ""
        api_key = settings.ollama_api_key or ""

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ]

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                client_kwargs: Dict[str, Any] = {}
                if host:
                    client_kwargs["host"] = host
                
                headers = {}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                    client_kwargs["headers"] = headers

                if client_kwargs or headers:
                    client = _ollama.Client(**client_kwargs)
                    response = client.chat(
                        model=model,
                        messages=messages,
                        format="json",
                        options={"temperature": 0.2},
                    )
                else:
                    response = _ollama.chat(
                        model=model,
                        messages=messages,
                        format="json",
                        options={"temperature": 0.2},
                    )

                content = response.message.content
                if not content:
                    raise ValueError("Ollama returned empty response.")

                return self._parse_json(content)

            except Exception as exc:
                last_error = exc
                wait = 3.0 * (1.5 ** attempt)
                logger.warning(
                    f"[RFPResponseGen] Ollama attempt {attempt + 1}/{max_retries} failed: {exc} "
                    f"(retrying in {wait:.1f}s)"
                )
                if attempt < max_retries - 1:
                    time.sleep(wait)

        logger.error(f"[RFPResponseGen] All Ollama attempts failed: {last_error}")
        return {}

    def _parse_json(self, text: str) -> Dict[str, Any]:
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
        rfp_data: Dict[str, Any],
        pitch_data: Dict[str, Any],
        winner_profile: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Builds all document sections deterministically from structured data.
        No LLM required.
        """
        meta         = rfp_data.get("metadata", {})
        reqs         = rfp_data.get("identified_components", {})
        prime        = pitch_data.get("prime_contractor", {})
        sub          = pitch_data.get("subcontractor", {})
        alignments   = pitch_data.get("alignment_matrices", {})
        settings_p   = pitch_data.get("proposal_settings", {})
        outreach     = pitch_data.get("pitch_outreach", {})

        agency_name    = meta.get("issuing_agency", "the issuing agency")
        project_title  = meta.get("project_title", "IT Services")
        prime_name     = prime.get("company_name", "Prime Contractor")
        workshare_pct  = settings_p.get("proposed_workshare_pct", 15.0)
        product_name   = sub.get("product_name", "our technology platform")
        domain         = sub.get("industry_domain", "technology services")

        # Executive summary
        executive_summary = (
            f"OrbitAvanya Tech LLP is pleased to present this formal subcontracting teaming proposal to "
            f"{prime_name} in response to Solicitation {meta.get('solicitation_number', '')} issued by "
            f"{agency_name}.\n\n"
            f"We propose to serve as a key subcontractor, contributing {workshare_pct}% of the total "
            f"contract scope, with a specific focus on {domain}. Our {product_name} platform directly "
            f"addresses the core technical and operational requirements outlined in the solicitation.\n\n"
            f"OrbitAvanya Tech LLP brings extensive experience in enterprise software delivery, cloud-native "
            f"architectures, and government-facing digital transformation initiatives. We are positioned to "
            f"add measurable value to {prime_name}'s delivery capability for this engagement."
        )

        key_highlights = [
            f"Proposed work share: {workshare_pct}% of total contract value",
            f"Core offering: {product_name} for {domain}",
            f"Demonstrated track record in enterprise digital transformation",
            f"Cloud-native, security-compliant architecture",
            f"Experienced delivery team with government sector expertise",
            "Committed to on-time, on-budget delivery with SLA guarantees",
        ]

        # Strategic context findings
        tech_reqs = reqs.get("technical", [])[:6]
        sec_reqs  = reqs.get("security", [])[:4]
        findings = [
            {
                "title": f"{agency_name} requires specialized technology capabilities",
                "body": (
                    f"The solicitation from {agency_name} outlines a comprehensive set of technical "
                    f"and operational requirements that demand deep domain expertise in {domain}. "
                    f"{prime_name}, as the prime contractor, can significantly strengthen its delivery "
                    f"capability by partnering with OrbitAvanya Tech LLP."
                ),
                "bullets": tech_reqs or [
                    "Enterprise-grade software development",
                    "Cloud-native and scalable architecture",
                    "Compliance and security standards alignment",
                ],
            },
            {
                "title": "OrbitAvanya's capabilities directly address the solicitation requirements",
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
            f"OrbitAvanya Tech LLP proposes to deliver the {product_name} as our core contribution "
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
            f"OrbitAvanya Tech LLP proposes to assume {workshare_pct}% of the total contract value "
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
                f"This teaming proposal outlines OrbitAvanya Tech LLP's qualifications and commitment "
                f"to supporting {prime_name} in delivering a successful outcome for {agency_name} "
                f"under Solicitation {meta.get('solicitation_number', '')}."
            ),
            "findings":               findings,
            "scope_intro":            (
                f"As the proposed subcontractor for this engagement, OrbitAvanya Tech LLP will be "
                f"responsible for delivering the following scope of work as part of the prime team:"
            ),
            "deliverables":           deliverables,
            "technical_alignment":    technical_alignment,
            "proposed_solution":      proposed_solution,
            "capabilities":           capabilities,
            "tech_stack":             tech_stack,
            "timeline_intro":         (
                f"The following phased delivery plan reflects OrbitAvanya's structured approach "
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

    def _load_our_profile(self) -> Dict[str, Any]:
        """Load Orbit Avanya's own company profile from private/."""
        if self._our_profile is not None:
            return self._our_profile

        profile_path = self.project_root / "private" / "orbit_avanya_detailed_profiles.json"
        if profile_path.exists():
            try:
                with open(profile_path, encoding="utf-8") as f:
                    self._our_profile = json.load(f)
                    if isinstance(self._our_profile, list) and self._our_profile:
                        self._our_profile = self._our_profile[0]
                    logger.info("[RFPResponseGen] Loaded own company profile from private/")
                    return self._our_profile
            except Exception as exc:
                logger.warning(f"[RFPResponseGen] Could not load own profile: {exc}")

        # Fallback hardcoded profile
        self._our_profile = {
            "products":         ["T360 Platform", "OrbitAI", "GovConnect Suite", "DataBridge"],
            "services":         ["Enterprise Software Development", "Cloud Architecture", "AI/ML Solutions",
                                 "e-Governance Platforms", "System Integration", "DevOps & CI/CD"],
            "technology_stack": ["React", "Node.js", "Python", "FastAPI", ".NET Core", "PostgreSQL",
                                 "MongoDB", "AWS", "Azure", "Docker", "Kubernetes"],
            "certifications":   ["SAM.gov Registered", "MSME India", "ISO 27001 (In Progress)"],
        }
        return self._our_profile

    def _get_flat_tech_stack(self, profile: Dict[str, Any]) -> List[str]:
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

    def _load_past_performance(self) -> List[Dict[str, str]]:
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
        self, sections: Dict[str, Any], rfp_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Ensure all required section keys exist with sensible defaults."""
        meta = rfp_data.get("metadata", {})

        defaults = {
            "executive_summary":      f"OrbitAvanya Tech LLP is pleased to submit this response to {meta.get('issuing_agency', 'the issuing agency')}.",
            "key_highlights":         ["Enterprise technology delivery", "Cloud-native architecture", "Government compliance expertise"],
            "strategic_context_intro": "This proposal addresses the core requirements of the solicitation.",
            "findings":               [
                {"title": "Technical requirements alignment", "body": "Our capabilities directly address the technical requirements.", "bullets": []},
            ],
            "scope_intro":            "The following scope of work describes our proposed deliverables.",
            "deliverables":           ["Enterprise application development", "System integration", "Testing & QA"],
            "technical_alignment":    [],
            "proposed_solution":      "OrbitAvanya Tech LLP proposes a comprehensive technology solution addressing all stated requirements.",
            "capabilities":           [],
            "tech_stack":             ["React", "Node.js", "Python", "AWS", "Docker"],
            "timeline_intro":         "The following phased plan outlines our implementation approach.",
            "phases":                 [],
            "total_duration":         "8–10 Weeks",
            "investment_intro":       "Our pricing is competitive and structured to deliver maximum value.",
            "pricing":                [],
            "sla_terms":              ["90-day post-delivery warranty", "Weekly status reporting", "Dedicated project manager"],
            "past_performance":       self._load_past_performance(),
        }

        for key, default in defaults.items():
            if not sections.get(key):
                sections[key] = default

        return sections


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def generate_prime_sections(
    rfp_data: Dict[str, Any],
    optimized_profile: Optional[Dict[str, Any]] = None,
    solicitation_number: str = "",
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate LLM-powered prime response sections."""
    gen = RFPResponseGenerator(project_root=project_root)
    return gen.generate_prime_sections(rfp_data, optimized_profile, solicitation_number)


def generate_subcontract_sections(
    rfp_data: Dict[str, Any],
    pitch_data: Dict[str, Any],
    winner_profile: Optional[Dict[str, Any]] = None,
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate rule-based subcontract teaming sections."""
    gen = RFPResponseGenerator(project_root=project_root)
    return gen.generate_subcontract_sections(rfp_data, pitch_data, winner_profile)
