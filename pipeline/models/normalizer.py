"""
models/normalizer.py
--------------------
Pre-merge normaliser: combines raw outputs from the website crawler, LinkedIn scraper,
and external search agent into a single structured dict ready for the LLM compactor.

Key fixes vs. original compactor-branch version:
  - Accepts a 4th `external_insights` dict (LLM-structured search profile)
  - Pulls competitors from external search results
  - Pulls financial highlights from external search insights
  - Reads founded_year from the correct nested LinkedIn path: identity.founded_year
  - Increases raw_website_text limit to 8 000 chars (was 3 000)
  - Phone number deduplication / validation — rejects year-range strings
  - Merges external products_and_services into the combined products/services lists
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_phone(value: str) -> bool:
    """
    Return False for strings that look like year ranges or other non-phone values.
    Accepts only strings that contain 6+ consecutive digits (international or national).
    """
    stripped = re.sub(r"[\s\-\(\)\+\.]", "", value)
    # Must have at least 6 digits
    if not re.search(r"\d{6}", stripped):
        return False
    # Reject pure year ranges like "2021-2022" or "2021-2025"
    if re.fullmatch(r"(19|20)\d{2}[\-/](19|20)\d{2}", value.strip()):
        return False
    # Reject 4-digit years
    if re.fullmatch(r"(19|20)\d{2}", stripped):
        return False
    return True


def clean_list(items: Optional[List[Any]], max_len: int = 150) -> List[str]:
    """Clean, strip, de-duplicate and length-filter list elements."""
    if not items:
        return []
    seen: set = set()
    cleaned: List[str] = []
    for item in items:
        if not item:
            continue
        item_str = str(item).strip()
        # Collapse whitespace / markdown characters
        item_str = re.sub(r"[*_\t\n\r]+", " ", item_str)
        item_str = re.sub(r"\s+", " ", item_str).strip()
        if not item_str:
            continue
        # Clean LinkedIn noise
        item_str = clean_linkedin_garbage(item_str)
        if not item_str:
            continue
        # Drop overly long items (likely sentence fragments, not names)
        if len(item_str) > max_len:
            continue
        # Drop common nav-garbage patterns
        if _is_nav_garbage(item_str):
            continue
        lower = item_str.lower()
        if lower not in seen:
            seen.add(lower)
            cleaned.append(item_str)
    return cleaned


_NAV_GARBAGE_PATTERNS = re.compile(
    r"^(privacy|cookie|terms|disclaimer|all rights|please fill|required field|"
    r"strictly necessary|always active|performance cookies|functional cookies|"
    r"targeting cookies|your privacy|preference centre|press release template|"
    r"copyright ©|sign up|log in|register|subscribe|download|click here|"
    r"read more|learn more|get started|find out|explore|view all|"
    r"we use|we collect|our website|this site|this page|this document|"
    r"and launching|and (new|the|a |our|your|their|its)|"
    r"models faster|please (fill|select|enter|check|agree)|"
    r"if you are|for more information|to (learn|find|get|see|view|access))",
    re.IGNORECASE,
)

_NAV_GARBAGE_EXACT = {
    "true", "false", "null", "undefined", "yes", "no",
    "submit", "cancel", "close", "back", "next", "menu",
}


def _is_nav_garbage(text: str) -> bool:
    """Return True if the string looks like a UI/nav element, not business content."""
    lower = text.lower().strip()
    if lower in _NAV_GARBAGE_EXACT:
        return True
    if _NAV_GARBAGE_PATTERNS.match(text):
        return True
    return False


_LINKEDIN_GARBAGE_PATTERNS_LIST = [
    re.compile(p, re.IGNORECASE) for p in [
        r"sign in welcome back email or phone password show forgot password\??",
        r"sign in or by clicking continue to join or sign in, you agree to linkedin.*",
        r"new to linkedin\? join now.*",
        r"see all employees locations primary.*get directions",
        r"linkedin member\s*linkedin member\s*linkedin member\s*linkedin member\s*linkedin member",
        r"view \d+ employees at .*",
        r"report this post",
        r"followers \d+d",
        r"we were honoured to welcome.*",
        r"together, we continue to.*",
        r"we appreciate the interest shown by.*",
        r"looking forward to fostering.*",
        r"nasiru abdullahi",
    ]
]


def clean_linkedin_garbage(text: str) -> str:
    """Strip common LinkedIn login wall, cookies consent, and scraper noise."""
    if not text:
        return ""
    
    # 1. Clean line-by-line block noise
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        line_strip = line.strip()
        # Filter out obvious login page/sign-in elements
        lower_line = line_strip.lower()
        if any(keyword in lower_line for keyword in [
            "sign in", "welcome back", "forgot password", "join now", "cookie policy",
            "user agreement", "privacy policy", "linkedin member", "view all employees",
            "report this post", "followers", "followers count", "get directions",
            "by clicking continue", "continue to join", "show password", "agree to linkedin",
            "email or phone password", "see all employees locations"
        ]):
            continue
        # Strip lines that look like social post headers
        if lower_line.startswith("we were honoured to welcome") or lower_line.startswith("we appreciate the interest shown"):
            continue
        cleaned_lines.append(line)
        
    cleaned = "\n".join(cleaned_lines)

    # 2. Pre-compiled regex search-and-replace for inline noise blocks
    for pat in _LINKEDIN_GARBAGE_PATTERNS_LIST:
        cleaned = pat.sub("", cleaned)

    # Replace multiple spaces/newlines
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def merge_lists(*lists: Optional[List[str]], max_len: int = 150) -> List[str]:
    """Merge multiple lists, clean and de-duplicate."""
    combined: List[str] = []
    for lst in lists:
        if lst:
            combined.extend(lst)
    return clean_list(combined, max_len=max_len)


# ---------------------------------------------------------------------------
# Main normaliser
# ---------------------------------------------------------------------------

def normalize_company_intelligence(
    website_data: Dict[str, Any],
    linkedin_data: Dict[str, Any],
    google_data: Dict[str, Any],
    external_insights: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Normalise and pre-merge data from Website, LinkedIn, Google Search, and external insights.

    Args:
        website_data:       Serialised WebsiteData or CompanyMongoRecord from the website agent.
        linkedin_data:      Serialised LinkedInCompanyData from the LinkedIn agent.
        google_data:        Raw search results dict with a "results" list and optional "summary".
        external_insights:  LLM-structured profile from discover_external_news (may be None).

    Returns:
        A unified dict designed to be passed to BusinessIntelligenceCompactor.compact_from_dict().
    """

    # ------------------------------------------------------------------
    # 1. Unpack nested structures
    # ------------------------------------------------------------------

    # Website data can be a CompanyMongoRecord (with nested company_data) or a flat WebsiteData dict
    w_intel: Dict[str, Any] = (
        website_data.get("company_data", website_data)
        if isinstance(website_data.get("company_data"), dict)
        else website_data
    )

    # LinkedIn identity lives under the "identity" key in LinkedInCompanyData
    li_identity: Dict[str, Any] = linkedin_data.get("identity") or {}
    li_bi: Dict[str, Any] = linkedin_data.get("bi_profile") or {}
    li_desc: Dict[str, Any] = linkedin_data.get("description") or {}

    # External insights (LLM-structured search profile)
    ext: Dict[str, Any] = external_insights or {}
    ext_insights_list: List[Dict[str, Any]] = ext.get("insights") or []

    # ------------------------------------------------------------------
    # 2. Company name & website
    # ------------------------------------------------------------------
    website_name = w_intel.get("company_name") or w_intel.get("company_data", {}).get("company_name", "")
    linkedin_name = li_identity.get("company_name") or linkedin_data.get("company_name") or linkedin_data.get("name") or ""

    website_url = (
        w_intel.get("website_url")
        or w_intel.get("website")
        or website_data.get("website")
        or li_identity.get("website_url")
        or linkedin_data.get("website")
        or ""
    )

    company_name = (linkedin_name or website_name).strip()
    website = website_url.strip()

    # ------------------------------------------------------------------
    # 3. Locations
    # ------------------------------------------------------------------
    website_locs: List[str] = w_intel.get("locations", [])
    website_hq = w_intel.get("headquarters") or ""
    linkedin_locs_raw = linkedin_data.get("office_locations") or []
    linkedin_locs: List[str] = []
    if isinstance(linkedin_locs_raw, list):
        for loc in linkedin_locs_raw:
            if isinstance(loc, dict):
                city = loc.get("city") or loc.get("full_address") or ""
                if city:
                    linkedin_locs.append(city)
            elif isinstance(loc, str):
                linkedin_locs.append(loc)
    linkedin_locs += linkedin_data.get("locations", [])

    hq = (
        li_identity.get("headquarters_location")
        or linkedin_data.get("headquarters")
        or website_hq
    )
    locations = merge_lists(
        [website_hq] if website_hq else [],
        website_locs,
        [hq] if hq else [],
        linkedin_locs,
        linkedin_data.get("locations", []),
    )

    # ------------------------------------------------------------------
    # 4. Products & Services
    # ------------------------------------------------------------------
    # LinkedIn products live under bi_profile.products_and_services
    li_products_raw = li_bi.get("products_and_services") or []
    li_product_names: List[str] = [
        p.get("name", "") for p in li_products_raw if isinstance(p, dict) and p.get("name")
    ]

    # External insights products_and_services
    ext_products_raw = ext.get("products_and_services") or []
    ext_product_names: List[str] = [
        p.get("name", "") for p in ext_products_raw if isinstance(p, dict) and p.get("name")
    ]
    ext_service_names: List[str] = [
        p.get("description", "") for p in ext_products_raw
        if isinstance(p, dict) and p.get("description") and len(p.get("description", "")) < 120
    ]

    products = merge_lists(
        w_intel.get("products", []),
        linkedin_data.get("products", []),
        li_product_names,
        ext_product_names,
        max_len=120,
    )
    services = merge_lists(
        w_intel.get("services", []),
        linkedin_data.get("services", []),
        ext_service_names,
        max_len=120,
    )

    # ------------------------------------------------------------------
    # 5. Technology stack
    # ------------------------------------------------------------------
    li_tech_stack = (li_bi.get("tech_stack") or {})
    if isinstance(li_tech_stack, dict):
        li_tech = (
            li_tech_stack.get("frameworks_and_tools", [])
            + li_tech_stack.get("languages", [])
            + li_tech_stack.get("platforms", [])
        )
    else:
        li_tech = []
    technology_stack = merge_lists(
        w_intel.get("technology_stack", []),
        linkedin_data.get("technology_stack", []),
        li_tech,
        max_len=80,
    )

    # ------------------------------------------------------------------
    # 6. Leadership
    # ------------------------------------------------------------------
    li_leadership_raw = linkedin_data.get("leadership_team") or []
    li_leadership: List[str] = [
        m.get("full_name", "") for m in li_leadership_raw
        if isinstance(m, dict) and m.get("full_name")
    ]
    leadership = merge_lists(
        li_leadership,
        w_intel.get("leadership", []),
        linkedin_data.get("leadership", []),
        max_len=60,
    )

    # ------------------------------------------------------------------
    # 7. Clients & Partners
    # ------------------------------------------------------------------
    clients = merge_lists(
        w_intel.get("clients", []),
        linkedin_data.get("clients", []),
        max_len=100,
    )
    partners = merge_lists(
        w_intel.get("partners", []),
        linkedin_data.get("partners", []),
        max_len=100,
    )

    # ------------------------------------------------------------------
    # 8. Contact info
    # ------------------------------------------------------------------
    raw_phones = merge_lists(
        w_intel.get("phone_numbers", []),
        linkedin_data.get("phone_numbers", []),
        max_len=30,
    )
    phone_numbers = [p for p in raw_phones if _is_valid_phone(p)]

    emails = merge_lists(
        w_intel.get("emails", []),
        linkedin_data.get("emails", []),
        max_len=100,
    )
    social_links = merge_lists(
        w_intel.get("social_links", []),
        linkedin_data.get("social_links", []),
        max_len=200,
    )

    # ------------------------------------------------------------------
    # 9. Google search snippets (raw results list)
    # ------------------------------------------------------------------
    google_snippets: List[str] = []
    results_list = (
        google_data.get("results", [])
        if isinstance(google_data, dict)
        else (google_data if isinstance(google_data, list) else [])
    )
    for res in results_list:
        if isinstance(res, dict):
            title = res.get("title", "").strip()
            snippet = res.get("snippet", "").strip()
            link = (res.get("link") or res.get("url") or "").strip()
            if title or snippet:
                google_snippets.append(f"Title: {title}\nLink: {link}\nSnippet: {snippet}")
        elif isinstance(res, str):
            google_snippets.append(res.strip())

    # ------------------------------------------------------------------
    # 10. Descriptions
    # ------------------------------------------------------------------
    website_desc = w_intel.get("description", "")
    if isinstance(website_desc, dict):
        website_desc = json.dumps(website_desc)

    linkedin_desc_text = (
        li_desc.get("about_text")
        or linkedin_data.get("description")
        or linkedin_data.get("about_text")
        or ""
    )
    if isinstance(linkedin_desc_text, dict):
        linkedin_desc_text = json.dumps(linkedin_desc_text)

    google_summary = ""
    if isinstance(google_data, dict):
        google_summary = google_data.get("summary", "")
        if isinstance(google_summary, dict):
            google_summary = json.dumps(google_summary)

    descriptions = {k: v for k, v in {
        "website": str(website_desc).strip(),
        "linkedin": str(linkedin_desc_text).strip(),
        "google_summary": str(google_summary).strip(),
        "external_business_model": str(ext.get("business_model", "")).strip(),
        "external_value_proposition": str(ext.get("value_proposition", "")).strip(),
    }.items() if v}

    # ------------------------------------------------------------------
    # 11. LinkedIn identity metadata
    # ------------------------------------------------------------------
    employee_count = (
        li_identity.get("company_size_range")
        or linkedin_data.get("employee_count")
        or linkedin_data.get("size")
        or ""
    )
    specialties = clean_list(linkedin_data.get("specialties", []))
    tagline = li_identity.get("tagline") or ""

    # Founded year — correct path: identity.founded_year
    founded_year: Optional[int] = None
    raw_founded = (
        li_identity.get("founded_year")
        or linkedin_data.get("founded_year")
        or linkedin_data.get("founded")
    )
    if raw_founded:
        if isinstance(raw_founded, int) and 1800 < raw_founded < 2030:
            founded_year = raw_founded
        else:
            match = re.search(r"\b(19\d{2}|20[0-2]\d)\b", str(raw_founded))
            if match:
                founded_year = int(match.group(1))

    # ------------------------------------------------------------------
    # 12. Competitors (from external search insights)
    # ------------------------------------------------------------------
    competitors: List[str] = []
    for insight in ext_insights_list:
        cat = str(insight.get("category", "")).lower()
        desc = str(insight.get("description", ""))
        if "competitor" in cat or "competition" in cat or "market share" in cat:
            competitors.append(desc[:200])

    # Also pull from any top-level competitors key
    if ext.get("competitors"):
        competitors.extend([str(c) for c in ext["competitors"] if c])
    competitors = clean_list(competitors, max_len=250)

    # ------------------------------------------------------------------
    # 13. Financial highlights (from external search insights)
    # ------------------------------------------------------------------
    financial_highlights: List[str] = []
    for insight in ext_insights_list:
        cat = str(insight.get("category", "")).lower()
        if any(kw in cat for kw in ["financial", "revenue", "profit", "growth", "funding", "capital"]):
            financial_highlights.append(str(insight.get("description", ""))[:200])
    financial_highlights = clean_list(financial_highlights, max_len=250)

    # ------------------------------------------------------------------
    # 14. Recent news headlines
    # ------------------------------------------------------------------
    recent_news: List[str] = []
    for res in results_list[:8]:
        if isinstance(res, dict):
            title = res.get("title", "").strip()
            if title:
                recent_news.append(title)
    recent_news = clean_list(recent_news, max_len=200)

    # ------------------------------------------------------------------
    # 15. BI signals from LinkedIn
    # ------------------------------------------------------------------
    key_differentiators = li_bi.get("key_differentiators", [])
    competitive_advantages = li_bi.get("competitive_advantages", [])
    executive_summary = li_bi.get("executive_summary") or ""
    mission_statement = li_desc.get("mission_statement") or ""

    # ------------------------------------------------------------------
    # 16. Raw website text (increased limit for richer LLM context)
    # ------------------------------------------------------------------
    raw_website_text = (
        w_intel.get("clean_text")
        or w_intel.get("cleaned_markdown")
        or w_intel.get("raw_text")
        or ""
    )[:8_000]

    # Clean descriptions dict values
    cleaned_descs = {}
    for k, v in descriptions.items():
        cleaned_descs[k] = clean_linkedin_garbage(v)

    # Clean executive summary and tagline
    executive_summary = clean_linkedin_garbage(executive_summary)
    tagline = clean_linkedin_garbage(tagline)

    return {
        # Identity
        "company_name": company_name,
        "website": website,
        "industry": w_intel.get("industry") or li_identity.get("industry") or linkedin_data.get("industry") or "",
        "tagline": tagline,
        "employee_count": str(employee_count) if employee_count else "",
        "founded_year": founded_year,
        "specialties": specialties,

        # Descriptions
        "descriptions": cleaned_descs,
        "executive_summary": executive_summary,
        "mission_statement": mission_statement,

        # Location
        "headquarters": hq,
        "locations": locations,

        # Products, Services, Tech
        "products": products,
        "services": services,
        "technology_stack": technology_stack,

        # Business model (from external)
        "business_model": str(ext.get("business_model", "")).strip(),
        "value_proposition": str(ext.get("value_proposition", "")).strip(),

        # People
        "leadership": leadership,

        # Competitive intelligence
        "competitors": competitors,
        "financial_highlights": financial_highlights,
        "key_differentiators": clean_list(key_differentiators, max_len=200),
        "competitive_advantages": clean_list(competitive_advantages, max_len=200),

        # Clients & Partners
        "clients": clients,
        "partners": partners,

        # News
        "recent_news": recent_news,
        "google_search_insights": google_snippets,

        # Contact
        "emails": emails,
        "phone_numbers": phone_numbers,
        "social_links": social_links,

        # Raw text for additional LLM context
        "raw_website_text": raw_website_text,
    }
