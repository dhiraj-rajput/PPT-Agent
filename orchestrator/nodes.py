"""
orchestrator/nodes.py
----------------------
All LangGraph node functions for the PPT-Agent pipeline.

Each function takes the current AgentState, does its work,
and returns a dict of state keys to update (not the full state).

Node catalogue:
  1. classify_input        → determines input_type
  2. discover_website      → company name → official website URL
  3. discover_linkedin     → company name → LinkedIn URL
  4. discover_from_website → website URL → LinkedIn URL (scraped/searched)
  5. run_website_agent     → crawl the official website
  6. run_linkedin_agent    → scrape LinkedIn
  7. merge_results         → combine outputs into a unified company profile
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from utils.helpers import is_valid_url, setup_logger
from utils.db_client import get_collection
from orchestrator.state import AgentState

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# 1. Input Classifier
# ---------------------------------------------------------------------------

def classify_input(state: AgentState) -> dict:
    """
    Determine whether the user_input is a:
      - "both_urls"     → contains both a website URL and a LinkedIn URL
      - "linkedin_url"  → looks like linkedin.com/company/...
      - "website_url"   → any other valid http/https URL
      - "company_name"  → plain text (no URL pattern)

    Also extracts company_slug from the input where possible.
    """
    raw = state["user_input"].strip()
    logger.info(f"[classify_input] Input: '{raw}'")

    # Split by whitespace, comma, or semicolon
    parts = [p.strip() for p in re.split(r'[\s,;]+', raw) if p.strip()]
    website_candidates = []
    linkedin_candidates = []

    for part in parts:
        if is_valid_url(part):
            if "linkedin.com/company" in part.lower():
                linkedin_candidates.append(part)
            else:
                website_candidates.append(part)

    # Case 1: Both URLs provided
    if website_candidates and linkedin_candidates:
        web_url = website_candidates[0]
        li_url = linkedin_candidates[0]
        slug = _slug_from_linkedin_url(li_url)
        logger.info(f"[classify_input] → both_urls (web={web_url}, linkedin={li_url}, slug={slug})")
        return {
            "input_type": "both_urls",
            "website_url": web_url,
            "linkedin_url": li_url,
            "company_slug": slug,
            "errors": [],
        }

    # Case 2: Direct URL inputs
    if is_valid_url(raw):
        netloc = urlparse(raw).netloc.lower()
        if "linkedin.com" in netloc:
            slug = _slug_from_linkedin_url(raw)
            logger.info(f"[classify_input] → linkedin_url (slug={slug})")
            return {
                "input_type": "linkedin_url",
                "linkedin_url": raw,
                "company_slug": slug,
                "errors": [],
            }
        else:
            domain = netloc.replace("www.", "")
            slug = domain.split(".")[0].lower().replace("-", "_")
            logger.info(f"[classify_input] → website_url (slug={slug})")
            return {
                "input_type": "website_url",
                "website_url": raw,
                "company_slug": slug,
                "errors": [],
            }

    # Plain text → company name
    logger.info("[classify_input] → company_name")
    return {
        "input_type": "company_name",
        "company_name": raw,
        "errors": [],
    }


# ---------------------------------------------------------------------------
# 2. Discover Official Website
# ---------------------------------------------------------------------------

def discover_website(state: AgentState) -> dict:
    """
    Given a company_name, search for the official website URL via Tavily.
    Updates: website_url, company_slug
    """
    company_name = state.get("company_name") or state["user_input"]
    logger.info(f"[discover_website] Searching for website of: '{company_name}'")

    try:
        from google_search import CompanyDiscovery
        discovery = CompanyDiscovery()
        website_url = discovery.find_official_website(company_name)

        if website_url:
            domain = urlparse(website_url).netloc.replace("www.", "")
            slug = domain.split(".")[0].lower().replace("-", "_")
            logger.info(f"[discover_website] Found: {website_url} (slug={slug})")
            return {"website_url": website_url, "company_slug": slug or state.get("company_slug")}
        else:
            logger.warning(f"[discover_website] No website found for '{company_name}'")
            return {"website_url": None}

    except Exception as e:
        msg = f"discover_website failed: {e}"
        logger.error(f"[discover_website] {msg}")
        return {"website_url": None, "errors": state.get("errors", []) + [msg]}


# ---------------------------------------------------------------------------
# 3. Discover LinkedIn URL
# ---------------------------------------------------------------------------

def discover_linkedin(state: AgentState) -> dict:
    """
    Given a company_name (or use company_slug), search for the LinkedIn company page.
    Updates: linkedin_url
    """
    company_name = state.get("company_name") or state["user_input"]
    logger.info(f"[discover_linkedin] Searching LinkedIn for: '{company_name}'")

    try:
        from google_search import CompanyDiscovery
        discovery = CompanyDiscovery()
        linkedin_url = discovery.find_linkedin_url(company_name)

        if linkedin_url:
            logger.info(f"[discover_linkedin] Found: {linkedin_url}")
            # Also extract slug from LinkedIn URL if not already set
            slug = state.get("company_slug") or _slug_from_linkedin_url(linkedin_url)
            return {"linkedin_url": linkedin_url, "company_slug": slug}
        else:
            logger.warning(f"[discover_linkedin] No LinkedIn found for '{company_name}'")
            return {"linkedin_url": None}

    except Exception as e:
        msg = f"discover_linkedin failed: {e}"
        logger.error(f"[discover_linkedin] {msg}")
        return {"linkedin_url": None, "errors": state.get("errors", []) + [msg]}


# ---------------------------------------------------------------------------
# 4. Discover LinkedIn from Website
# ---------------------------------------------------------------------------

def discover_from_website(state: AgentState) -> dict:
    """
    Given a website_url, try to find the LinkedIn company page:
      1. Try Tavily search for "<domain> site:linkedin.com/company"
      2. The website pipeline also extracts LinkedIn links from the site itself
         (set via website_data.linkedin_url after website agent runs)

    Updates: linkedin_url, company_name (if still unknown)
    """
    website_url = state.get("website_url")
    if not website_url:
        return {}

    logger.info(f"[discover_from_website] Finding LinkedIn from: {website_url}")

    updates = {}
    try:
        from google_search import CompanyDiscovery
        discovery = CompanyDiscovery()
        linkedin_url = discovery.find_linkedin_from_website(website_url)
        if linkedin_url:
            slug = state.get("company_slug") or _slug_from_linkedin_url(linkedin_url)
            updates["linkedin_url"] = linkedin_url
            updates["company_slug"] = slug
            logger.info(f"[discover_from_website] Found LinkedIn: {linkedin_url}")
        else:
            logger.warning(f"[discover_from_website] No LinkedIn found from: {website_url}")
    except Exception as e:
        msg = f"discover_from_website failed: {e}"
        logger.error(f"[discover_from_website] {msg}")
        updates["errors"] = state.get("errors", []) + [msg]

    return updates


# ---------------------------------------------------------------------------
# 5. Website Agent Node
# ---------------------------------------------------------------------------

def run_website_agent(state: AgentState) -> dict:
    """
    Run the WebsitePipeline on the company's official website.
    Stores results in MongoDB and returns a serialised dict in website_data.

    If no website_url is in state, this node is a no-op.
    """
    website_url = state.get("website_url")
    if not website_url:
        logger.info("[run_website_agent] No website_url — skipping")
        return {"website_data": None}

    logger.info(f"[run_website_agent] Crawling: {website_url}")
    try:
        from website.pipeline import WebsitePipeline
        pipeline = WebsitePipeline()
        data = pipeline.run(website_url)

        if data is None:
            logger.warning(f"[run_website_agent] Website pipeline returned None for: {website_url}")
            return {"website_data": None}

        serialized = data.model_dump(mode="json")

        # Propagate LinkedIn URL found on the website back into state
        updates: dict = {"website_data": serialized}
        if data.linkedin_url and not state.get("linkedin_url"):
            logger.info(f"[run_website_agent] LinkedIn found on site: {data.linkedin_url}")
            updates["linkedin_url"] = data.linkedin_url

        # Set company_name from website if still unknown
        if data.company_name and not state.get("company_name"):
            updates["company_name"] = data.company_name

        return updates

    except Exception as e:
        msg = f"run_website_agent failed: {e}"
        logger.error(f"[run_website_agent] {msg}", exc_info=True)
        return {"website_data": None, "errors": state.get("errors", []) + [msg]}


# ---------------------------------------------------------------------------
# 6. LinkedIn Agent Node
# ---------------------------------------------------------------------------

def run_linkedin_agent(state: AgentState) -> dict:
    """
    Run the LinkedIn scraping pipeline (all 3 layers).
    Input can be a LinkedIn URL, company slug, or company name.

    If no linkedin_url is in state but company_name exists, the LinkedIn
    module's InputResolver will use Tavily to find it.
    """
    linkedin_input = (
        state.get("linkedin_url")
        or state.get("company_name")
        or state["user_input"]
    )
    logger.info(f"[run_linkedin_agent] Scraping LinkedIn for: '{linkedin_input}'")

    try:
        from linkedin.scraper import scrape_company
        data = asyncio.run(scrape_company(linkedin_input))

        serialized = data.model_dump(mode="json")

        updates: dict = {"linkedin_data": serialized}

        # Propagate website URL from LinkedIn data back into state
        if data.identity and data.identity.website_url and not state.get("website_url"):
            logger.info(f"[run_linkedin_agent] Website found on LinkedIn: {data.identity.website_url}")
            updates["website_url"] = data.identity.website_url

        # Set company_slug from LinkedIn data if still unknown
        if data.company_slug and not state.get("company_slug"):
            updates["company_slug"] = data.company_slug

        if data.identity and data.identity.company_name and not state.get("company_name"):
            updates["company_name"] = data.identity.company_name

        return updates

    except Exception as e:
        msg = f"run_linkedin_agent failed: {e}"
        logger.error(f"[run_linkedin_agent] {msg}", exc_info=True)
        return {"linkedin_data": None, "errors": state.get("errors", []) + [msg]}


# ---------------------------------------------------------------------------
# 7. Merge Results
# ---------------------------------------------------------------------------

def merge_results(state: AgentState) -> dict:
    """
    Combine LinkedIn and Website data into a unified company profile,
    save it to the 'company_profiles' MongoDB collection, and return it.

    LinkedIn data is treated as the authoritative source for identity fields
    when both sources have data. Website data fills gaps.
    """
    logger.info("[merge_results] Building unified company profile")

    linkedin = state.get("linkedin_data") or {}
    website = state.get("website_data") or {}
    errors = state.get("errors", [])

    linkedin_identity = linkedin.get("identity") or {}
    linkedin_bi = linkedin.get("bi_profile") or {}
    linkedin_desc = linkedin.get("description") or {}

    # Build a unified profile — LinkedIn authoritative, website fills gaps
    profile = {
        # Identity
        "company_slug": (
            state.get("company_slug")
            or linkedin.get("company_slug")
            or website.get("company_slug")
            or "unknown"
        ),
        "company_name": (
            linkedin_identity.get("company_name")
            or website.get("company_name")
            or state.get("company_name")
        ),
        "website_url": (
            linkedin_identity.get("website_url")
            or state.get("website_url")
            or website.get("website_url")
        ),
        "linkedin_url": (
            linkedin_identity.get("linkedin_url")
            or state.get("linkedin_url")
            or website.get("linkedin_url") # found from website crawl
        ),
        "industry": (
            linkedin_identity.get("industry")
            or website.get("industry")
        ),
        "headquarters": (
            linkedin_identity.get("headquarters_location")
            or website.get("headquarters")
        ),
        "company_size": linkedin_identity.get("company_size_range"),
        "founded_year": linkedin_identity.get("founded_year"),
        "tagline": linkedin_identity.get("tagline"),
        "logo_url": linkedin_identity.get("logo_url"),
        "followers_count": linkedin_identity.get("followers_count"),

        # Description
        "about_text": (
            linkedin_desc.get("about_text")
            or website.get("description")
        ),
        "mission_statement": linkedin_desc.get("mission_statement"),

        # Products & Services (merge both sources)
        "products": _merge_lists(
            [p.get("name", "") for p in (linkedin_bi.get("products_and_services") or [])],
            website.get("products", []),
        ),
        "services": website.get("services", []),
        "technology_stack": _merge_lists(
            (linkedin_bi.get("tech_stack") or {}).get("frameworks_and_tools", [])
            if linkedin_bi.get("tech_stack") else [],
            website.get("technology_stack", []),
        ),

        # People
        "leadership": [
            m.get("full_name") for m in (linkedin.get("leadership_team") or [])
            if m.get("full_name")
        ] or website.get("leadership", []),

        # Contact & Social
        "emails": website.get("emails", []),
        "phone_numbers": website.get("phone_numbers", []),
        "social_links": website.get("social_links", []),
        "locations": (
            [
                loc.get("city") or loc.get("full_address", "")
                for loc in (linkedin.get("office_locations") or [])
                if loc.get("city") or loc.get("full_address")
            ] or website.get("locations", [])
        ),

        # Business Intelligence (from LinkedIn)
        "key_differentiators": linkedin_bi.get("key_differentiators", []),
        "competitive_advantages": linkedin_bi.get("competitive_advantages", []),
        "business_challenges": [
            c.get("description") for c in (linkedin_bi.get("business_challenges") or [])
        ],
        "strategic_initiatives": [
            i.get("initiative_name") for i in (linkedin_bi.get("strategic_initiatives") or [])
        ],
        "growth_signals": [
            g.get("description") for g in (linkedin_bi.get("growth_signals") or [])
        ],
        "executive_summary": linkedin_bi.get("executive_summary"),
        "sales_talking_points": linkedin_bi.get("sales_talking_points", []),
        "ai_adoption_level": linkedin_bi.get("ai_adoption_level"),
        "digital_transformation_status": linkedin_bi.get("digital_transformation_status"),

        # Source tracking
        "data_sources": _list_data_sources(linkedin, website),
        "errors": errors,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    # Save to MongoDB
    try:
        collection = get_collection("company_profiles")
        collection.update_one(
            {"company_slug": profile["company_slug"]},
            {"$set": profile},
            upsert=True,
        )
        logger.info(f"[merge_results] Saved company_profiles for slug='{profile['company_slug']}'")
    except Exception as e:
        logger.error(f"[merge_results] Failed to save to MongoDB: {e}")
        profile["errors"] = errors + [f"merge_results save failed: {e}"]

    return {"combined_profile": profile}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _slug_from_linkedin_url(url: str) -> Optional[str]:
    """Extract company slug from a LinkedIn company URL."""
    try:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "company":
            return parts[1].lower()
    except Exception:
        pass
    return None


def _merge_lists(*lists) -> list:
    """Merge multiple lists, deduplicate, preserve order, skip empty strings."""
    seen = set()
    result = []
    for lst in lists:
        for item in (lst or []):
            if item and item not in seen:
                seen.add(item)
                result.append(item)
    return result


def _list_data_sources(linkedin: dict, website: dict) -> list:
    """Return which agents actually produced data."""
    sources = []
    if linkedin:
        sources.append("linkedin")
    if website:
        sources.append("website")
    return sources


def trigger_scrapers(state: AgentState) -> dict:
    """Pass-through node to split the flow into parallel scraping branches."""
    logger.info("[trigger_scrapers] Triggering website and linkedin agents in parallel")
    return {}
