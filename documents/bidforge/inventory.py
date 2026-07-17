"""
bidforge/inventory.py
----------------------
Stage 2a of the BidForge pipeline: "inventory" analysis — checking what we
can actually deliver against the parsed RFP requirements.

The original BidForge required the user to manually upload inventory files
per-product. That system isn't populated in PPT-Agent, so instead we reuse
the company profile that already exists (private/orbit_avanya_detailed_profiles.json
— reused here (loaded and flattened by _load_our_catalog()) as the
inventory source. Governed by the master AI_MODE toggle (BIDFORGE_MODE
override), with a deterministic rule-based fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from utils.helpers import setup_logger

logger = setup_logger(__name__)

_PROFILE_PATH = Path(__file__).resolve().parent.parent.parent / "private" / "orbit_avanya_detailed_profiles.json"


def _load_our_catalog() -> List[Dict[str, Any]]:
    """
    private/orbit_avanya_detailed_profiles.json is actually a LIST of per-product
    profiles (LMS, HMS, ERP, ...), each shaped like:
      {product_name, industry_domain, about_text, key_features: [...],
       technology_stack: {frontend: [...], backend: [...], ...}, pricing_model, ...}
    This builds a flat, usable product catalog from it. Falls back to a small
    hardcoded catalog if the file is missing/unreadable.
    """
    if _PROFILE_PATH.exists():
        try:
            raw = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"[BidForge:Inventory] Failed to load our company profile: {exc}")
            raw = None
        if isinstance(raw, list) and raw:
            catalog = []
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                tech_stack = entry.get("technology_stack", {})
                flat_tech: List[str] = []
                if isinstance(tech_stack, dict):
                    for items in tech_stack.values():
                        if isinstance(items, list):
                            flat_tech.extend(str(i) for i in items)
                elif isinstance(tech_stack, list):
                    flat_tech = [str(i) for i in tech_stack]

                catalog.append({
                    "product_name": entry.get("product_name", entry.get("company_name", "Product")),
                    "industry_domain": entry.get("industry_domain", ""),
                    "about": entry.get("about_text", ""),
                    "features": entry.get("key_features", []) or [],
                    "tech_stack": flat_tech,
                    "pricing_model": entry.get("pricing_model", "Not listed"),
                    "competitive_advantages": entry.get("competitive_advantages", []) or [],
                })
            if catalog:
                return catalog
        elif isinstance(raw, dict) and raw:
            # Already flat-shaped (e.g. a hand-edited single-company profile)
            return [{
                "product_name": raw.get("company_name", "Our Offering"),
                "industry_domain": "",
                "about": raw.get("about", ""),
                "features": (raw.get("products", []) or []) + (raw.get("services", []) or []),
                "tech_stack": raw.get("technology_stack") if isinstance(raw.get("technology_stack"), list) else [],
                "pricing_model": "Not listed",
                "competitive_advantages": [],
            }]

    # Hardcoded fallback (mirrors utils/rfp_response_generator.py's fallback profile)
    return [{
        "product_name": "OrbitAvanya Core Platform",
        "industry_domain": "",
        "about": "Enterprise software development, cloud architecture, and AI/ML solutions.",
        "features": ["Enterprise Software Development", "Cloud Architecture", "AI/ML Solutions",
                     "e-Governance Platforms", "System Integration", "DevOps & CI/CD"],
        "tech_stack": ["React", "Node.js", "Python", "FastAPI", ".NET Core", "PostgreSQL",
                        "MongoDB", "AWS", "Azure", "Docker", "Kubernetes"],
        "pricing_model": "Not listed",
        "competitive_advantages": [],
    }]


def analyze_inventory(parsed_rfp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a dict: {"items": [{name, present, our_price, availability,
    features_matched, features_missing, notes}], "generated_via": "ai"|"rule_based"}
    """
    from pipeline.ai.mode import run_with_fallback

    our_catalog = _load_our_catalog()
    result, path_used = run_with_fallback(
        "bidforge",
        ai_fn=lambda: _analyze_inventory_ai(parsed_rfp, our_catalog),
        rule_fn=lambda: _analyze_inventory_rules(parsed_rfp, our_catalog),
    )
    result["generated_via"] = path_used
    logger.info(f"[BidForge:Inventory] Analysis completed via '{path_used}' path.")
    return result


def _requested_items(parsed_rfp: Dict[str, Any]) -> List[str]:
    comps = parsed_rfp.get("identified_components", {}) or {}
    items = list(comps.get("technical", [])) + list(comps.get("layout", []))
    if not items:
        # fall back to technical_requirements capabilities
        for r in parsed_rfp.get("technical_requirements", []) or []:
            cap = r.get("capability") if isinstance(r, dict) else None
            if cap:
                items.append(cap)
    return items[:20]


def _analyze_inventory_ai(parsed_rfp: Dict[str, Any], our_catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
    from pipeline.ai.client import get_ai_client

    requirements_text = (parsed_rfp.get("raw_text", "") or "")[:8000] or parsed_rfp.get("summary", "")
    catalog_text = json.dumps(our_catalog, indent=2)[:6000]

    messages = [
        {
            "role": "system",
            "content": (
                "You are an Inventory Check & Analysis agent. Given RFP requirements and our company's "
                "product catalog (each entry is one of our products/services with its features, tech "
                "stack, and pricing model), determine what we can deliver. Respond ONLY with a JSON object: "
                '{"items": [{"name": str, "present": "YES"|"PARTIAL"|"NO", "our_price": str, '
                '"availability": str, "features_matched": [str], "features_missing": [str], "notes": str}]}. '
                "Never invent prices or facts not present in the catalog — use 'Not listed' if absent."
            ),
        },
        {
            "role": "user",
            "content": f"RFP Requirements:\n{requirements_text}\n\nOur product catalog:\n{catalog_text}",
        },
    ]
    result = get_ai_client().chat_json(messages)
    if not result.get("items"):
        raise ValueError("AI inventory analysis returned no items")
    return result


def _analyze_inventory_rules(parsed_rfp: Dict[str, Any], our_catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
    logger.info("[BidForge:Inventory] Running rule-based inventory match.")
    # Flatten catalog into a searchable (product_name, keyword) index
    keyword_index: List[tuple] = []
    for product in our_catalog:
        pool = [product.get("product_name", "")] + product.get("features", []) + product.get("tech_stack", [])
        for kw in pool:
            if kw:
                keyword_index.append((str(kw).lower(), product))

    items = []
    for req_item in _requested_items(parsed_rfp):
        req_lower = str(req_item).lower()
        matches = [(kw, prod) for kw, prod in keyword_index if kw in req_lower or req_lower in kw]
        matched_products = {m[1].get("product_name") for m in matches}
        matched_features = [m[0] for m in matches][:5]

        if matched_products:
            product = next(m[1] for m in matches)
            items.append({
                "name": req_item,
                "present": "YES",
                "our_price": product.get("pricing_model", "Not listed"),
                "availability": "Available" ,
                "features_matched": matched_features,
                "features_missing": [],
                "notes": f"Matched against our {', '.join(matched_products)} offering(s).",
            })
        else:
            items.append({
                "name": req_item,
                "present": "NO",
                "our_price": "Not listed",
                "availability": "Not listed",
                "features_matched": [],
                "features_missing": [req_item],
                "notes": "Not found in our product catalog.",
            })

    if not items:
        items.append({
            "name": "General Scope",
            "present": "PARTIAL",
            "our_price": "Not listed",
            "availability": "Not listed",
            "features_matched": [],
            "features_missing": [],
            "notes": "No specific requirement items were extracted from the RFP text.",
        })
    return {"items": items}
