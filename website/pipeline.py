"""
website/pipeline.py
-------------------
Orchestrator for the website scraping agent.

Ties together: crawler → cleaner → classifier → extractor → storage.

Entry point:
    pipeline = WebsitePipeline()
    website_data = pipeline.run("https://infosys.com")
"""

import time
from datetime import datetime, timezone
from typing import Optional

from utils.helpers import setup_logger, is_valid_url
from website.crawler import crawl_website
from website.cleaner import clean_html_content, extract_raw_text
from website.classifier import classify_text_by_sections
from website.extractor import extract_company_intelligence, identify_role_pages
from website.parser import parse_html_metadata, extract_contact_info
from website.models import WebsiteData, RawWebsiteScrapedData
from website.storage import WebsiteStorage
from website.urls import get_domain

logger = setup_logger(__name__)


def _make_company_slug(url: str) -> str:
    """Create a clean slug from a domain name (e.g. 'infosys.com' → 'infosys')."""
    domain = get_domain(url)
    return domain.split(".")[0].lower().replace("-", "_") if domain else "unknown"


class WebsitePipeline:
    """
    End-to-end pipeline for scraping a company website and storing results in MongoDB.

    Steps:
        1. Crawl all internal pages with Playwright
        2. Clean HTML and extract metadata / contacts per page
        3. Classify combined clean text into business sections
        4. Extract structured WebsiteData (rule-based)
        5. Save raw pages + structured data to MongoDB
        6. Return WebsiteData

    Usage:
        pipeline = WebsitePipeline()
        data = pipeline.run("https://infosys.com")
        print(data.company_name, data.linkedin_url)
    """

    def __init__(self):
        self.storage = WebsiteStorage()

    def run(
        self,
        website_url: str,
        max_pages: int | None = None,
        timeout_ms: int | None = None,
        force_rescrape: bool = False,
    ) -> Optional[WebsiteData]:
        """
        Run the full website scraping pipeline.

        Args:
            website_url:    Company homepage URL.
            max_pages:      Override for max pages to crawl.
            timeout_ms:     Override for Playwright page timeout.
            force_rescrape: If True, re-scrape even if data exists in MongoDB.

        Returns:
            WebsiteData if successful, None if the crawl failed completely.
        """
        start_time = time.time()

        if not is_valid_url(website_url):
            logger.error(f"Invalid website URL: {website_url}")
            return None

        company_slug = _make_company_slug(website_url)
        logger.info(f"=== Website pipeline started === url='{website_url}' slug='{company_slug}'")

        # Check MongoDB cache
        if not force_rescrape and self.storage.website_data_exists(company_slug):
            logger.info(f"Cache hit — returning existing data for '{company_slug}'")
            return self.storage.get_website_data(company_slug)

        # Step 1: Crawl
        crawled_pages = crawl_website(website_url, max_pages=max_pages, timeout_ms=timeout_ms)
        if not crawled_pages:
            logger.error(f"Crawl returned no pages for: {website_url}")
            self.storage.log_scrape_operation(company_slug, "website", "failed", 0.0, "No pages crawled")
            return None

        # Step 2: Process each page
        page_metadata = {}
        clean_text_blocks = []
        raw_text_blocks = []
        combined_emails, combined_phones, combined_socials = [], [], []
        successful_urls = []
        linkedin_url_found = None

        for url, page_data in crawled_pages.items():
            if page_data["status"] != "success":
                continue

            successful_urls.append(url)
            html = page_data["html"]

            meta = parse_html_metadata(html)
            page_metadata[url] = meta

            clean_body = clean_html_content(html)
            raw_body = extract_raw_text(html)

            if clean_body:
                clean_text_blocks.append(clean_body)
            if raw_body:
                raw_text_blocks.append(raw_body)

            contacts = extract_contact_info(html, text_content=clean_body)
            combined_emails.extend(contacts["emails"])
            combined_phones.extend(contacts["phone_numbers"])
            combined_socials.extend(contacts["social_links"])
            if contacts.get("linkedin_url") and not linkedin_url_found:
                linkedin_url_found = contacts["linkedin_url"]

            # Save raw page to MongoDB
            raw_record = RawWebsiteScrapedData(
                company_slug=company_slug,
                page_url=url,
                raw_html=html[:100_000],
                raw_text=raw_body[:20_000] if raw_body else None,
                clean_text=clean_body[:20_000] if clean_body else None,
                page_title=meta.get("title"),
                meta_description=meta.get("description"),
                scraped_at=datetime.now(tz=timezone.utc),
                scrape_success=True,
            )
            self.storage.save_raw_page(raw_record)

        if not successful_urls:
            logger.error(f"No pages successfully crawled for: {website_url}")
            self.storage.log_scrape_operation(company_slug, "website", "failed", 0.0, "No successful pages")
            return None

        # Step 3: Aggregate & classify
        aggregated_contacts = {
            "emails": sorted(list(set(combined_emails))),
            "phone_numbers": sorted(list(set(combined_phones))),
            "social_links": sorted(list(set(combined_socials))),
        }
        combined_clean_text = "\n\n".join(clean_text_blocks)
        combined_raw_text = "\n\n".join(raw_text_blocks)
        classified_sections = classify_text_by_sections(combined_clean_text)
        discovered_pages = identify_role_pages(successful_urls)

        # Step 4: Extract structured intelligence
        website_data = extract_company_intelligence(
            homepage_url=website_url,
            company_slug=company_slug,
            page_metadata=page_metadata,
            combined_clean_text=combined_clean_text,
            combined_raw_text=combined_raw_text,
            classified_sections=classified_sections,
            aggregated_contacts=aggregated_contacts,
            discovered_pages=discovered_pages,
            social_links=combined_socials,
            visited_urls=successful_urls,
            crawl_duration=time.time() - start_time,
        )

        # Ensure LinkedIn URL found from site is stored
        if isinstance(linkedin_url_found, str) and linkedin_url_found and not website_data.linkedin_url:
            website_data.linkedin_url = linkedin_url_found

        # Step 5: Save structured data
        self.storage.save_website_data(website_data)

        duration = time.time() - start_time
        self.storage.log_scrape_operation(company_slug, "website", "success", duration)
        logger.info(f"=== Website pipeline complete === slug='{company_slug}' duration={duration:.2f}s pages={len(successful_urls)}")

        return website_data
