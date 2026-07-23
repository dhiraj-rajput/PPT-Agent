"""
linkedin/scraper.py
-------------------
Main orchestrator for LinkedIn data collection.

This is the single public entry point for the entire LinkedIn module.
All other modules (input_resolver, public_scraper, browser_scraper,
authenticated_scraper, rules_structurer, storage) are called from here.

The orchestration flow:
  1. Resolve input → canonical LinkedIn URL + company slug
  2. Check MongoDB cache (skip scraping if fresh data exists)
  3. Run Layer 1: Public scraper (always runs, fast baseline)
  4. Run Layer 2: Browser-based scraper (deep browser-based extraction)
  5. Run Layer 3: Authenticated scraper (only if li_at is configured)
  6. Run Rules Structurer (post-process and normalize all raw data)
  7. Save raw + structured data to MongoDB
  8. Return the final LinkedInCompanyData object

Design goals:
  - If any individual layer fails, the system continues with whatever data it has
  - All errors are logged and recorded, never silently swallowed
  - The output is always a valid LinkedInCompanyData object (may have None fields if data was unavailable)
"""

import asyncio
import time
from typing import Optional

from pipeline.linkedin.authenticated_scraper import AuthenticatedLinkedInScraper
from pipeline.linkedin.constants import (
    SCRAPE_LAYER_AUTHENTICATED,
    SCRAPE_LAYER_BROWSER,
    SCRAPE_LAYER_PUBLIC,
    build_company_page_url,
    build_company_about_url,
    build_company_jobs_url,
    build_company_people_url,
    build_company_posts_url,
)
from pipeline.linkedin.browser_scraper import BrowserLinkedInScraper
from pipeline.linkedin.data_cleaner import DataCleaner
from pipeline.linkedin.bi_extractor import BIExtractor
from pipeline.linkedin.input_resolver import InputResolver
from pipeline.linkedin.rules_structurer import RulesStructurer
from pipeline.linkedin.models import LinkedInCompanyData
from pipeline.linkedin.public_scraper import PublicLinkedInScraper
from pipeline.linkedin.storage import LinkedInStorage
from utils.helpers import setup_logger

logger = setup_logger(__name__)


async def scrape_company(
    user_input: str,
    force_rescrape: bool = False,
) -> LinkedInCompanyData:
    """
    The main public entry point for the LinkedIn data collection module.

    Given any form of company identifier (name, URL, slug, or post link),
    this function runs the full 3-layer scraping pipeline and returns
    a structured LinkedInCompanyData object stored in MongoDB.

    Args:
        user_input:     Any of: company name, LinkedIn URL, company slug, or post URL.
                        Examples:
                          - "Infosys"
                          - "https://www.linkedin.com/company/infosys"
                          - "infosys"
        force_rescrape: If True, scrapes fresh data even if the company exists in MongoDB.
                        Default is False (uses cached data if available).

    Returns:
        A LinkedInCompanyData object containing all extracted company information.

    Raises:
        ValueError: If the input cannot be resolved to a LinkedIn company URL.

    Example:
        import asyncio
        from pipeline.linkedin.scraper import scrape_company

        company_data = asyncio.run(scrape_company("Infosys"))
        print(company_data.identity.company_name)  # "Infosys"
        print(company_data.identity.industry)       # "IT Services and IT Consulting"
        print(len(company_data.recent_posts))       # 8
    """
    scrape_start_time = time.time()

    # Step 1: Resolve the user input to a canonical LinkedIn URL
    resolver = InputResolver()
    linkedin_url, company_slug = resolver.resolve(user_input)

    logger.info(
        f"=== Starting LinkedIn scrape === "
        f"input='{user_input}' → slug='{company_slug}'"
    )

    storage = LinkedInStorage()

    # Step 2: Check if we already have this company in MongoDB
    if not force_rescrape and storage.company_data_exists(company_slug):
        logger.info(
            f"Cache hit — returning existing data for '{company_slug}'. "
            "Use force_rescrape=True to fetch fresh data."
        )
        existing_data = storage.get_structured_company_data(company_slug)
        if existing_data:
            return existing_data

    # --- Begin actual scraping ---
    layers_used: list[str] = []
    all_raw_records = []
    layer2_extracted_data: dict = {}
    layer3_extracted_data: dict = {}

    # Step 3: Layer 1 — Public scraper (always runs)
    layer1_partial_identity, layer1_raw_record = _run_layer1_public_scraper(
        company_slug=company_slug,
        linkedin_url=linkedin_url,
    )

    if layer1_raw_record:
        all_raw_records.append(layer1_raw_record)
        layers_used.append(SCRAPE_LAYER_PUBLIC)

    # Step 4: Layer 2 — Browser-based scraper
    layer2_raw_records, layer2_extracted_data = await _run_layer2_browser_scraper(
        company_slug=company_slug,
    )
    all_raw_records.extend(layer2_raw_records)
    if layer2_raw_records:
        layers_used.append(SCRAPE_LAYER_BROWSER)

    # Step 5: Layer 3 — Authenticated scraper (only if li_at is configured)
    layer3_raw_records, layer3_extracted_data = await _run_layer3_authenticated_scraper(
        company_slug=company_slug,
    )
    all_raw_records.extend(layer3_raw_records)
    if layer3_raw_records:
        layers_used.append(SCRAPE_LAYER_AUTHENTICATED)

    # Build the list of all URLs that were scraped (for provenance tracking)
    source_urls_scraped = _collect_all_source_urls(company_slug)

    # Step 6: Save all raw records to MongoDB
    raw_document_ids: list[str] = []
    for raw_record in all_raw_records:
        raw_doc_id = storage.save_raw_scraped_data(raw_record)
        raw_document_ids.append(raw_doc_id)

    logger.info(
        f"Saved {len(all_raw_records)} raw records to MongoDB | "
        f"layers={layers_used}"
    )

    # Step 7: Rules-based Structuring — convert all raw data to clean structured data
    rules_structurer = RulesStructurer()
    final_company_data = await rules_structurer.structure_company_data(
        company_slug=company_slug,
        linkedin_url=linkedin_url,
        layer1_partial_identity=layer1_partial_identity,
        layer2_extracted_data=layer2_extracted_data,
        layer3_extracted_data=layer3_extracted_data,
        scrape_layers_used=layers_used,
        source_urls=source_urls_scraped,
    )

    # Set the reference to the raw data documents
    if raw_document_ids:
        final_company_data.raw_data_document_id = raw_document_ids[0]

    # Step 8: Clean raw structured data
    cleaner = DataCleaner()
    final_company_data, quality_score = cleaner.clean(final_company_data)

    # Step 9: Extract Business Intelligence (BI) Profile
    bi_extractor = BIExtractor()
    bi_profile = await bi_extractor.extract_bi_profile(final_company_data)
    final_company_data.bi_profile = bi_profile

    # Step 10: Save the structured and BI-enriched data to MongoDB
    storage.save_structured_company_data(final_company_data)

    # Record the scrape audit log
    total_duration_seconds = time.time() - scrape_start_time
    storage.log_scrape_operation(
        company_slug=company_slug,
        scrape_status="success",
        layers_used=layers_used,
        duration_seconds=total_duration_seconds,
    )

    logger.info(
        f"=== LinkedIn scrape complete === "
        f"company='{company_slug}' | "
        f"duration={total_duration_seconds:.2f}s | "
        f"layers={layers_used}"
    )

    return final_company_data


