"""
documents/rfp_response/response_planner.py
--------------------------------------------
Builds a per-RFP generation plan for RFPResponseGenerator -- the generator
used by the orchestrator's autonomous "RFP auto upload -> auto respond"
pipeline (pipeline/orchestrator/nodes.py:generate_rfp_response).

BEFORE this module existed, RFPResponseGenerator's prime-mode system prompt
contained one static "DOCUMENT PLAN" block (10 fixed section descriptions)
that was sent to the LLM identically for every solicitation, regardless of
what RFPParser actually extracted (rfp_type, structural_elements,
requirements, compliance_requirements). A 2-page RFI and a 90-page tender
with mandatory bid security and a dozen annexures got the exact same
instructions -- and the RFP's own structural_elements were never even read
by this stage of the pipeline.

This mirrors the same "read the parsed RFP, don't assume a fixed skeleton"
idea already used for the guided BidForge wizard outline
(documents/bidforge/outline.py), adapted to the fixed-JSON-schema prompt
RFPResponseGenerator uses: instead of returning a freeform section list, it
returns *plan guidance text* that gets substituted into the system prompt at
call time, plus a small structured summary (`include_pricing_table`, etc.)
callers can use directly instead of re-deriving it from raw rfp_data.
"""

from __future__ import annotations

from typing import Any

# Requirement/structural-element counts above these thresholds bump the plan
# to the next complexity tier. Not a hard cutoff -- just a way to scale
# section depth guidance to the actual size of the solicitation instead of
# treating every RFP as the same size.
_COMPLEX_REQUIREMENT_THRESHOLD = 20
_COMPLEX_STRUCTURAL_THRESHOLD = 6
_STANDARD_REQUIREMENT_THRESHOLD = 6


def build_response_plan(rfp_data: dict[str, Any]) -> dict[str, Any]:
    """Reads RFPParser's output (rfp_type, requirements, compliance_requirements,
    structural_elements) and returns a plan dict:

    {
        "rfp_type": "product_catalog|capability_tender|hybrid",
        "complexity": "simple|standard|complex",
        "requirement_count": int,
        "compliance_count": int,
        "include_pricing_table": bool,
        "pricing_basis": "catalog|lump_sum|deferred",
        "structural_callouts": [ {type, name, description}, ... ],
        "plan_text": "<guidance block substituted into the system prompt>",
    }
    """
    rfp_type = str(rfp_data.get("rfp_type") or "capability_tender").strip().lower()
    requirements = rfp_data.get("requirements") or []
    compliance = rfp_data.get("compliance_requirements") or []
    structural = [s for s in (rfp_data.get("structural_elements") or []) if isinstance(s, dict)]

    requirement_count = len(requirements)
    compliance_count = len(compliance)

    if requirement_count >= _COMPLEX_REQUIREMENT_THRESHOLD or len(structural) >= _COMPLEX_STRUCTURAL_THRESHOLD:
        complexity = "complex"
    elif requirement_count >= _STANDARD_REQUIREMENT_THRESHOLD or structural:
        complexity = "standard"
    else:
        complexity = "simple"

    def _of_type(*types: str) -> list[dict[str, Any]]:
        wanted = {t.lower() for t in types}
        return [s for s in structural if str(s.get("type", "")).lower() in wanted]

    pricing_structural = _of_type("pricing_format")
    bid_security = _of_type("bid_security")
    mandatory_forms = _of_type("mandatory_form", "annexure", "proforma", "form")
    submission_format = _of_type("submission_format")
    evaluation_criteria = _of_type("evaluation_criterion")

    if rfp_type == "product_catalog" or pricing_structural:
        include_pricing_table = True
        pricing_basis = "catalog" if rfp_type in ("product_catalog", "hybrid") else "lump_sum"
    else:
        include_pricing_table = False
        pricing_basis = "deferred"

    plan_text = _render_plan_text(
        rfp_type=rfp_type,
        complexity=complexity,
        requirement_count=requirement_count,
        compliance_count=compliance_count,
        include_pricing_table=include_pricing_table,
        pricing_basis=pricing_basis,
        bid_security=bid_security,
        mandatory_forms=mandatory_forms,
        submission_format=submission_format,
        evaluation_criteria=evaluation_criteria,
    )

    return {
        "rfp_type": rfp_type,
        "complexity": complexity,
        "requirement_count": requirement_count,
        "compliance_count": compliance_count,
        "include_pricing_table": include_pricing_table,
        "pricing_basis": pricing_basis,
        "structural_callouts": bid_security + mandatory_forms + submission_format + evaluation_criteria,
        "plan_text": plan_text,
    }


