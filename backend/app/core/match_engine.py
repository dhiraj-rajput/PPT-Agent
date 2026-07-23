"""
app/core/match_engine.py
-------------------------
Dynamic, deterministic suitability match engine.
Replaces random seed / static scores with real capability matching
against OrbitAvanya_Services_ADD.xlsx services and add-ons.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from app.core.company_catalog import load_services_catalog


def compute_company_match_score(
    primary_naics: str = "",
    industry_desc: str = "",
    company_name: str = "",
    services_text: str = ""
) -> int:
    """
    Computes a deterministic match score (50–98) for a company against OrbitAvanya's catalog.
    """
    catalog = load_services_catalog()
    all_services = catalog.get("services", [])
    all_addons = catalog.get("addons", [])

    score = 50.0

    # 1. NAICS Prefix / Code Match (up to +25)
    naics_clean = re.sub(r"\D", "", str(primary_naics or ""))
    if naics_clean:
        if naics_clean.startswith("5415") or naics_clean == "541511":
            score += 25.0
        elif naics_clean.startswith("54"):
            score += 18.0
        elif naics_clean.startswith("51") or naics_clean.startswith("33"):
            score += 12.0

    # 2. Service & Industry Keyword Overlap (up to +20)
    target_text = f"{industry_desc} {company_name} {services_text}".lower()
    matches = 0
    for s in all_services:
        s_name = s.get("service_name", "").lower()
        if s_name and (s_name in target_text or any(kw in target_text for kw in s_name.split() if len(kw) > 3)):
            matches += 1

    for a in all_addons:
        a_name = a.get("service_name", "").lower()
        if a_name and a_name in target_text:
            matches += 1

    score += min(20.0, matches * 3.5)

    # 3. Small Business / High Value Boost (up to +5)
    if "government" in target_text or "defense" in target_text or "security" in target_text:
        score += 3.0

    final_score = int(min(98, max(50, round(score))))
    return final_score


def compute_tender_match_score(
    notice_id: str,
    title: str = "",
    summary: str = "",
    naics_code: str = ""
) -> int:
    """
    Computes a deterministic match score (55–99) for an RFP / Tender against OrbitAvanya's catalog.
    """
    catalog = load_services_catalog()
    all_services = catalog.get("services", [])
    all_addons = catalog.get("addons", [])

    score = 55.0

    # 1. NAICS Match (35%)
    naics_clean = re.sub(r"\D", "", str(naics_code or ""))
    if naics_clean:
        if naics_clean.startswith("541511") or naics_clean.startswith("5415"):
            score += 25.0
        elif naics_clean.startswith("54"):
            score += 18.0
        elif naics_clean.startswith("51"):
            score += 14.0
        elif naics_clean.startswith("33") or naics_clean.startswith("56"):
            score += 10.0

    # 2. Capability & Scope Overlap (35%)
    rfp_text = f"{title} {summary}".lower()
    matches = 0
    for s in all_services:
        s_name = s.get("service_name", "").lower()
        if s_name and s_name in rfp_text:
            matches += 1

    for a in all_addons:
        a_name = a.get("service_name", "").lower()
        if a_name and a_name in rfp_text:
            matches += 1

    score += min(18.0, matches * 4.0)

    # 3. Security & Compliance Keywords (15%)
    sec_keywords = ["iso 27001", "soc 2", "fips", "hipaa", "nist", "cybersecurity", "audit log", "rbac", "clearance"]
    sec_count = sum(1 for k in sec_keywords if k in rfp_text)
    score += min(7.0, sec_count * 2.0)

    # Return bounded score
    return int(min(99, max(55, round(score))))
