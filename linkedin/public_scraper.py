"""
linkedin/public_scraper.py
--------------------------
Layer 1: Public page scraping — no LinkedIn account required.

This is the fastest, safest scraping layer. It fetches the company page
HTML without a browser (just requests), then extracts:

  1. JSON-LD structured data (machine-readable metadata embedded by LinkedIn)
  2. Open Graph <meta> tags (og:title, og:description, og:image)
  3. Standard <meta> tags (name, description)

JSON-LD is the most reliable source because it's generated server-side
and has a consistent structure. Meta tags are a useful fallback.

Note: This layer provides limited data compared to Layers 2 and 3.
LinkedIn returns a login wall or minimal HTML for many fields when
the request is not authenticated. The Crawl4AI layer handles the rest.
"""

import json
import random
from typing import Optional

import requests
from bs4 import BeautifulSoup

from linkedin.constants import (
    LINKEDIN_COMPANY_BASE_URL,
    PUBLIC_REQUEST_HEADERS,
    SCRAPE_LAYER_PUBLIC,
    USER_AGENT_POOL,
    build_company_about_url,
    build_company_page_url,
)
from linkedin.models import CompanyIdentity, RawLinkedInScrapedData
from utils.helpers import get_utc_now, retry_on_network_error, setup_logger, wait_random_delay

logger = setup_logger(__name__)

# Timeout for HTTP requests in seconds
HTTP_REQUEST_TIMEOUT_SECONDS = 15


