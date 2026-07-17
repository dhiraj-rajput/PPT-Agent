"""
linkedin/browser_scraper.py
----------------------------
Layer 2: Browser-based scraping using Crawl4AI.

Performs browser crawls without using LLMExtractionStrategy.
This removes all AI API calls during scraping, preventing rate limits (429)
and 404 errors completely. The raw text/markdown is still collected and saved.
"""

from typing import Optional

from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig, BrowserConfig

from pipeline.linkedin.constants import (
    SCRAPE_LAYER_BROWSER,
    build_company_about_url,
    build_company_jobs_url,
    build_company_page_url,
    build_company_people_url,
    build_company_posts_url,
)
from pipeline.linkedin.models import RawLinkedInScrapedData
from utils.helpers import get_utc_now, setup_logger

logger = setup_logger(__name__)


class BrowserLinkedInScraper:
    """
    Layer 2 scraper: visits the company's LinkedIn pages using a browser
    via Crawl4AI. Fetches raw markdown/text to feed the parser.
    Uses zero AI/LLM requests during crawls.
    """

    def __init__(self):
        """Initializes the scraper."""
        pass

    async def scrape(
        self,
        company_slug: str,
    ) -> tuple[list[RawLinkedInScrapedData], dict]:
        """
        Runs the full browser scraping sequence for a company.

        Visits the main page, About, Posts, Jobs, and People sub-pages.
        Extracts raw markdown and saves it. No LLM extraction is performed.
        """
        logger.info(f"[Layer 2 - Browser] Starting crawl for: '{company_slug}'")

        browser_config = self._build_browser_config()
        combined_extracted_data: dict = {}
        raw_records: list[RawLinkedInScrapedData] = []

        async with AsyncWebCrawler(config=browser_config) as crawler:
            # --- 1. Main company page ---
            _, main_page_raw = await self._scrape_main_page(
                crawler, company_slug
            )
            raw_records.append(main_page_raw)

            # --- 2. About page ---
            _, about_raw = await self._scrape_about_page(
                crawler, company_slug
            )
            raw_records.append(about_raw)

            # --- 3. Posts page ---
            _, posts_raw = await self._scrape_posts_page(
                crawler, company_slug
            )
            raw_records.append(posts_raw)

            # --- 4. Jobs page ---
            _, jobs_raw = await self._scrape_jobs_page(
                crawler, company_slug
            )
            raw_records.append(jobs_raw)

            # --- 5. People page ---
            _, people_raw = await self._scrape_people_page(
                crawler, company_slug
            )
            raw_records.append(people_raw)

        logger.info(
            f"[Layer 2] Completed | company='{company_slug}' "
            f"| pages_scraped={len(raw_records)}"
        )

        return raw_records, combined_extracted_data

    # ---------------------------------------------------------------------------
    # Browser Configuration
    # ---------------------------------------------------------------------------

    def _build_browser_config(self) -> BrowserConfig:
        """Builds a Playwright browser configuration with stealth settings."""
        from config.settings import settings
        return BrowserConfig(
            headless=settings.BROWSER_HEADLESS,
            verbose=False,
            extra_args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

    def _build_crawler_run_config(self) -> CrawlerRunConfig:
        """Builds the CrawlerRunConfig for a page scrape."""
        return CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_for_images=False,
            word_count_threshold=20,
        )

    # ---------------------------------------------------------------------------
    # Individual Page Crawlers
    # ---------------------------------------------------------------------------

    async def _scrape_main_page(
        self,
        crawler: AsyncWebCrawler,
        company_slug: str,
    ) -> tuple[None, RawLinkedInScrapedData]:
        """Scrapes the main company LinkedIn page."""
        page_url = build_company_page_url(company_slug)
        return await self._run_crawl(
            crawler=crawler,
            company_slug=company_slug,
            page_url=page_url,
            page_label="main",
        )

    async def _scrape_about_page(
        self,
        crawler: AsyncWebCrawler,
        company_slug: str,
    ) -> tuple[None, RawLinkedInScrapedData]:
        """Scrapes the /about sub-page."""
        page_url = build_company_about_url(company_slug)
        return await self._run_crawl(
            crawler=crawler,
            company_slug=company_slug,
            page_url=page_url,
            page_label="about",
        )

    async def _scrape_posts_page(
        self,
        crawler: AsyncWebCrawler,
        company_slug: str,
    ) -> tuple[None, RawLinkedInScrapedData]:
        """Scrapes the /posts sub-page."""
        page_url = build_company_posts_url(company_slug)
        return await self._run_crawl(
            crawler=crawler,
            company_slug=company_slug,
            page_url=page_url,
            page_label="posts",
        )

    async def _scrape_jobs_page(
        self,
        crawler: AsyncWebCrawler,
        company_slug: str,
    ) -> tuple[None, RawLinkedInScrapedData]:
        """Scrapes the /jobs sub-page."""
        page_url = build_company_jobs_url(company_slug)
        return await self._run_crawl(
            crawler=crawler,
            company_slug=company_slug,
            page_url=page_url,
            page_label="jobs",
        )

    async def _scrape_people_page(
        self,
        crawler: AsyncWebCrawler,
        company_slug: str,
    ) -> tuple[None, RawLinkedInScrapedData]:
        """Scrapes the /people sub-page."""
        page_url = build_company_people_url(company_slug)
        return await self._run_crawl(
            crawler=crawler,
            company_slug=company_slug,
            page_url=page_url,
            page_label="people",
        )

    # ---------------------------------------------------------------------------
    # Core Crawl Runner
    # ---------------------------------------------------------------------------

    async def _run_crawl(
        self,
        crawler: AsyncWebCrawler,
        company_slug: str,
        page_url: str,
        page_label: str,
    ) -> tuple[None, RawLinkedInScrapedData]:
        """Runs a single crawl on the given URL without any LLM extraction."""
        logger.info(f"[Layer 2] Crawling '{page_label}' page: {page_url}")

        try:
            crawl_result = await crawler.arun(
                url=page_url,
                config=self._build_crawler_run_config(),
            )

            raw_record = RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_BROWSER,
                page_url=page_url,
                raw_text=crawl_result.markdown[:20_000] if crawl_result.markdown else None,
                scraped_at=get_utc_now(),
                scrape_success=crawl_result.success,
                error_message=crawl_result.error_message if not crawl_result.success else None,
            )

            return None, raw_record

        except Exception as unexpected_error:
            logger.error(
                f"[Layer 2] Unexpected error crawling '{page_label}' for '{company_slug}': "
                f"{unexpected_error}",
                exc_info=True,
            )
            raw_record = RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_BROWSER,
                page_url=page_url,
                scraped_at=get_utc_now(),
                scrape_success=False,
                error_message=str(unexpected_error),
            )
            return None, raw_record

    def _parse_extracted_content(
        self,
        extracted_content: Optional[str],
        page_label: str,
        company_slug: str,
    ) -> Optional[dict | list]:
        """
        Parses the JSON string returned by the Crawl4AI extraction strategy.
        Normalizes the output: unwraps single-element lists containing a dict.
        """
        import json
        if not extracted_content:
            return None

        try:
            parsed = json.loads(extracted_content)
            
            # If the strategy returned an empty list, return None
            if isinstance(parsed, list) and not parsed:
                return None
            
            # If the strategy returned a single-item list containing a dict, unwrap it
            if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
                logger.debug(f"[Layer 2] Unwrapped single-item list result for '{page_label}'")
                return parsed[0]
                
            return parsed
        except json.JSONDecodeError as decode_error:
            logger.warning(f"[Layer 2] Failed to parse JSON for '{page_label}': {decode_error}")
            return None