# ---------------------------------------------------------------------------
# Layer Runner Functions
# ---------------------------------------------------------------------------
# These are separate functions (not methods) to keep the main orchestrator
# clean and easy to read. Each handles one layer, including its error handling.

def _run_layer1_public_scraper(
    company_slug: str,
    linkedin_url: str,
) -> tuple:
    """
    Runs Layer 1 (public scraper) and returns its output.
    Returns (None, None) if the layer fails.
    """
    try:
        public_scraper = PublicLinkedInScraper()
        raw_record, partial_identity = public_scraper.scrape(
            company_slug=company_slug,
            linkedin_url=linkedin_url,
        )
        logger.info(f"[Orchestrator] Layer 1 complete | identity_found={partial_identity is not None}")
        return partial_identity, raw_record

    except Exception as layer1_error:
        logger.error(
            f"[Orchestrator] Layer 1 failed for '{company_slug}': {layer1_error}",
            exc_info=True,
        )
        return None, None


async def _run_layer2_browser_scraper(
    company_slug: str,
) -> tuple[list, dict]:
    """
    Runs Layer 2 (Browser-based) and returns its raw records and extracted data.
    Returns ([], {}) if the layer fails.
    """
    try:
        browser_scraper = BrowserLinkedInScraper()
        raw_records, extracted_data = await browser_scraper.scrape(company_slug)
        logger.info(
            f"[Orchestrator] Layer 2 complete | "
            f"pages_scraped={len(raw_records)} | "
            f"data_keys={list(extracted_data.keys())}"
        )
        return raw_records, extracted_data

    except Exception as layer2_error:
        logger.error(
            f"[Orchestrator] Layer 2 failed for '{company_slug}': {layer2_error}",
            exc_info=True,
        )
        return [], {}


async def _run_layer3_authenticated_scraper(
    company_slug: str,
) -> tuple[list, dict]:
    """
    Runs Layer 3 (authenticated) if configured.
    Returns ([], {}) if disabled or if the layer fails.
    """
    auth_scraper = AuthenticatedLinkedInScraper()

    if not auth_scraper.is_enabled():
        logger.info(
            "[Orchestrator] Layer 3 skipped — LINKEDIN_LI_AT not configured."
        )
        return [], {}

    try:
        raw_records, extracted_data = await auth_scraper.scrape(company_slug)
        logger.info(
            f"[Orchestrator] Layer 3 complete | "
            f"pages_scraped={len(raw_records)}"
        )
        return raw_records, extracted_data

    except Exception as layer3_error:
        logger.error(
            f"[Orchestrator] Layer 3 failed for '{company_slug}': {layer3_error}",
            exc_info=True,
        )
        return [], {}


def _collect_all_source_urls(company_slug: str) -> list[str]:
    """
    Returns the list of all LinkedIn URLs that were scraped for this company.
    Used for provenance tracking in the final data object.
    """
    return [
        build_company_page_url(company_slug),
        build_company_about_url(company_slug),
        build_company_posts_url(company_slug),
        build_company_jobs_url(company_slug),
        build_company_people_url(company_slug),
    ]
