"""
google_search/search_client.py
-------------------------------
Company discovery via Tavily search API.

Given any input (company name, website URL, LinkedIn URL), this module
finds the company's official website URL and LinkedIn company page URL.

Strategy for each input type:
  - website_url  → search for "<domain> linkedin company page" to find LinkedIn
  - company_name → search for official website, then search for LinkedIn page
  - linkedin_url → search for official website from the company name on LinkedIn

All results are cached in MongoDB ('search_cache' collection) to avoid
redundant API calls.
"""

import re
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from config.settings import settings
from utils.db_client import get_collection
from utils.helpers import is_valid_url, setup_logger

logger = setup_logger(__name__)

COLLECTION_SEARCH_CACHE = "search_cache"
TAVILY_MAX_RESULTS = 5


class CompanyDiscovery:
    """
    Discovers a company's official website URL and LinkedIn company page URL
    from any form of user input using the Tavily search API.

    Usage:
        discovery = CompanyDiscovery()

        # From company name
        result = discovery.find_all("Infosys Limited")

        # From website URL only
        result = discovery.find_all("https://infosys.com")

        # Returns:
        {
            "company_name":  "Infosys",
            "website_url":   "https://infosys.com",
            "linkedin_url":  "https://www.linkedin.com/company/infosys",
        }
    """

    def find_all(self, user_input: str) -> dict:
        """
        Main entry point: resolve any input to a dict with website_url and linkedin_url.

        Args:
            user_input: Company name, website URL, or LinkedIn URL.

        Returns:
            Dict with keys: company_name, website_url, linkedin_url.
            Any key can be None if not found.
        """
        cleaned = user_input.strip()
        result = {
            "company_name": None,
            "website_url": None,
            "linkedin_url": None,
        }

        if self._is_linkedin_url(cleaned):
            # Input IS the LinkedIn URL — just need to find the website
            result["linkedin_url"] = self._normalize_linkedin_url(cleaned)
            company_name = self._extract_name_from_linkedin_url(cleaned)
            result["company_name"] = company_name
            if company_name:
                result["website_url"] = self.find_official_website(company_name)

        elif is_valid_url(cleaned) and "linkedin.com" not in cleaned:
            # Input is a website URL — find the LinkedIn page
            result["website_url"] = cleaned
            domain = self._get_domain(cleaned)
            result["company_name"] = domain.split(".")[0].capitalize() if domain else None
            result["linkedin_url"] = self.find_linkedin_from_website(cleaned)

        else:
            # Input is a company name
            result["company_name"] = cleaned
            result["website_url"] = self.find_official_website(cleaned)
            result["linkedin_url"] = self.find_linkedin_url(cleaned)

        logger.info(
            f"Discovery result for '{cleaned}': "
            f"website={result['website_url']} | linkedin={result['linkedin_url']}"
        )
        return result

    # ---------------------------------------------------------------------------
    # Public search methods
    # ---------------------------------------------------------------------------

    def find_official_website(self, company_name: str) -> Optional[str]:
        """
        Search for a company's official website using Tavily.

        Args:
            company_name: Plain-text company name, e.g. "Infosys Limited".

        Returns:
            The official website URL string, or None if not found.
        """
        query = f'"{company_name}" official website'
        cached = self._get_cached(query)
        if cached:
            return cached.get("website_url")

        results = self._tavily_search(query)
        for r in results:
            url = r.get("url", "")
            # Skip LinkedIn, Wikipedia, social media, aggregator sites
            if url and self._is_likely_official_site(url, company_name):
                self._save_cache(query, {"website_url": url})
                logger.info(f"Found official website: {url} (query='{query}')")
                return url

        logger.warning(f"Could not find official website for: {company_name}")
        return None

    def find_linkedin_url(self, company_name: str) -> Optional[str]:
        """
        Search for a company's LinkedIn page URL using Tavily.

        Args:
            company_name: Plain-text company name.

        Returns:
            LinkedIn company page URL, or None if not found.
        """
        query = f'site:linkedin.com/company "{company_name}" official company page'
        cached = self._get_cached(query)
        if cached:
            return cached.get("linkedin_url")

        results = self._tavily_search(query)
        for r in results:
            url = r.get("url", "")
            if "linkedin.com/company/" in url:
                clean_url = self._normalize_linkedin_url(url)
                self._save_cache(query, {"linkedin_url": clean_url})
                logger.info(f"Found LinkedIn URL: {clean_url} (query='{query}')")
                return clean_url

        logger.warning(f"Could not find LinkedIn URL for: {company_name}")
        return None

    def find_linkedin_from_website(self, website_url: str) -> Optional[str]:
        """
        Find a company's LinkedIn page by searching with the website domain.

        Args:
            website_url: The company's official website URL.

        Returns:
            LinkedIn company page URL, or None if not found.
        """
        domain = self._get_domain(website_url)
        if not domain:
            return None

        query = f'site:linkedin.com/company "{domain}" company page'
        cached = self._get_cached(query)
        if cached:
            return cached.get("linkedin_url")

        results = self._tavily_search(query)
        for r in results:
            url = r.get("url", "")
            if "linkedin.com/company/" in url:
                clean_url = self._normalize_linkedin_url(url)
                self._save_cache(query, {"linkedin_url": clean_url})
                logger.info(f"Found LinkedIn URL from website domain: {clean_url}")
                return clean_url

        logger.warning(f"Could not find LinkedIn URL for website: {website_url}")
        return None

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    def _tavily_search(self, query: str) -> list:
        """Run a Tavily search and return a list of result dicts."""
        if not settings.is_tavily_search_enabled:
            logger.warning("TAVILY_API_KEY is not set — cannot search. Add it to .env")
            return []

        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=settings.TAVILY_API_KEY)
            logger.info(f"Tavily search: '{query}'")
            response = client.search(
                query=query,
                max_results=TAVILY_MAX_RESULTS,
                search_depth="basic",
            )
            return response.get("results", [])
        except Exception as e:
            logger.error(f"Tavily search failed for '{query}': {e}")
            return []

    def _is_likely_official_site(self, url: str, company_name: str) -> bool:
        """
        Heuristic: return True if the URL looks like the company's own website.
        Excludes LinkedIn, Wikipedia, social media, aggregator sites.
        """
        EXCLUDED = [
            "linkedin.com", "wikipedia.org", "crunchbase.com", "bloomberg.com",
            "twitter.com", "facebook.com", "instagram.com", "youtube.com",
            "glassdoor.com", "indeed.com", "zoominfo.com", "dnb.com",
            "owler.com", "pitchbook.com", "techcrunch.com", "forbes.com",
        ]
        url_lower = url.lower()
        if any(ex in url_lower for ex in EXCLUDED):
            return False
        if not is_valid_url(url):
            return False
        return True

    def _is_linkedin_url(self, text: str) -> bool:
        if not is_valid_url(text):
            return False
        return "linkedin.com" in urlparse(text).netloc

    def _normalize_linkedin_url(self, url: str) -> str:
        """Strip query params and trailing slashes from a LinkedIn URL."""
        parsed = urlparse(url)
        clean_path = parsed.path.rstrip("/")
        return f"https://www.linkedin.com{clean_path}"

    def _extract_name_from_linkedin_url(self, url: str) -> Optional[str]:
        """Extract company slug from a linkedin.com/company/<slug> URL and humanize it."""
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "company":
            slug = parts[1]
            return slug.replace("-", " ").title()
        return None

    def _get_domain(self, url: str) -> str:
        """Return the bare domain (no www) from a URL."""
        try:
            domain = urlparse(url).netloc
            return domain[4:] if domain.startswith("www.") else domain
        except Exception:
            return ""

    # ---------------------------------------------------------------------------
    # MongoDB cache helpers
    # ---------------------------------------------------------------------------

    def _get_cached(self, query: str) -> Optional[dict]:
        """Look up a cached search result by query string."""
        try:
            collection = get_collection(COLLECTION_SEARCH_CACHE)
            doc = collection.find_one({"query": query})
            if doc:
                logger.debug(f"Cache hit for query: '{query}'")
                return doc.get("result")
        except Exception:
            pass
        return None

    def _save_cache(self, query: str, result: dict) -> None:
        """Cache a search result keyed by query string."""
        try:
            collection = get_collection(COLLECTION_SEARCH_CACHE)
            collection.update_one(
                {"query": query},
                {"$set": {"query": query, "result": result, "cached_at": datetime.now(tz=timezone.utc)}},
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"Failed to cache search result: {e}")
