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

from typing import Any, Dict, List

from utils.helpers import setup_logger

logger = setup_logger(__name__)

# Absolute ceiling so a pathological AI response can't produce an
# unreasonably huge number of sections; NOT a target -- the model is told
# to scale to actual complexity, this is just a safety rail.
MAX_SECTIONS = 40


def build_outline(parsed_rfp: Dict[str, Any], company_context: str = "") -> Dict[str, Any]:
    """Returns {"sections": [...], "notes": "...", "generated_via": "ai|rule_based"}."""
    from pipeline.ai.client import get_ai_client
    from pipeline.ai.mode import run_with_fallback
    from documents.prompts import OUTLINE_ARCHITECT_PROMPT
    import json

    def ai_fn() -> Dict[str, Any]:
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
        messages = [
            {"role": "system", "content": OUTLINE_ARCHITECT_PROMPT},
            {
                "role": "user",
                "content": (
                    f"COMPANY CONTEXT (for tailoring which capability/experience sections make sense): "
                    f"{company_context or 'Not provided'}\n\n"
                    f"MERGED PARSED RFP:\n{json.dumps(payload, indent=2)}"
                ),
            },
        ]
        res = client.chat_json(messages, max_tokens=10000)
        sections = res.get("sections") or []
        sections = _sanitize_sections(sections)
        if not sections:
            raise ValueError("Outline architect returned no usable sections.")
        return {"sections": sections, "notes": res.get("notes", "")}

    def rule_fn() -> Dict[str, Any]:
        logger.warning("[BidForge:Outline] Using rule-based adaptive outline fallback.")
        return {"sections": _adaptive_fallback_outline(parsed_rfp), "notes": ""}

    result, path_used = run_with_fallback("bidforge_outline", ai_fn, rule_fn)
    result["generated_via"] = path_used
    logger.info(f"[BidForge:Outline] Built {len(result['sections'])} section(s) via '{path_used}' path.")
    return result


def _sanitize_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
            word_budget = int(s.get("word_budget") or 500)
        except (TypeError, ValueError):
            word_budget = 500
        word_budget = max(150, min(word_budget, 4000))
        key_points = s.get("key_points") or []
        if isinstance(key_points, str):
            key_points = [line.strip() for line in key_points.splitlines() if line.strip()]
        cleaned.append({
            "key": key,
            "title": title,
            "word_budget": word_budget,
            "included": s.get("included") is not False,
            "is_mandatory_form": bool(s.get("is_mandatory_form")),
            "source_clause": str(s.get("source_clause") or ""),
            "key_points": [str(k) for k in key_points if str(k).strip()],
        })
    return cleaned


def _adaptive_fallback_outline(parsed_rfp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Used only if the AI outline call fails outright. Still adapts to the
    RFP's own structural_elements/requirements instead of a fixed list, just
    without AI-authored key_points/word-budget tuning."""
    sections: List[Dict[str, Any]] = [
        {
            "key": "executive_summary",
            "title": "1. Executive Summary",
            "word_budget": 600,
            "included": True,
            "is_mandatory_form": False,
            "source_clause": "",
            "key_points": [parsed_rfp.get("summary", "Overview of our understanding and proposed response.")],
        },
    ]

    requirements = parsed_rfp.get("requirements") or []
    if requirements:
        # Group into batches of ~4 so scope coverage scales with RFP size
        # instead of collapsing every requirement into one generic section.
        batch_size = 4
        for i in range(0, len(requirements), batch_size):
            batch = requirements[i:i + batch_size]
            names = [str(r.get("name", "")).strip() for r in batch if isinstance(r, dict) and r.get("name")]
            if not names:
                continue
            sections.append({
                "key": f"scope_{i // batch_size + 1}",
                "title": f"Scope of Work — {', '.join(names[:3])}{'...' if len(names) > 3 else ''}",
                "word_budget": 250 * len(batch) + 200,
                "included": True,
                "is_mandatory_form": False,
                "source_clause": "",
                "key_points": [f"{r.get('name')}: {r.get('description', '')}"[:300] for r in batch if isinstance(r, dict)],
            })

    structural = parsed_rfp.get("structural_elements") or []
    mandatory_forms = [s for s in structural if isinstance(s, dict) and s.get("type") == "mandatory_form"]
    for i, form in enumerate(mandatory_forms, start=1):
        sections.append({
            "key": f"mandatory_form_{i}",
            "title": str(form.get("name") or f"Required Form {i}"),
            "word_budget": 300,
            "included": True,
            "is_mandatory_form": True,
            "source_clause": str(form.get("name") or ""),
            "key_points": [str(form.get("description") or "")],
        })

    if parsed_rfp.get("compliance_requirements"):
        sections.append({
            "key": "compliance",
            "title": "Compliance & Evaluation Criteria Response",
            "word_budget": 500,
            "included": True,
            "is_mandatory_form": False,
            "source_clause": "",
            "key_points": [str(c) for c in parsed_rfp.get("compliance_requirements", [])[:10]],
        })

    sections.append({
        "key": "pricing",
        "title": "Pricing / Commercial Proposal",
        "word_budget": 500,
        "included": True,
        "is_mandatory_form": False,
        "source_clause": "",
        "key_points": ["Follow the RFP's own price schedule structure where one is specified."],
    })
    sections.append({
        "key": "terms_conditions",
        "title": "Terms, Conditions & Next Steps",
        "word_budget": 400,
        "included": True,
        "is_mandatory_form": False,
        "source_clause": "",
        "key_points": ["Validity period", "Payment terms", "Contact for follow-up"],
    })
    return sections
