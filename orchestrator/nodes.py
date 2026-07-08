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

        # External News
        "external_news": state.get("external_news") or [],

        # External structured insights (LLM-processed competitor/financial profile)
        "external_structured_insights": state.get("external_structured_insights") or {},

        # Competitors surfaced from external search
        "competitors": (
            (state.get("external_structured_insights") or {}).get("competitors", [])
        ),

        # Source tracking
        "data_sources": _list_data_sources(linkedin, website, state.get("external_news")),
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


def _list_data_sources(linkedin: dict, website: dict, external_news: list | None) -> list:
    """Return which agents actually produced data."""
    sources = []
    if linkedin:
        sources.append("linkedin")
    if website:
        sources.append("website")
    if external_news:
        sources.append("news")
    return sources


def trigger_scrapers(state: AgentState) -> dict:
    """Pass-through node to split the flow into parallel scraping branches."""
    logger.info("[trigger_scrapers] Triggering website and linkedin agents in parallel")
    return {}


def discover_external_news(state: AgentState) -> dict:
    """
    Search external platforms (TechCrunch, Medium, press releases, etc.)
    for news, financials, and competitor updates about the company in parallel.
    Saves raw search results to 'raw_external_search' and structured LLM extraction to 'structured_external_search'.

    Fix: Falls back to domain name when company_name is None (e.g. for website_url inputs
    that run this node in parallel with run_website_agent, before the name is known).
    """
    import time
    import json
    start_time = time.time()
    company_name = state.get("company_name")
    official_url = state.get("website_url")
    company_slug = state.get("company_slug") or "unknown"

    # Fall back to domain name if company_name is not yet resolved (parallel execution)
    if not company_name and official_url:
        from urllib.parse import urlparse
        netloc = urlparse(official_url).netloc.replace("www.", "")
        company_name = netloc.split(".")[0].capitalize() if netloc else None
        if company_name:
            logger.info(f"[discover_external_news] company_name not set — using domain fallback: '{company_name}'")

    if not company_name or not official_url:
        logger.warning("[discover_external_news] Missing company_name and website_url; skipping news search.")
        return {}

    logger.info(f"[discover_external_news] Searching detailed external news and financials for: '{company_name}'")

    from google_search import ExternalSearchClient
    from config.settings import settings
    from utils.db_client import get_collection

    search_client = ExternalSearchClient(settings)

    # 1. Fetch raw search results across multiple targeted queries in parallel
    try:
        import asyncio

        async def fetch_all_searches():
            tasks = [
                search_client.search_company_sources(
                    company_name=company_name,
                    official_url=official_url,
                    max_results=5,
                    custom_query=f'"{company_name}" latest news press release OR announcement 2026'
                ),
                search_client.search_company_sources(
                    company_name=company_name,
                    official_url=official_url,
                    max_results=5,
                    custom_query=f'"{company_name}" revenue growth profit financial results 2025 OR 2026'
                ),
                search_client.search_company_sources(
                    company_name=company_name,
                    official_url=official_url,
                    max_results=5,
                    custom_query=f'"{company_name}" key competitors market share SWOT analysis'
                ),
                search_client.search_company_sources(
                    company_name=company_name,
                    official_url=official_url,
                    max_results=5,
                    custom_query=f'"{company_name}" RFP tender government contract win 2024 OR 2025 OR 2026'
                ),
            ]
            return await asyncio.gather(*tasks)

        results_lists = asyncio.run(fetch_all_searches())

        # Merge and deduplicate by URL
        seen_urls = set()
        deduped_results = []
        for lst in results_lists:
            for r in lst:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    deduped_results.append(r)

        raw_results = [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "provider": r.provider
            }
            for r in deduped_results
        ]

        # Save raw search results to 'raw_external_search'
        raw_collection = get_collection("raw_external_search")
        raw_record = {
            "company_slug": company_slug,
            "company_name": company_name,
            "search_results": raw_results,
            "scraped_at": datetime.now(tz=timezone.utc)
        }
        raw_collection.insert_one(raw_record)
        logger.info(f"[discover_external_news] Saved raw search data to 'raw_external_search' collection.")

        if not raw_results:
            logger.info("[discover_external_news] No news results found.")
            # Log successful but empty operation to scrape_logs
            logs_collection = get_collection("scrape_logs")
            logs_collection.insert_one({
                "company_slug": company_slug,
                "agent_name": "external_search",
                "status": "success",
                "duration_seconds": round(time.time() - start_time, 2),
                "timestamp": datetime.now(tz=timezone.utc)
            })
            return {"external_news": []}

        if not settings.USE_LLM_STRUCTURING:
            logger.info("[discover_external_news] USE_LLM_STRUCTURING is False. Running rule-based structured search profiling.")
            insights = []
            for r in raw_results[:6]:
                snippet_lower = r["snippet"].lower()
                category = "General News"
                if any(x in snippet_lower for x in ["revenue", "profit", "growth", "funding", "valuation", "financial"]):
                    category = "Financial Health"
                elif any(x in snippet_lower for x in ["competitor", "market share", "beat", "swot", "rival"]):
                    category = "Competitor Intelligence"
                elif any(x in snippet_lower for x in ["rfp", "tender", "contract", "win"]):
                    category = "RFP / Contract Win"
                elif any(x in snippet_lower for x in ["product", "launch", "feature", "release"]):
                    category = "Product Release"

                insights.append({
                    "category": category,
                    "description": r["snippet"],
                    "source_url": r["url"],
                    "confidence_score": 0.8
                })

            structured_profile = {
                "company_name": company_name,
                "website": official_url,
                "business_model": f"Core business model for {company_name} extracted from search snippets.",
                "value_proposition": f"Value proposition for {company_name} extracted from search snippets.",
                "products_and_services": [],
                "insights": insights,
                "company_slug": company_slug,
                "scraped_at": datetime.now(tz=timezone.utc).isoformat()
            }
        else:
            # 2. Run LLM structuring pass (using dict config to resolve Pylance parameter warnings)
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                **{
                    "openai_api_key": settings.OPENROUTER_API_KEY,
                    "openai_api_base": settings.OPENROUTER_BASE_URL,
                    "model_name": settings.OPENROUTER_MODEL,
                    "max_tokens": 2000,
                },
                temperature=0.0,
                timeout=45.0
            )

            prompt = f"""You are a professional business intelligence and research analyst.
Analyze the following raw search snippets about the company '{company_name}' and extract a structured company research profile.
This profile is for RFP (Request for Proposal) research.

Search Snippets:
{json.dumps(raw_results, indent=2)}

Produce a JSON object strictly matching this schema:
{{
  "company_name": "{company_name}",
  "website": "{official_url}",
  "business_model": "Summarize the company's core business model in one sentence.",
  "value_proposition": "Summarize the company's value proposition in one sentence.",
  "products_and_services": [
    {{
      "name": "Product or service name",
      "description": "Short description of what it does",
      "target_audience": "Target audience or null"
    }}
  ],
  "insights": [
    {{
      "category": "E.g., Financial Health, Operational Efficiency, Strategic Pivot, Capital Allocation, Market Growth, etc.",
      "description": "Factual insight detailing numbers, margins, buybacks, pivots, or performance from the snippets",
      "source_url": "The exact URL from the snippet supporting this insight",
      "confidence_score": 1.0
    }}
  ]
}}

Ensure all fields are derived directly from the snippets. Provide a minimum of 4-6 detailed insights covering financial metrics, competitor comparisons, strategic pivots, and latest announcements. The insights must contain specific numbers, growth rates, dates, or competitor names from the snippets where possible. Do not output anything other than a valid JSON object.
"""

            logger.info("[discover_external_news] Invoking LLM for structured search profiling...")
            response = llm.invoke(prompt)
            content = str(response.content).strip()

            # Clean potential markdown wrappers
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            structured_profile = json.loads(content)
            structured_profile["company_slug"] = company_slug
            structured_profile["scraped_at"] = datetime.now(tz=timezone.utc).isoformat()

        # Save structured profile to 'structured_external_search'
        struct_collection = get_collection("structured_external_search")
        struct_collection.update_one(
            {"company_slug": company_slug},
            {"$set": structured_profile},
            upsert=True
        )
        logger.info(f"[discover_external_news] Saved structured search data to 'structured_external_search' collection.")

        # Log operation to scrape_logs
        logs_collection = get_collection("scrape_logs")
        logs_collection.insert_one({
            "company_slug": company_slug,
            "agent_name": "external_search",
            "status": "success",
            "duration_seconds": round(time.time() - start_time, 2),
            "timestamp": datetime.now(tz=timezone.utc)
        })

        return {
            "external_news": raw_results,
            "external_structured_insights": structured_profile
        }

    except Exception as e:
        logger.error(f"[discover_external_news] Search failed: {e}")
        # Log failure to scrape_logs
        try:
            logs_collection = get_collection("scrape_logs")
            logs_collection.insert_one({
                "company_slug": company_slug,
                "agent_name": "external_search",
                "status": "failed",
                "duration_seconds": round(time.time() - start_time, 2),
                "error_message": str(e),
                "timestamp": datetime.now(tz=timezone.utc)
            })
        except Exception:
            pass
        return {"errors": state.get("errors", []) + [f"discover_external_news failed: {e}"]}


