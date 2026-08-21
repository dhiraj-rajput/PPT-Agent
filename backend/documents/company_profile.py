"""
documents/company_profile.py
-----------------------------
Single source of truth for the identity of "our own company" -- the bidder /
offeror this platform generates RFP responses on behalf of.

BEFORE this module existed, "OrbitAvanya Tech LLP" / "OrbitAvanya" was
hardcoded as a literal string in 50+ places across:
  - documents/rfp_response/rfp_response_generator.py (every prompt template
    and every rule-based fallback section)
  - documents/brand_config.py (DEFAULT_BRAND)
  - app/core/company_catalog.py (Mongo doc id, Excel filename, product names)

That meant standing this platform up for a *different* bidding company
required editing and redeploying Python source. This module makes the
bidding company's identity data, not code:

Resolution order (lowest -> highest priority):
  1. Built-in default (keeps today's OrbitAvanya behavior with zero config)
  2. Environment variables: OWN_COMPANY_NAME, OWN_COMPANY_SHORT_NAME,
     OWN_COMPANY_ID
  3. The `own_company_profile` MongoDB document (already the mechanism
     Settings > Company Profile writes to -- see brand_config.get_brand_config)

Usage:
    from documents.company_profile import get_company_name, get_company_short_name

    name = get_company_name()          # "OrbitAvanya Tech LLP" (or whatever is configured)
    short = get_company_short_name()   # "OrbitAvanya"
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Built-in fallback so an unconfigured deployment doesn't hard-fail. This is
# NOT meant to be "the" company -- override via env vars or the
# own_company_profile collection for any other deployment.
_DEFAULT_COMPANY_NAME = "OrbitAvanya Tech LLP"
_DEFAULT_COMPANY_SHORT = "OrbitAvanya"

_cached: dict[str, str] | None = None
_cached_full_profile: dict[str, Any] | None = None


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "", name.lower())
    return slug or "default_company"


def clear_company_profile_cache() -> None:
    """Clears cached company profile and identity data so updates from DB take immediate effect."""
    global _cached, _cached_full_profile
    _cached = None
    _cached_full_profile = None


def get_full_company_profile(force_refresh: bool = False) -> dict[str, Any]:
    """
    Returns the complete company profile dictionary for the bidding company from MongoDB 'own_company_profile'.
    Falls back gracefully to environment variables and default configuration.
    """
    global _cached_full_profile
    if _cached_full_profile is not None and not force_refresh:
        return _cached_full_profile

    profile: dict[str, Any] = {
        "company_name": os.environ.get("OWN_COMPANY_NAME", _DEFAULT_COMPANY_NAME),
        "short_name": os.environ.get("OWN_COMPANY_SHORT_NAME", _DEFAULT_COMPANY_SHORT),
        "website": os.environ.get("OWN_COMPANY_WEBSITE", "https://orbitavanya.com"),
        "email": os.environ.get("OWN_COMPANY_EMAIL", "contact@orbitavanya.com"),
        "phone": os.environ.get("OWN_COMPANY_PHONE", "+1 (800) 555-0199"),
        "address": os.environ.get("OWN_COMPANY_ADDRESS", "McLean, VA 22102"),
        "capabilities": [
            "AI-Powered Visual Analytics Dashboards",
            "Predictive Modeling & Disaster Expenditure Forecasting",
            "AWS & Cloud Infrastructure Migration",
            "Medical & Operating Room Video Systems Integration",
            "Automated RFP Analysis & Proposal Generation",
        ],
        "products": [
            {"name": "Orbit Avanya HMS", "description": "Operating Room Video & Medical Imaging Integration"},
            {"name": "Orbit Avanya Analytics", "description": "Predictive Analytics & Executive BI Dashboards"},
            {"name": "Orbit BidForge", "description": "Automated Government RFP & Teaming Proposal Platform"},
        ],
    }

    try:
        from utils.db_client import get_collection
        doc = get_collection("own_company_profile").find_one({}, {"_id": 0})
        if doc:
            # Map standard fields supporting multiple common naming styles
            name = doc.get("company_name") or doc.get("name") or doc.get("legal_name")
            if name:
                profile["company_name"] = name
                profile["name"] = name
            
            short = doc.get("short_name") or doc.get("company_short")
            if short:
                profile["short_name"] = short
                profile["company_short"] = short

            for key in ("website", "email", "phone", "address", "uei", "cage_code", "primary_naics", "primary_naics_desc", "size"):
                if doc.get(key):
                    profile[key] = doc[key]

            if doc.get("capabilities"):
                profile["capabilities"] = doc["capabilities"]
            if doc.get("products"):
                profile["products"] = doc["products"]
            if doc.get("city") and doc.get("state"):
                profile["city"] = doc["city"]
                profile["state"] = doc["state"]
                if "address" not in doc:
                    profile["address"] = f"{doc['city']}, {doc['state']}"
    except Exception as exc:
        logger.debug(f"[CompanyProfile] Could not load own_company_profile from MongoDB: {exc}")

    _cached_full_profile = profile
    return profile


def get_company_identity(force_refresh: bool = False) -> dict[str, str]:
    """Returns {"name": ..., "short_name": ..., "id": ...} for the bidding
    company this deployment represents. Cached in-process; pass
    force_refresh=True after the company profile is updated via Settings."""
    global _cached
    if _cached is not None and not force_refresh:
        return _cached

    full_profile = get_full_company_profile(force_refresh=force_refresh)
    name = full_profile.get("company_name") or full_profile.get("name") or _DEFAULT_COMPANY_NAME
    short = full_profile.get("short_name") or full_profile.get("company_short") or ""

    if not short:
        short = _DEFAULT_COMPANY_SHORT if name == _DEFAULT_COMPANY_NAME else (name.split()[0] if name else "")

    company_id = os.environ.get("OWN_COMPANY_ID") or _slugify(name)

    _cached = {"name": name, "short_name": short, "id": company_id}
    return _cached


def get_company_name() -> str:
    return get_company_identity()["name"]


def get_company_short_name() -> str:
    return get_company_identity()["short_name"]


def get_company_id() -> str:
    """Slug used for per-company storage keys (Mongo doc ids, catalog filenames)."""
    return get_company_identity()["id"]
