"""
bidforge/outline.py
--------------------
Stage 1.5 of the BidForge pipeline: build the document outline THIS RFP
actually requires, instead of the previous hardcoded 5-section skeleton
(Executive Summary / Scope of Work / Pricing Table / Implementation
Timeline / Terms and Conditions) that was used for every RFP regardless of
content.

Reads the merged parsed_rfp (including structural_elements -- mandatory
annexures/forms/submission-format requirements extracted by rfp_parser.py)
and asks the model to design a compliant, RFP-specific outline: one section
per major scope theme, one section per mandatory annexure/form the bidder
must literally fill in and return, a compliance/evaluation-criteria walk
-through, and a pricing section shaped like the RFP's own price schedule.

Falls back to a slightly-adaptive generic skeleton (sized to the number of
requirements actually found) only if the AI call fails outright -- never to
a completely RFP-blind 5-fixed-section list.
"""

from __future__ import annotations

import re
from typing import Any

from utils.helpers import setup_logger

logger = setup_logger(__name__)

# Absolute ceiling so a pathological AI response can't produce an
# unreasonably huge number of sections; NOT a target -- the model is told
# to scale to actual complexity, this is just a safety rail.
MAX_SECTIONS = 40


def build_outline(
    parsed_rfp: dict[str, Any],
    company_context: str = "",
    template_sections_present: list[str] | None = None,
) -> dict[str, Any]:
    """Returns {"sections": [...], "notes": "...", "generated_via": "ai|rule_based"}.

    template_sections_present: headings already on the uploaded company
    template (will be preserved). Outline will skip or mark improve_existing
    so generation does not double-write Executive Summary etc.
    """
    import json

    from pipeline.ai.client import get_ai_client
    from pipeline.ai.mode import run_with_fallback

    from documents.prompts import OUTLINE_ARCHITECT_PROMPT

    template_sections_present = template_sections_present or []

    def ai_fn() -> dict[str, Any]:
        client = get_ai_client()
        payload = {
            "rfp_type": parsed_rfp.get("rfp_type", "capability_tender"),
            "summary": parsed_rfp.get("summary", ""),
            "parsed_content": parsed_rfp.get("parsed_content", ""),
            "requirements": parsed_rfp.get("requirements", []),
            "compliance_requirements": parsed_rfp.get("compliance_requirements", []),
            "structural_elements": parsed_rfp.get("structural_elements", []),
            "metadata": parsed_rfp.get("metadata", {}),
        }
        template_block = ""
        if template_sections_present:
            template_block = (
                "TEMPLATE_SECTIONS_ALREADY_PRESENT (do not re-author full duplicates):\n"
                + "\n".join(f"  - {s}" for s in template_sections_present)
                + "\n\n"
            )
        messages = [
            {"role": "system", "content": OUTLINE_ARCHITECT_PROMPT},
            {
                "role": "user",
                "content": (
                    f"COMPANY CONTEXT (for tailoring which capability/experience sections make sense): "
                    f"{company_context or 'Not provided'}\n\n"
                    f"{template_block}"
                    f"MERGED PARSED RFP:\n{json.dumps(payload, indent=2)}"
                ),
            },
        ]
        res = client.chat_json(messages, max_tokens=10000)
        sections = res.get("sections") or []
        sections = _sanitize_sections(sections)
        sections = _dedupe_against_template(sections, template_sections_present)
        if not sections:
            raise ValueError("Outline architect returned no usable sections.")
        # Under rate limits the model often returns only 4–6 thin sections.
        # Merge missing critical tender sections so annexures / qual / compliance
        # are never dropped.
        if len(sections) < 10:
            fallback = _adaptive_fallback_outline(parsed_rfp)
            have = {_normalize_title(str(s.get("title") or "")) for s in sections}
            for fb in fallback:
                nt = _normalize_title(str(fb.get("title") or ""))
                if nt and nt not in have:
                    sections.append(fb)
                    have.add(nt)
            sections = _sanitize_sections(sections)[:MAX_SECTIONS]
        return {"sections": sections, "notes": res.get("notes", "")}

    def rule_fn() -> dict[str, Any]:
        logger.warning("[BidForge:Outline] Using rule-based adaptive outline fallback.")
        return {"sections": _adaptive_fallback_outline(parsed_rfp), "notes": ""}

    result, path_used = run_with_fallback("bidforge_outline", ai_fn, rule_fn)
    result["generated_via"] = path_used
    logger.info(f"[BidForge:Outline] Built {len(result['sections'])} section(s) via '{path_used}' path.")
    return result


