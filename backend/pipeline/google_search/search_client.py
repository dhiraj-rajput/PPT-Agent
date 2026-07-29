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
import asyncio
import requests
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Any
from urllib.parse import urlparse, urlsplit, urlunsplit

from config.settings import settings

class ConfigurationError(Exception):
    pass

Settings = Any


from utils.db_client import get_collection
from utils.helpers import is_valid_url, setup_logger

logger = setup_logger(__name__)

LINKEDIN_HOSTS = {"linkedin.com", "www.linkedin.com", "in.linkedin.com"}
DEFAULT_TIMEOUT_SECONDS = 30

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
        result: dict[str, str | None] = {
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

    def _verify_search_result_match(self, company_name: str, url: str, title: str, snippet: str) -> bool:
        """
        Verify if the search result title, snippet, or URL is a good match for the company_name.
        """
        name_lower = company_name.lower()
        title_lower = title.lower()
        snippet_lower = snippet.lower()
        url_lower = url.lower()

        # Clean words of company name into key tokens
        words = re.sub(r'[^a-z0-9\s]+', '', name_lower).split()
        stop_words = {
            "inc", "llc", "ltd", "corp", "co", "and", "the", "for", "solutions",
            "systems", "services", "group", "company", "corporation", "association",
            "foundation", "community", "development", "international", "agency"
        }
        distinctive_tokens = [w for w in words if w not in stop_words and len(w) > 2]

        if not distinctive_tokens:
            # Edge case: all tokens are stop words (e.g. company called "International Services Group").
            # Instead of blindly returning True (which accepts any result), check if the FULL
            # company name appears as a substring in the title or snippet.
            full_name_clean = re.sub(r'\s+', ' ', name_lower).strip()
            if full_name_clean in title_lower or full_name_clean in snippet_lower:
                return True
            logger.debug(f"[Discovery] No distinctive tokens for '{company_name}' and full name not found in result — rejecting.")
            return False

        # Check domain match first (e.g. if company name has a distinct token, and domain has it too)
        domain = self._get_domain(url) or ""
        domain_lower = domain.lower()

        generic_brand_words = {
            "hope", "group", "center", "centre", "alliance", "union", "care", "trust",
            "hands", "partnership", "house", "people", "global", "national", "united"
        }

        for token in distinctive_tokens:
            if token in domain_lower and token not in generic_brand_words:
                return True

        # Otherwise, check keyword match in title or snippet
        matches = [t for t in distinctive_tokens if t in title_lower or t in snippet_lower]
        if not matches:
            return False

        # For multi-word brand names, require a higher match ratio to prevent false positives.
        # e.g. "Hope Pulse" should NOT match a result that only contains "Hope" but not "Pulse".
        if len(distinctive_tokens) >= 2:
            match_ratio = len(matches) / len(distinctive_tokens)
            # Require at least 60% of distinctive tokens to match for multi-word brands
            if match_ratio < 0.6:
                logger.debug(
                    f"[Discovery] Match ratio {match_ratio:.1%} < 60% for '{company_name}' — rejecting weak match."
                )
                return False

        return len(matches) / len(distinctive_tokens) >= 0.5

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
            title = r.get("title", "")
            snippet = r.get("content", "")
            # Skip LinkedIn, Wikipedia, social media, aggregator sites
            if url and self._is_likely_official_site(url, company_name):
                # Verify match
                if self._verify_search_result_match(company_name, url, title, snippet):
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
            title = r.get("title", "")
            snippet = r.get("content", "")
            if "linkedin.com/company/" in url:
                # Verify match
                if self._verify_search_result_match(company_name, url, title, snippet):
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
                logger.info(f"Found LinkedIn URL from pipeline.website domain: {clean_url}")
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


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A third-party web search result after source filtering."""

    title: str
    url: str
    snippet: str
    provider: str


class ExternalSearchClient:
    """Find non-official, non-LinkedIn sources for a company."""

    def __init__(self, settings: Settings, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._settings = settings
        self._timeout_seconds = timeout_seconds

    async def search_company_sources(
        self,
        *,
        company_name: str,
        official_url: str,
        max_results: int = 8,
        custom_query: str | None = None,
    ) -> list[SearchResult]:
        """Return external sources only: no LinkedIn and no official company host."""

        provider = self._choose_provider()
        official_host = _host_without_www(official_url)
        excluded_hosts = {official_host, f"www.{official_host}", *LINKEDIN_HOSTS}
        
        if custom_query:
            # Append exclusions if they aren't already in the query
            query = custom_query
            exclusions = [
                "-site:linkedin.com",
                "-site:www.linkedin.com",
                f"-site:{official_host}",
                f"-site:www.{official_host}",
            ]
            for excl in exclusions:
                if excl not in query:
                    query += f" {excl}"
        else:
            query = _build_company_query(company_name=company_name, official_host=official_host)

        if provider == "tavily":
            raw_results = await asyncio.to_thread(
                self._search_tavily,
                query,
                max_results * 2,
                sorted(excluded_hosts),
            )
        elif provider == "serpapi":
            raw_results = await asyncio.to_thread(self._search_serpapi, query, max_results * 2)
        else:
            raise ConfigurationError(f"Unsupported SEARCH_PROVIDER: {provider}")

        filtered = _filter_results(
            raw_results,
            official_host=official_host,
            provider=provider,
            max_results=max_results,
        )
        logger.info(
            "external_search_completed",
            extra={"provider": provider, "company_name": company_name, "result_count": len(filtered)},
        )
        return filtered

    def _choose_provider(self) -> str:
        requested = self._settings.search_provider
        if requested in {"tavily", "serpapi"}:
            self._validate_provider_key(requested)
            return requested
        if requested != "auto":
            raise ConfigurationError("SEARCH_PROVIDER must be one of: auto, tavily, serpapi")
        if self._settings.tavily_api_key:
            return "tavily"
        if self._settings.serpapi_api_key:
            return "serpapi"
        raise ConfigurationError("External discovery requires TAVILY_API_KEY or SERPAPI_API_KEY.")

    def _validate_provider_key(self, provider: str) -> None:
        if provider == "tavily" and not self._settings.tavily_api_key:
            raise ConfigurationError("SEARCH_PROVIDER=tavily requires TAVILY_API_KEY.")
        if provider == "serpapi" and not self._settings.serpapi_api_key:
            raise ConfigurationError("SEARCH_PROVIDER=serpapi requires SERPAPI_API_KEY.")

    def _search_tavily(self, query: str, max_results: int, excluded_domains: list[str]) -> list[dict[str, Any]]:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self._settings.tavily_api_key,
                "query": query,
                "search_depth": "advanced",
                "include_answer": False,
                "include_raw_content": False,
                "max_results": max_results,
                "exclude_domains": excluded_domains,
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            }
            for item in payload.get("results", [])
        ]

    def _search_serpapi(self, query: str, max_results: int) -> list[dict[str, Any]]:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": query,
                "num": max_results,
                "api_key": self._settings.serpapi_api_key,
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in payload.get("organic_results", [])
        ]


def _build_company_query(*, company_name: str, official_host: str) -> str:
    exclusions = [
        "-site:linkedin.com",
        "-site:www.linkedin.com",
        f"-site:{official_host}",
        f"-site:www.{official_host}",
    ]
    intent = "company business profile news financial results analysis competitors"
    return f'"{company_name}" {intent} {" ".join(exclusions)}'


def _filter_results(
    raw_results: list[dict[str, Any]],
    *,
    official_host: str,
    provider: str,
    max_results: int,
) -> list[SearchResult]:
    output: list[SearchResult] = []
    seen_urls: set[str] = set()
    for item in raw_results:
        normalized_url = _normalize_result_url(str(item.get("url", "")))
        if not normalized_url or normalized_url in seen_urls:
            continue
        host = _host_without_www(normalized_url)
        if _is_same_or_subdomain(host, official_host) or _is_linkedin_host(host):
            continue
        output.append(
            SearchResult(
                title=str(item.get("title", "")).strip(),
                url=normalized_url,
                snippet=str(item.get("snippet", "")).strip(),
                provider=provider,
            )
        )
        seen_urls.add(normalized_url)
        if len(output) >= max_results:
            break
    return output


def _normalize_result_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))


def _host_without_www(url_or_host: str) -> str:
    parsed = urlsplit(url_or_host if "://" in url_or_host else f"https://{url_or_host}")
    host = (parsed.hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _is_same_or_subdomain(host: str, root_host: str) -> bool:
    return host == root_host or host.endswith(f".{root_host}")


def _is_linkedin_host(host: str) -> bool:
    return host in LINKEDIN_HOSTS or host.endswith(".linkedin.com")
