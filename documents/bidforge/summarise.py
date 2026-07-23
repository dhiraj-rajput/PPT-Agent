"""
documents/bidforge/summarise.py
--------------------------------
Stage 3 of BidForge pipeline: synthesizes strategic pricing decisions from
parsed RFP requirements, inventory analysis, and competitor intelligence.
Ported from original BidForge's SUMMARISER_PROMPT.
"""

import json
import logging
from typing import Dict, Any

from utils.helpers import setup_logger
from pipeline.ai.client import get_ai_client
from documents.prompts import SUMMARISER_PROMPT

logger = setup_logger(__name__)

def summarise_pricing_strategy(
    parsed_rfp: Dict[str, Any],
    inventory: Dict[str, Any],
    competitor_intel: Dict[str, Any],
) -> Dict[str, Any]:
    """Generates pricing options and strategic reasoning per product/service item."""
    ai_client = get_ai_client()

    user_content = (
        f"1. PARSED RFP REQUIREMENTS:\n"
        f"Full parsed content:\n{parsed_rfp.get('parsed_content', '') or parsed_rfp.get('summary', '')}\n\n"
        f"Structured requirements:\n{json.dumps(parsed_rfp.get('requirements', []), indent=2)}\n\n"
        f"2. INVENTORY ANALYSIS:\n{json.dumps(inventory.get('items', []), indent=2)}\n\n"
        f"3. COMPETITOR PRICING:\n{json.dumps(competitor_intel.get('items', []), indent=2)}"
    )

    messages = [
        {"role": "system", "content": SUMMARISER_PROMPT},
        {"role": "user", "content": user_content}
    ]

    from pipeline.ai.mode import run_with_fallback

    def ai_fn() -> Dict[str, Any]:
        res = ai_client.chat_json(messages)
        if not res.get("items"):
            raise ValueError("AI summarise returned empty items array")
        return res

    def rule_fn() -> Dict[str, Any]:
        logger.warning(f"[BidForge:Summarise] Using rule fallback for pricing strategy synthesis.")
        return _summarise_fallback(inventory, competitor_intel)

    result, path_used = run_with_fallback("bidforge_summarise", ai_fn, rule_fn)
    result["generated_via"] = path_used
    return result


def _summarise_fallback(inventory: Dict[str, Any], competitor_intel: Dict[str, Any]) -> Dict[str, Any]:
    items = []
    comp_map = {c.get("item_name"): c for c in competitor_intel.get("items", [])}

    for inv in inventory.get("items", []):
        name = inv.get("name", "Item")
        current_price = inv.get("our_price", "Not listed")
        comp = comp_map.get(name, {})
        avg_price = comp.get("avg_price")

        options = [f"Current Price: {current_price} — Standard catalog price"]
        if avg_price:
            options.append(f"Competitive Match: {avg_price} — Market rate match")
        options.append(f"{current_price} (Bundled) — Includes priority SLA")

        items.append({
            "name": name,
            "current_price": current_price,
            "options": options,
            "avg_competitor_price": avg_price,
            "recommended_option_index": 0,
            "data": f"## {name}\n- Availability: {inv.get('present')}\n- Notes: {inv.get('notes')}"
        })

    return {"items": items}