def _normalize_title(title: str) -> str:
    t = re.sub(r"^\s*(section\s+)?\d+[\.\)\:]?\s*", "", title.strip(), flags=re.IGNORECASE)
    t = re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()
    return re.sub(r"\s+", " ", t)


def _titles_overlap(a: str, b: str) -> bool:
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    # Token overlap for close matches ("executive summary" vs "executive overview")
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    inter = ta & tb
    return len(inter) >= 2 and len(inter) / max(len(ta), len(tb)) >= 0.5


def _dedupe_against_template(
    sections: list[dict[str, Any]],
    template_sections: list[str],
) -> list[dict[str, Any]]:
    """Drop or demote outline sections that would duplicate template headings.

    - Brochure-style topics already on the template are omitted (cover/exec
      overview/competencies/accreditation already preserved).
    - RFP-mandatory form sections are never dropped.
    - improve_existing keeps a short tailoring pass only.
    """
    if not template_sections:
        return sections

    brochure_tokens = {
        "executive", "overview", "about", "company", "profile", "competenc",
        "accreditation", "certification", "contact", "capability statement",
        "corporate", "dossier",
    }
    out: list[dict[str, Any]] = []
    for s in sections:
        title = s.get("title") or ""
        mode = str(s.get("mode") or "write_new").lower()
        is_form = bool(s.get("is_mandatory_form"))
        overlaps = [t for t in template_sections if _titles_overlap(title, t)]
        if overlaps and not is_form:
            norm = _normalize_title(title)
            is_brochure = any(tok in norm for tok in brochure_tokens)
            if is_brochure and mode != "improve_existing":
                logger.info(
                    f"[BidForge:Outline] Omitting '{title}' — already present on template "
                    f"(matched: {overlaps[0]!r})"
                )
                continue
            if mode == "improve_existing" or is_brochure:
                s = dict(s)
                s["mode"] = "improve_existing"
                s["word_budget"] = min(int(s.get("word_budget") or 400), 500)
                s["key_points"] = (s.get("key_points") or [])[:4]
                s["key_points"] = [
                    "Tailor existing template narrative to THIS RFP only — do not rewrite from scratch",
                    *s["key_points"],
                ]
        out.append(s)
    return out


def _sanitize_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    seen_keys = set()
    for i, s in enumerate(sections[:MAX_SECTIONS]):
        if not isinstance(s, dict):
            continue
        title = str(s.get("title") or "").strip()
        if not title:
            continue
        key = str(s.get("key") or f"section_{i+1}").strip() or f"section_{i+1}"
        if key in seen_keys:
            key = f"{key}_{i+1}"
        seen_keys.add(key)
        try:
            word_budget = int(s.get("word_budget") or 1200)
        except (TypeError, ValueError):
            word_budget = 1200
        # Floor raised so tender sections are never stub-length; ceiling allows
        # deep technical / annexure responses.
        word_budget = max(800, min(word_budget, 6000))
        key_points = s.get("key_points") or []
        if isinstance(key_points, str):
            key_points = [line.strip() for line in key_points.splitlines() if line.strip()]
        mode = str(s.get("mode") or "write_new").strip().lower()
        if mode not in ("write_new", "improve_existing"):
            mode = "write_new"
        cleaned.append({
            "key": key,
            "title": title,
            "word_budget": word_budget,
            "included": s.get("included") is not False,
            "is_mandatory_form": bool(s.get("is_mandatory_form")),
            "source_clause": str(s.get("source_clause") or ""),
            "mode": mode,
            "key_points": [str(k) for k in key_points if str(k).strip()],
        })
    return cleaned


