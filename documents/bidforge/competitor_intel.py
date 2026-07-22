"""
bidforge/competitor_intel.py
-----------------------------
Stage 2b of the BidForge pipeline: competitor / market pricing intelligence.

The original BidForge required manually-uploaded competitor pricing files.
Instead, we reuse PPT-Agent's existing google_search agent (google_search/search_client.py
ExternalSearchClient) to pull live market/competitor pricing signals for each
requested item, then have the AI synthesize them the same way BidForge's
COMPETITOR_PRICING_PROMPT does. Governed by the master AI_MODE toggle
(BIDFORGE_MODE override), with a rule-based fallback that just surfaces the
raw search snippets without AI synthesis.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from utils.helpers import setup_logger

logger = setup_logger(__name__)


def gather_competitor_intel(parsed_rfp: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns {"items": [{item_name, competitors: [{name, price, notes}], avg_price, generated_via}]}
    """
    from pipeline.ai.mode import run_with_fallback

    item_names = [it.get("name") for it in inventory.get("items", []) if it.get("name")][:8]
    if not item_names:
        item_names = ["core scope of work"]

    try:
        def _pricing_worker():
            return asyncio.run(_search_market_pricing(item_names))

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                snippets_by_item = pool.submit(_pricing_worker).result()
        else:
            snippets_by_item = _pricing_worker()
    except Exception as exc:
        logger.warning(f"[BidForge:Competitor] Market search stage failed entirely: {exc}")
        snippets_by_item = {name: [] for name in item_names}

    result, path_used = run_with_fallback(
        "bidforge",
        ai_fn=lambda: _synthesize_competitor_pricing_ai(parsed_rfp, snippets_by_item),
        rule_fn=lambda: _synthesize_competitor_pricing_rules(snippets_by_item),
    )
    result["generated_via"] = path_used
    logger.info(f"[BidForge:Competitor] Analysis completed via '{path_used}' path.")
    return result


async def _search_market_pricing(item_names: List[str]) -> Dict[str, List[Dict[str, str]]]:
    """Uses the existing external search client to look up live market/competitor
    pricing signals for each requested item — the Python equivalent of BidForge's
    get_market_price tool."""
    results: Dict[str, List[Dict[str, str]]] = {}
    try:
        from config.settings import settings
        from pipeline.google_search.search_client import ExternalSearchClient
        client = ExternalSearchClient(settings)
    except Exception as exc:
        logger.warning(f"[BidForge:Competitor] Could not initialize search client: {exc}")
        return results

    for item in item_names:
        try:
            found = await client.search_company_sources(
                company_name="",
                official_url="",
                max_results=5,
                custom_query=f"{item} pricing competitors market rate 2026",
            )
            results[item] = [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in found]
        except Exception as exc:
            logger.warning(f"[BidForge:Competitor] Market search failed for '{item}': {exc}")
            results[item] = []
    return results


def _synthesize_competitor_pricing_ai(
    parsed_rfp: Dict[str, Any], snippets_by_item: Dict[str, List[Dict[str, str]]]
) -> Dict[str, Any]:
    from pipeline.ai.client import get_ai_client

    blocks = []
    for item, snippets in snippets_by_item.items():
        snippet_text = "\n".join(f"  - [{s['url']}] {s['snippet']}" for s in snippets) or "  (no market data found)"
        blocks.append(f"### {item}\n{snippet_text}")
    market_data = "\n\n".join(blocks)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a Competitor Pricing Intelligence agent. Given live web search snippets about "
                "market/competitor pricing for each requested item, extract what's usable. Respond ONLY "
                'with JSON: {"items": [{"item_name": str, "competitors": [{"name": str, "price": str, '
                '"notes": str}], "avg_price": str|null}]}. Use "Not listed" for prices not clearly stated '
                "in the snippets — never estimate or invent a price."
            ),
        },
        {"role": "user", "content": f"RFP summary: {parsed_rfp.get('summary', '')}\n\nMarket data:\n{market_data}"},
    ]
    result = get_ai_client().chat_json(messages)
    if not result.get("items"):
        raise ValueError("AI competitor synthesis returned no items")
    return result


def _synthesize_competitor_pricing_rules(snippets_by_item: Dict[str, List[Dict[str, str]]]) -> Dict[str, Any]:
    logger.info("[BidForge:Competitor] Running rule-based competitor snippet passthrough.")
    items = []
    for item, snippets in snippets_by_item.items():
        items.append({
            "item_name": item,
            "competitors": [
                {"name": s.get("title", "Unknown source"), "price": "Not listed", "notes": s.get("snippet", "")}
                for s in snippets[:3]
            ],
            "avg_price": None,
        })
    return {"items": items}