class PublicLinkedInScraper:
    """
    Layer 1 scraper: fetches publicly visible LinkedIn company data
    using only standard HTTP requests (no browser, no login).

    This layer runs first and is always used, even when Crawl4AI or
    authenticated scraping is also enabled. It provides a fast baseline.

    Usage:
        scraper = PublicLinkedInScraper()
        raw_data, partial_identity = scraper.scrape(
            company_slug="infosys",
            linkedin_url="https://www.linkedin.com/company/infosys"
        )
    """

    def scrape(
        self,
        company_slug: str,
        linkedin_url: str,
    ) -> tuple[RawLinkedInScrapedData, Optional[CompanyIdentity]]:
        """
        Fetches and parses public data from the LinkedIn company page.

        Args:
            company_slug:  The LinkedIn slug, e.g. "infosys".
            linkedin_url:  Canonical company URL to scrape.

        Returns:
            A tuple of:
              - RawLinkedInScrapedData: The full raw scrape record (for MongoDB storage).
              - CompanyIdentity | None: Partial identity data if extraction succeeded,
                                       otherwise None.
        """
        logger.info(f"[Layer 1 - Public] Scraping: {linkedin_url}")

        page_html, fetch_error = self._fetch_page_html(linkedin_url)

        if page_html is None:
            logger.warning(f"[Layer 1] Failed to fetch page: {fetch_error}")
            raw_record = RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_PUBLIC,
                page_url=linkedin_url,
                scraped_at=get_utc_now(),
                scrape_success=False,
                error_message=fetch_error,
            )
            return raw_record, None

        # Parse the HTML
        soup = BeautifulSoup(page_html, "lxml")
        json_ld_data = self._extract_json_ld(soup)
        meta_tags = self._extract_meta_tags(soup)

        # Build the raw record for MongoDB storage
        raw_record = RawLinkedInScrapedData(
            company_slug=company_slug,
            scrape_layer=SCRAPE_LAYER_PUBLIC,
            page_url=linkedin_url,
            raw_html=page_html[:50_000],   # Store first 50KB of HTML (for debugging)
            raw_text=soup.get_text(separator=" ", strip=True)[:20_000],
            json_ld_data=json_ld_data,
            meta_tags=meta_tags,
            scraped_at=get_utc_now(),
            scrape_success=True,
        )

        # Extract structured identity data from the parsed content
        partial_identity = self._extract_company_identity(
            company_slug=company_slug,
            linkedin_url=linkedin_url,
            json_ld_data=json_ld_data,
            meta_tags=meta_tags,
        )

        logger.info(
            f"[Layer 1] Success | company='{company_slug}' "
            f"| json_ld_found={json_ld_data is not None} "
            f"| meta_tags_found={len(meta_tags)}"
        )

        return raw_record, partial_identity

    # ---------------------------------------------------------------------------
    # HTTP Fetching
    # ---------------------------------------------------------------------------

    @retry_on_network_error(max_attempts=3)
    def _fetch_page_html(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """
        Fetches the HTML content of a page via HTTP GET.

        Rotates User-Agent strings and includes realistic browser headers
        to minimize the chance of being blocked.

        Returns:
            (html_content, None) on success.
            (None, error_message) on failure.
        """
        # Pick a random User-Agent from the pool for each request
        selected_user_agent = random.choice(USER_AGENT_POOL)
        request_headers = {**PUBLIC_REQUEST_HEADERS, "User-Agent": selected_user_agent}

        wait_random_delay()

        try:
            response = requests.get(
                url,
                headers=request_headers,
                timeout=HTTP_REQUEST_TIMEOUT_SECONDS,
                allow_redirects=True,
            )

            if response.status_code == 200:
                return response.text, None

            if response.status_code == 429:
                logger.warning(f"Rate limited by LinkedIn (429). URL: {url}")
                return None, "Rate limited (HTTP 429)"

            if response.status_code in (401, 403):
                logger.warning(
                    f"Access denied (HTTP {response.status_code}). "
                    "LinkedIn may require authentication for this page."
                )
                return None, f"Access denied (HTTP {response.status_code})"

            return None, f"Unexpected HTTP status: {response.status_code}"

        except requests.exceptions.Timeout:
            return None, f"Request timed out after {HTTP_REQUEST_TIMEOUT_SECONDS}s"
        except requests.exceptions.ConnectionError as connection_error:
            return None, f"Connection error: {connection_error}"

    # ---------------------------------------------------------------------------
    # JSON-LD Extraction
    # ---------------------------------------------------------------------------

    def _extract_json_ld(self, soup: BeautifulSoup) -> Optional[dict]:
        """
        Extracts structured JSON-LD data from the page.

        LinkedIn embeds JSON-LD in <script type="application/ld+json"> tags.
        This data typically contains the company name, URL, description,
        industry, and other core details in a machine-readable format.

        Returns:
            A dict of JSON-LD data if found, otherwise None.
        """
        json_ld_script_tags = soup.find_all("script", {"type": "application/ld+json"})

        for script_tag in json_ld_script_tags:
            raw_json_text = script_tag.string
            if not raw_json_text:
                continue

            try:
                parsed_json = json.loads(raw_json_text.strip())

                # LinkedIn's JSON-LD is typically @type: Organization or similar
                if isinstance(parsed_json, dict) and parsed_json.get("@type"):
                    logger.debug(
                        f"Found JSON-LD block with @type='{parsed_json.get('@type')}'"
                    )
                    return parsed_json

                # Sometimes it's a list of objects — return the first Organization
                if isinstance(parsed_json, list):
                    for item in parsed_json:
                        if isinstance(item, dict) and item.get("@type") == "Organization":
                            return item

            except json.JSONDecodeError:
                continue  # Skip malformed JSON blocks

        logger.debug("No valid JSON-LD found on the page.")
        return None

    # ---------------------------------------------------------------------------
    # Meta Tag Extraction
    # ---------------------------------------------------------------------------

    def _extract_meta_tags(self, soup: BeautifulSoup) -> dict[str, str]:
        """
        Extracts all relevant <meta> tags from the page into a flat dict.

        Prioritizes Open Graph tags (og:title, og:description, og:image)
        which LinkedIn populates reliably for company pages.

        Returns:
            A dict mapping tag names/properties to their content values.
            e.g. {"og:title": "Infosys | LinkedIn", "og:description": "..."}
        """
        meta_data: dict[str, str] = {}

        for meta_tag in soup.find_all("meta"):
            # Open Graph properties (e.g., og:title, og:description, og:image)
            og_property = meta_tag.get("property", "")
            if og_property.startswith("og:"):
                content = meta_tag.get("content", "").strip()
                if content:
                    meta_data[og_property] = content

            # Standard named meta tags (e.g., name="description")
            meta_name = meta_tag.get("name", "")
            if meta_name in ("description", "keywords", "author"):
                content = meta_tag.get("content", "").strip()
                if content:
                    meta_data[meta_name] = content

        return meta_data

    # ---------------------------------------------------------------------------
    # Structured Data Extraction
    # ---------------------------------------------------------------------------

    def _extract_company_identity(
        self,
        company_slug: str,
        linkedin_url: str,
        json_ld_data: Optional[dict],
        meta_tags: dict[str, str],
    ) -> Optional[CompanyIdentity]:
        """
        Builds a partial CompanyIdentity object from JSON-LD and meta tags.

        Not all fields will be populated from this layer — Crawl4AI (Layer 2)
        will fill in the remaining details.

        Returns:
            A CompanyIdentity object with whatever data was extractable,
            or None if not even the company name could be determined.
        """
        company_name = None
        website_url = None
        logo_url = None
        description_text = None
        industry = None

        # --- Try JSON-LD first (most reliable) ---
        if json_ld_data:
            company_name = json_ld_data.get("name") or json_ld_data.get("legalName")
            website_url = json_ld_data.get("url")
            logo_url = self._extract_logo_from_json_ld(json_ld_data)
            description_text = json_ld_data.get("description")
            industry = json_ld_data.get("industry")

        # --- Fall back to meta tags ---
        if not company_name:
            og_title = meta_tags.get("og:title", "")
            # LinkedIn og:title format: "Company Name | LinkedIn"
            if " | LinkedIn" in og_title:
                company_name = og_title.replace(" | LinkedIn", "").strip()
            elif og_title:
                company_name = og_title.strip()

        if not description_text:
            description_text = (
                meta_tags.get("og:description")
                or meta_tags.get("description")
            )

        if not logo_url:
            logo_url = meta_tags.get("og:image")

        if not company_name:
            logger.warning(
                f"[Layer 1] Could not extract company name for slug='{company_slug}'. "
                "Layer 2 (Crawl4AI) will attempt to get this data."
            )
            return None

        return CompanyIdentity(
            company_name=company_name,
            linkedin_url=linkedin_url,
            company_slug=company_slug,
            website_url=website_url,
            logo_url=logo_url,
            industry=industry,
        )

    def _extract_logo_from_json_ld(self, json_ld_data: dict) -> Optional[str]:
        """
        Extracts the company logo URL from JSON-LD data.

        The logo can appear in several forms in JSON-LD:
          - {"logo": "https://..."}
          - {"logo": {"@type": "ImageObject", "url": "https://..."}}
          - {"image": "https://..."}
        """
        logo = json_ld_data.get("logo")

        if isinstance(logo, str):
            return logo

        if isinstance(logo, dict):
            return logo.get("url") or logo.get("contentUrl")

        image = json_ld_data.get("image")
        if isinstance(image, str):
            return image

        if isinstance(image, dict):
            return image.get("url") or image.get("contentUrl")

        return None
