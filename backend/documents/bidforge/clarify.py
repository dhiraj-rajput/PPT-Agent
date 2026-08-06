"""
bidforge/clarify.py
--------------------
Generates the small set of clarifying questions a human must answer before
generation, derived from THIS RFP's actual missing_fields/ambiguities and
structural requirements -- not the previous generic "pricing model focus"
wizard questions that were shown before the RFP had even been parsed.

Supports multiple rounds: pass previously-answered questions back in via
`answered` and the model will only surface genuinely new/still-open items,
so the UI can loop ("ask -> answer -> re-check -> ask again if still
missing -> ... -> proceed") until nothing critical remains, capped by
MAX_ROUNDS to guarantee the loop terminates.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from utils.helpers import setup_logger

logger = setup_logger(__name__)

MAX_ROUNDS = 3


def build_clarifying_questions(
    parsed_rfp: Dict[str, Any],
    company_context: str = "",
    answered: Optional[List[Dict[str, Any]]] = None,
    round_number: int = 1,
) -> Dict[str, Any]:
    """Returns {"questions": [...], "round": n, "is_final_round": bool, "generated_via": "ai|rule_based"}.

    An empty `questions` list means the pipeline has everything it needs and
    generation can proceed.
    """
    from pipeline.ai.client import get_ai_client
    from pipeline.ai.mode import run_with_fallback
    from documents.prompts import CLARIFYING_QUESTIONS_PROMPT

    answered = answered or []
    is_final_round = round_number >= MAX_ROUNDS

    def ai_fn() -> Dict[str, Any]:
        client = get_ai_client()
        payload = {
            "missing_fields": parsed_rfp.get("missing_fields", []),
            "structural_elements": parsed_rfp.get("structural_elements", []),
            "compliance_requirements": parsed_rfp.get("compliance_requirements", []),
            "metadata": parsed_rfp.get("metadata", {}),
            "rfp_type": parsed_rfp.get("rfp_type", "capability_tender"),
        }
        user_content = (
            f"COMPANY CONTEXT: {company_context or 'Not provided'}\n\n"
            f"RFP GAPS/STRUCTURE TO CONSIDER:\n{json.dumps(payload, indent=2)}\n\n"
            f"QUESTIONS ALREADY ANSWERED THIS SESSION (do NOT re-ask these; only ask about "
            f"what's still genuinely unresolved):\n{json.dumps(answered, indent=2)}\n\n"
            f"This is round {round_number} of at most {MAX_ROUNDS}."
        )
        if is_final_round:
            user_content += (
                "\n\nThis is the FINAL round -- only ask about items that would make the "
                "proposal materially non-compliant or factually wrong if left unanswered. "
                "Anything less critical should be left out; the pipeline will proceed with "
                "a clearly-marked placeholder for it instead."
            )
        messages = [
            {"role": "system", "content": CLARIFYING_QUESTIONS_PROMPT},
            {"role": "user", "content": user_content},
        ]
        res = client.chat_json(messages, max_tokens=4000)
        questions = res.get("questions") or []
        return {"questions": _sanitize_questions(questions)}

    def rule_fn() -> Dict[str, Any]:
        logger.warning("[BidForge:Clarify] Using rule-based fallback: surfacing missing_fields verbatim.")
        answered_ids = {a.get("id") for a in answered if isinstance(a, dict)}
        questions = []
        for i, gap in enumerate(parsed_rfp.get("missing_fields", [])[:8]):
            qid = f"gap_{i+1}"
            if qid in answered_ids:
                continue
            questions.append({
                "id": qid,
                "question": f"The RFP does not clearly specify: {gap}. How should we handle this in our response?",
                "why_it_matters": "Flagged directly by RFP parsing as missing/ambiguous.",
                "category": "Compliance",
                "input_type": "text",
                "options": [],
                "allow_skip": True,
            })
        return {"questions": questions}

    result, path_used = run_with_fallback("bidforge_clarify", ai_fn, rule_fn)
    result["round"] = round_number
    result["is_final_round"] = is_final_round
    result["generated_via"] = path_used
    logger.info(
        f"[BidForge:Clarify] Round {round_number}/{MAX_ROUNDS}: "
        f"{len(result['questions'])} question(s) via '{path_used}' path."
    )
    return result


def _sanitize_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned = []
    seen_ids = set()
    for i, q in enumerate(questions[:8]):
        if not isinstance(q, dict):
            continue
        question_text = str(q.get("question") or "").strip()
        if not question_text:
            continue
        qid = str(q.get("id") or f"q_{i+1}").strip() or f"q_{i+1}"
        if qid in seen_ids:
            qid = f"{qid}_{i+1}"
        seen_ids.add(qid)
        options = q.get("options") or []
        clean_options = []
        for opt in options:
            if isinstance(opt, dict) and opt.get("id") and opt.get("label"):
                clean_options.append({
                    "id": str(opt["id"]),
                    "label": str(opt["label"]),
                    "description": str(opt.get("description") or ""),
                })
        input_type = str(q.get("input_type") or "text").strip().lower()
        if input_type not in ("text", "single_select", "multi_select"):
            input_type = "text"
        if input_type in ("single_select", "multi_select") and not clean_options:
            input_type = "text"
        cleaned.append({
            "id": qid,
            "question": question_text,
            "why_it_matters": str(q.get("why_it_matters") or ""),
            "category": str(q.get("category") or "General"),
            "input_type": input_type,
            "options": clean_options,
            "allow_skip": q.get("allow_skip") is not False,
        })
    return cleaned


def answers_to_context_block(answers: List[Dict[str, Any]]) -> str:
    """Renders resolved Q&A into a plain-text block the document generator's
    prompts can use directly as authoritative, human-confirmed context."""
    if not answers:
        return ""
    lines = ["HUMAN-CONFIRMED ANSWERS (treat as authoritative; do not contradict these):"]
    for a in answers:
        if not isinstance(a, dict):
            continue
        q = str(a.get("question") or a.get("id") or "").strip()
        ans = a.get("answer")
        if isinstance(ans, list):
            ans_text = ", ".join(str(x) for x in ans)
        else:
            ans_text = str(ans or "").strip()
        if not ans_text:
            continue
        lines.append(f"- Q: {q}\n  A: {ans_text}")
    return "\n".join(lines) if len(lines) > 1 else ""