# ---------------------------------------------------------------------------
# 10. Compactor Node — Final RFP / Competitor Intelligence Profile
# ---------------------------------------------------------------------------

def run_compactor(state: AgentState) -> dict:
    """
    Final pipeline step: compact outputs from all three agents into a single
    OptimizedCompanyProfile using the LLM-powered BusinessIntelligenceCompactor.

    Inputs consumed:
        - website_data              (from run_website_agent)
        - linkedin_data             (from run_linkedin_agent)
        - external_news             (raw search snippets from discover_external_news)
        - external_structured_insights  (LLM-structured profile from discover_external_news)

    Outputs:
        - optimized_profile         (dict matching OptimizedCompanyProfile schema)

    The profile is also persisted to:
        - MongoDB: company_profiles collection (upsert by website)
        - Disk:    output/company_profile.json
                   output/json/<domain>_profile.json
    """
    logger.info("[run_compactor] Building OptimizedCompanyProfile from all agent outputs")

    website_data = state.get("website_data") or {}
    linkedin_data = state.get("linkedin_data") or {}
    external_insights = state.get("external_structured_insights") or {}

    # Build google_data from raw external news snippets + business model summary
    google_data: dict = {"results": state.get("external_news") or []}
    if external_insights.get("business_model"):
        google_data["summary"] = external_insights["business_model"]

    try:
        from models.compactor import BusinessIntelligenceCompactor
        compactor = BusinessIntelligenceCompactor()
        result = compactor.compact_from_dicts(
            website_data=website_data,
            linkedin_data=linkedin_data,
            google_data=google_data,
            external_insights=external_insights,
        )
        profile = result.get("profile") or {}

        # Smart fallback: if the compactor failed validation (lacks required fields like company_name),
        # merge the raw combined_profile from state to ensure we don't return an empty profile.
        combined = state.get("combined_profile") or {}
        if (not profile.get("company_name") or not profile.get("website")) and combined.get("company_name"):
            logger.warning("[run_compactor] Compacted profile failed validation or was empty. Overlaying combined_profile.")
            # Merge combined_profile into profile to keep the uncompacted data as fallback
            for k, v in combined.items():
                if v and not profile.get(k):
                    profile[k] = v

        logger.info(
            f"[run_compactor] Profile compiled for '{profile.get('company_name', 'unknown')}' "
            f"| MongoDB={'saved' if result.get('mongodb_stored') else 'skipped'}"
        )
        return {"optimized_profile": profile}

    except Exception as exc:
        msg = f"run_compactor failed: {exc}"
        logger.error(f"[run_compactor] {msg}", exc_info=True)
        return {
            "optimized_profile": None,
            "errors": state.get("errors", []) + [msg],
        }