def _adaptive_fallback_outline(parsed_rfp: dict[str, Any]) -> list[dict[str, Any]]:
    """Used only if the AI outline call fails outright. Still adapts to the
    RFP's own structural_elements/requirements instead of a fixed list, just
    without AI-authored key_points/word-budget tuning."""
    summary = parsed_rfp.get("summary") or "Overview of our understanding and proposed response."
    sections: list[dict[str, Any]] = [
        {
            "key": "cover_letter",
            "title": "1. Cover Letter / Letter of Transmittal",
            "word_budget": 800,
            "included": True,
            "is_mandatory_form": False,
            "source_clause": "",
            "key_points": [
                "Reference exact tender number and title",
                "Confirm full-scope turnkey bid",
                "Bid validity and bid security commitment",
            ],
        },
        {
            "key": "executive_summary",
            "title": "2. Executive Summary",
            "word_budget": 1200,
            "included": True,
            "is_mandatory_form": False,
            "source_clause": "",
            "key_points": [summary],
        },
    ]

    requirements = parsed_rfp.get("requirements") or []
    if requirements:
        batch_size = 3
        for i in range(0, len(requirements), batch_size):
            batch = requirements[i:i + batch_size]
            names = [str(r.get("name", "")).strip() for r in batch if isinstance(r, dict) and r.get("name")]
            if not names:
                continue
            sections.append({
                "key": f"scope_{i // batch_size + 1}",
                "title": f"Scope of Work — {', '.join(names[:3])}{'...' if len(names) > 3 else ''}",
                "word_budget": max(1200, 400 * len(batch)),
                "included": True,
                "is_mandatory_form": False,
                "source_clause": "",
                "key_points": [
                    f"{r.get('name')}: {r.get('description', '')}"[:400]
                    for r in batch if isinstance(r, dict)
                ],
            })
    else:
        sections.append({
            "key": "technical_approach",
            "title": "3. Technical Approach & Methodology",
            "word_budget": 2000,
            "included": True,
            "is_mandatory_form": False,
            "source_clause": "",
            "key_points": ["Detailed methodology aligned to full RFP scope of work"],
        })

    structural = parsed_rfp.get("structural_elements") or []
    mandatory_forms = [
        s for s in structural
        if isinstance(s, dict) and (
            s.get("type") in ("mandatory_form", "annexure", "proforma", "form")
            or "annexure" in str(s.get("name", "")).lower()
            or "form" in str(s.get("type", "")).lower()
        )
    ]
    if not mandatory_forms:
        # Still reserve an annexures section so forms are not omitted entirely
        sections.append({
            "key": "annexures_response",
            "title": "Annexures & Mandatory Forms Response",
            "word_budget": 2000,
            "included": True,
            "is_mandatory_form": True,
            "source_clause": "RFP Annexures",
            "key_points": [
                "Respond to every annexure listed in the RFP (Bid Bond, Checklist, etc.)",
                "Use tables; mark unknown fields as [BIDDER TO INSERT: …]",
            ],
        })
    else:
        for i, form in enumerate(mandatory_forms, start=1):
            sections.append({
                "key": f"mandatory_form_{i}",
                "title": str(form.get("name") or f"Required Form / Annexure {i}"),
                "word_budget": 1000,
                "included": True,
                "is_mandatory_form": True,
                "source_clause": str(form.get("name") or ""),
                "key_points": [str(form.get("description") or "Complete this annexure as required by the RFP")],
            })

    if parsed_rfp.get("compliance_requirements"):
        sections.append({
            "key": "compliance",
            "title": "Compliance Matrix & Evaluation Criteria Response",
            "word_budget": 2000,
            "included": True,
            "is_mandatory_form": False,
            "source_clause": "",
            "key_points": [str(c) for c in parsed_rfp.get("compliance_requirements", [])[:20]],
        })

    sections.append({
        "key": "technical_qualification",
        "title": "Technical Qualification & Past Performance",
        "word_budget": 1800,
        "included": True,
        "is_mandatory_form": False,
        "source_clause": "",
        "key_points": [
            "Evidence against RFP technical qualification criteria",
            "Project reference table with years, clients, values",
        ],
    })
    sections.append({
        "key": "financial_qualification",
        "title": "Financial Qualification",
        "word_budget": 1000,
        "included": True,
        "is_mandatory_form": False,
        "source_clause": "",
        "key_points": ["Turnover, net worth, bank guarantees as required by RFP"],
    })
    sections.append({
        "key": "hse",
        "title": "HSE Management Plan",
        "word_budget": 1200,
        "included": True,
        "is_mandatory_form": False,
        "source_clause": "",
        "key_points": ["HSE policy, emergency response, statutory compliance"],
    })
    sections.append({
        "key": "pricing",
        "title": "Commercial Proposal & Price Schedule",
        "word_budget": 1500,
        "included": True,
        "is_mandatory_form": False,
        "source_clause": "",
        "key_points": ["Follow the RFP's own price schedule structure where specified"],
    })
    sections.append({
        "key": "terms_conditions",
        "title": "Terms, Conditions & Declarations",
        "word_budget": 800,
        "included": True,
        "is_mandatory_form": False,
        "source_clause": "",
        "key_points": ["Validity period", "Payment terms", "Deviations if any"],
    })
    return sections
