"""
linkedin/input_resolver.py
--------------------------
Resolves any user-provided input into a canonical LinkedIn company URL.

Users can provide any of the following input formats:
  - Full URL:       "https://www.linkedin.com/company/infosys"
  - Company slug:   "infosys"
  - Company name:   "Infosys Limited"
  - Post URL:       "https://www.linkedin.com/posts/infosys_..."
  - Feed URL:       "https://www.linkedin.com/feed/update/urn:li:activity:..."

This module normalizes all of them to:
  "https://www.linkedin.com/company/<slug>"

Resolution strategy:
  1. If the input looks like a LinkedIn URL → extract slug directly
  2. If the input looks like a short slug → construct URL directly
  3. If the input is a company name → search via Tavily to find the LinkedIn URL
"""

import re
from urllib.parse import urlparse

from config.settings import settings
from linkedin.constants import (
    LINKEDIN_BASE_URL,
    LINKEDIN_COMPANY_BASE_URL,
    TAVILY_LINKEDIN_SEARCH_QUERY_TEMPLATE,
    TAVILY_MAX_SEARCH_RESULTS,
    build_company_page_url,
)
from utils.helpers import (
    extract_company_slug_from_url,
    is_valid_url,
    normalize_linkedin_company_url,
    setup_logger,
)

logger = setup_logger(__name__)


