"""
bidforge/summarise.py
----------------------
Stage 3 of the BidForge pipeline: consolidate parsed requirements +
inventory + competitor intel into a per-item strategic pricing decision
(mirrors BidForge's SUMMARISER_PROMPT). Governed by the master AI_MODE
toggle (BIDFORGE_MODE override), with a deterministic rule-based fallback.
"""

from __future__ import annotations

from typing import Any, Dict, List

from utils.helpers import setup_logger

logger = setup_logger(__name__)


def summarise_pricing_strategy(
    parsed_rfp: Dict[str, Any],
    inventory: Dict[str, Any],
    competitor_intel: Dict[str, Any],
) -> Dict[str, Any]:
    """Returns {"items": [{name, current_price, options, avg_competitor_price,
    recommended_option_index, data}], "generated_via": ...}"""
    from pipeline.ai.mode import run_with_fallback

    result, path_used = run_with_fallback(
        "bidforge",
        ai_fn=lambda: _summarise_ai(parsed_rfp, inventory, competitor_intel),
        rule_fn=lambda: _summarise_rules(inventory, competitor_intel),
    )
    result["generated_via"] = path_used
    logger.info(f"[BidForge:Summarise] Strategy synthesized via '{path_used}' path.")
    return result


def _summarise_ai(
    parsed_rfp: Dict[str, Any], inventory: Dict[str, Any], competitor_intel: Dict[str, Any]
) -> Dict[str, Any]:
    from pipeline.ai.client import get_ai_client
    import json

    messages = [
        {
            "role": "system",
            "content": (
                "You are a Strategic Sales Decision agent. Given parsed RFP requirements, our inventory "
                "analysis, and competitor pricing data, produce a pricing strategy decision for each "
                "product/service. Respond ONLY with JSON: "
                '{"items": [{"name": str, "current_price": str, "options": [str, str, str], '
                '"avg_competitor_price": str|null, "recommended_option_index": int, "data": str}]}. '
                "Each item must have 2-3 genuinely different pricing options (always include the current "
                "price as one option). 'data' is a thorough markdown summary a proposal writer can work "
                "from directly. Never invent a price that isn't in the source data."
            ),
        },
        {
            "role": "user",
            "content": (
                f"RFP summary: {parsed_rfp.get('summary', '')}\n\n"
                f"Inventory analysis:\n{json.dumps(inventory.get('items', []), indent=2)[:6000]}\n\n"
                f"Competitor pricing:\n{json.dumps(competitor_intel.get('items', []), indent=2)[:6000]}"
            ),
        },
    ]
    result = get_ai_client().chat_json(messages)
    if not result.get("items"):
        raise ValueError("AI summarise returned no items")
    return result


def _summarise_rules(inventory: Dict[str, Any], competitor_intel: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("[BidForge:Summarise] Running rule-based pricing strategy synthesis.")
    comp_by_name = {c.get("item_name"): c for c in competitor_intel.get("items", [])}

    items = []
    for inv_item in inventory.get("items", []):
        name = inv_item.get("name", "Item")
        current_price = inv_item.get("our_price", "Not listed")
        comp = comp_by_name.get(name, {})
        avg_price = comp.get("avg_price")

        options = [f"Current Price: {current_price} — our standard offering"]
        if avg_price:
            options.append(f"Competitive Match: {avg_price} — align with observed market rate")
        options.append(f"{current_price} with bundled support — added value option")

        items.append({
            "name": name,
            "current_price": current_price,
            "options": options,
            "avg_competitor_price": avg_price,
            "recommended_option_index": 0,
            "data": (
                f"Requirement: {name}. Availability: {inv_item.get('present', 'Unknown')}. "
                f"Notes: {inv_item.get('notes', '')} "
                f"Competitor data: {comp.get('competitors', 'None found')}"
            ),
        })
    return {"items": items}