_DEPTH_BY_COMPLEXITY = {
    "simple": (
        "This is a smaller-scope solicitation ({n} requirement(s) extracted). Keep every section focused "
        "and proportional to that scope -- do not pad findings, deliverables, or key_highlights to look "
        "bigger than the actual opportunity."
    ),
    "standard": (
        "This solicitation has a real, multi-part scope ({n} requirement(s) extracted). Give every section "
        "full, substantive treatment matched to that scope."
    ),
    "complex": (
        "This is a large, multi-requirement solicitation ({n} requirement(s), {s} structural element(s) "
        "extracted). Findings, technical_alignment, and deliverables must be comprehensive and map to every "
        "distinct requirement theme found -- do not condense a complex tender into a handful of generic bullets."
    ),
}


def _render_plan_text(
    *,
    rfp_type: str,
    complexity: str,
    requirement_count: int,
    compliance_count: int,
    include_pricing_table: bool,
    pricing_basis: str,
    bid_security: list[dict[str, Any]],
    mandatory_forms: list[dict[str, Any]],
    submission_format: list[dict[str, Any]],
    evaluation_criteria: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    lines.append(
        f"This solicitation was classified as rfp_type='{rfp_type}', complexity='{complexity}' "
        f"({requirement_count} distinct requirement(s), {compliance_count} compliance item(s) extracted "
        f"from the actual RFP text). Scale the depth and structure of every section to THIS solicitation, "
        f"not to a fixed template."
    )
    depth_template = _DEPTH_BY_COMPLEXITY.get(complexity, _DEPTH_BY_COMPLEXITY["standard"])
    lines.append(depth_template.format(n=requirement_count, s=len(mandatory_forms) + len(bid_security)))

    if include_pricing_table:
        if pricing_basis == "catalog":
            lines.append(
                "PRICING: this RFP expects a catalog/line-item price match -- populate the 'pricing' array "
                "with one row per priced item/service the requirements actually call for."
            )
        else:
            lines.append(
                "PRICING: this RFP defines its own pricing/price-schedule structure -- populate the "
                "'pricing' array to mirror that exact structure (same periods/line items), not a generic table."
            )
    else:
        lines.append(
            "PRICING: this RFP does not define a pricing/price-schedule structure and is not a catalog match "
            "-- leave the 'pricing' array empty and use investment_intro to explain how pricing will be "
            "handled (e.g. deferred to a separate financial envelope, negotiation, or provided on request). "
            "Do not invent a pricing table that the solicitation itself does not ask for."
        )

    if bid_security:
        names = "; ".join(str(s.get("name") or s.get("description") or "bid security") for s in bid_security[:5])
        lines.append(
            f"BID SECURITY: this RFP requires bid security/bid bond ({names}) -- explicitly confirm "
            f"commitment to it (in sla_terms or a finding). Never silently omit a mandatory financial instrument."
        )

    if mandatory_forms:
        names = "; ".join(str(s.get("name") or "form/annexure") for s in mandatory_forms[:8])
        lines.append(
            f"MANDATORY FORMS/ANNEXURES: the RFP requires {len(mandatory_forms)} form(s)/annexure(s) "
            f"({names}) -- reference each by name in findings or deliverables so the response visibly "
            f"acknowledges every mandatory attachment, even where the actual filled-in form is a separate file."
        )

    if submission_format:
        names = "; ".join(str(s.get("name") or s.get("description") or "") for s in submission_format[:3])
        lines.append(
            f"SUBMISSION FORMAT: the RFP specifies a submission format ({names}) -- reflect awareness of it "
            f"(e.g. envelope structure, sealing, page limits) in the executive summary or a finding."
        )

    if evaluation_criteria:
        names = "; ".join(str(s.get("name") or s.get("description") or "") for s in evaluation_criteria[:5])
        lines.append(
            f"EVALUATION CRITERIA: the RFP states specific evaluation criteria ({names}) -- shape "
            f"technical_alignment and findings to visibly satisfy these, not a generic capability pitch."
        )

    return "\n".join(f"- {line}" for line in lines)