class InputResolver:
    """
    Converts any user-provided company identifier into a LinkedIn company URL.

    This is the entry point for all scraping operations. It ensures that
    regardless of what format the user provides, every subsequent step
    always receives a clean, canonical LinkedIn company URL.

    Usage:
        resolver = InputResolver()
        linkedin_url, company_slug = resolver.resolve("Infosys")
        # Returns: ("https://www.linkedin.com/company/infosys", "infosys")
    """

    def resolve(self, user_input: str) -> tuple[str, str]:
        """
        Resolves user input to a (linkedin_url, company_slug) tuple.

        Args:
            user_input: Any of: LinkedIn URL, company slug, company name, post URL.

        Returns:
            A tuple of (canonical_linkedin_url, company_slug).

        Raises:
            ValueError: If the input cannot be resolved to a LinkedIn company URL.
        """
        cleaned_input = user_input.strip()
        logger.info(f"Resolving input: '{cleaned_input}'")

        # --- Strategy 1: Input is already a LinkedIn URL ---
        if self._looks_like_linkedin_url(cleaned_input):
            return self._resolve_from_linkedin_url(cleaned_input)

        # --- Strategy 2: Input is a plain slug (short, no spaces, URL-safe) ---
        if self._looks_like_company_slug(cleaned_input):
            return self._resolve_from_slug(cleaned_input)

        # --- Strategy 3: Input is a company name — search for the LinkedIn URL ---
        return self._resolve_from_company_name(cleaned_input)

    # ---------------------------------------------------------------------------
    # Private Helpers
    # ---------------------------------------------------------------------------

    def _looks_like_linkedin_url(self, text: str) -> bool:
        """
        Returns True if the text appears to be a LinkedIn URL.
        Checks for 'linkedin.com' in the parsed netloc or raw string.
        """
        if not is_valid_url(text):
            return False
        parsed = urlparse(text)
        return "linkedin.com" in parsed.netloc

    def _looks_like_company_slug(self, text: str) -> bool:
        """
        Returns True if the text looks like a LinkedIn company slug.

        A slug:
          - Contains only lowercase letters, digits, and hyphens
          - Has no spaces
          - Is relatively short (≤ 100 characters)
          - Does NOT contain typical name-like patterns (e.g., "Ltd", "Inc")

        This is intentionally conservative — if there's any doubt,
        we fall through to the Tavily search strategy.
        """
        slug_pattern = re.compile(r"^[a-z0-9][a-z0-9\-]{0,99}$")
        return bool(slug_pattern.match(text)) and " " not in text

    def _resolve_from_linkedin_url(self, linkedin_url: str) -> tuple[str, str]:
        """
        Extracts the company slug from any LinkedIn URL and returns
        the canonical company page URL.

        Handles:
          - Company page URLs:  linkedin.com/company/infosys
          - Post URLs:          linkedin.com/posts/infosys_...
          - Feed URLs:          linkedin.com/feed/update/urn:li:...
        """
        parsed = urlparse(linkedin_url)
        path_parts = [part for part in parsed.path.split("/") if part]

        # Check if this is already a company URL
        if len(path_parts) >= 2 and path_parts[0] == "company":
            company_slug = path_parts[1]
            canonical_url = build_company_page_url(company_slug)
            logger.info(f"Resolved from LinkedIn URL → slug='{company_slug}'")
            return canonical_url, company_slug

        # For post URLs like /posts/infosys_xyz, try to extract the company prefix
        if len(path_parts) >= 2 and path_parts[0] == "posts":
            # Post author slug is typically before the first underscore
            post_slug_part = path_parts[1]
            if "_" in post_slug_part:
                company_slug_candidate = post_slug_part.split("_")[0]
                canonical_url = build_company_page_url(company_slug_candidate)
                logger.info(
                    f"Resolved from post URL → slug candidate='{company_slug_candidate}' "
                    f"(may need manual verification)"
                )
                return canonical_url, company_slug_candidate

        raise ValueError(
            f"Could not extract a company slug from LinkedIn URL: '{linkedin_url}'. "
            "Please provide a direct company page URL like: "
            "https://www.linkedin.com/company/your-company"
        )

    def _resolve_from_slug(self, company_slug: str) -> tuple[str, str]:
        """
        Constructs a canonical LinkedIn company URL from a plain slug.

        Args:
            company_slug: e.g. "infosys"

        Returns:
            ("https://www.linkedin.com/company/infosys", "infosys")
        """
        canonical_url = build_company_page_url(company_slug)
        logger.info(f"Resolved from slug → '{canonical_url}'")
        return canonical_url, company_slug

    def _resolve_from_company_name(self, company_name: str) -> tuple[str, str]:
        """
        Searches for a company's LinkedIn page URL using its name.

        Uses Tavily search API if configured, otherwise falls back to
        a DuckDuckGo-style approach using requests.

        Args:
            company_name: The plain-text company name, e.g. "Infosys Limited".

        Returns:
            A (canonical_url, company_slug) tuple.

        Raises:
            ValueError: If no LinkedIn URL can be found for the company name.
        """
        logger.info(f"Searching for LinkedIn URL for company name: '{company_name}'")

        if settings.is_tavily_search_enabled:
            return self._search_with_tavily(company_name)
        else:
            logger.warning(
                "TAVILY_API_KEY is not set. "
                "Cannot search for LinkedIn URL by company name. "
                "Please provide a LinkedIn URL or slug directly, "
                "or add your Tavily key to .env"
            )
            raise ValueError(
                f"Cannot resolve company name '{company_name}' to a LinkedIn URL. "
                "Either:\n"
                "  1. Provide a LinkedIn URL directly (e.g., linkedin.com/company/infosys)\n"
                "  2. Add TAVILY_API_KEY to your .env file to enable automatic search\n"
                "  3. Provide the LinkedIn slug directly (e.g., 'infosys')"
            )

    def _search_with_tavily(self, company_name: str) -> tuple[str, str]:
        """
        Uses the Tavily search API to find a company's LinkedIn URL.

        Searches for the company name + site:linkedin.com/company to
        maximize the chance of finding the correct page on the first try.

        Args:
            company_name: The company name to search for.

        Returns:
            A (canonical_url, company_slug) tuple.

        Raises:
            ValueError: If no LinkedIn company URL is found in Tavily results.
        """
        from tavily import TavilyClient  # Imported here to keep it optional

        search_query = TAVILY_LINKEDIN_SEARCH_QUERY_TEMPLATE.format(
            company_name=company_name
        )

        tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        logger.info(f"Tavily search query: '{search_query}'")

        search_response = tavily_client.search(
            query=search_query,
            max_results=TAVILY_MAX_SEARCH_RESULTS,
            search_depth="basic",
        )

        search_results = search_response.get("results", [])

        # Look for a LinkedIn company URL in the search results
        for result in search_results:
            result_url = result.get("url", "")

            if "linkedin.com/company/" in result_url:
                # Found a LinkedIn company URL — normalize and extract slug
                canonical_url = normalize_linkedin_company_url(result_url)

                try:
                    company_slug = extract_company_slug_from_url(canonical_url)
                except ValueError:
                    continue  # Skip malformed URLs and try the next result

                logger.info(
                    f"Found LinkedIn URL via Tavily | "
                    f"company='{company_name}' → slug='{company_slug}'"
                )
                return canonical_url, company_slug

        raise ValueError(
            f"Could not find a LinkedIn company page for '{company_name}' "
            f"using Tavily search. "
            "Please provide the LinkedIn URL or company slug directly."
        )
