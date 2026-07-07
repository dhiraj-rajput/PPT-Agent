"""Trial runner for website crawl, Mongo persistence, and optional BI extraction."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict
from pathlib import Path

from bi_extraction.extractor import HuggingFaceCompanyExtractor
from config.settings import load_settings
from google_search.search_client import ExternalSearchClient, SearchResult
from utils.db_client import MongoStorageManager
from website.crawler import CleanedPageOutput, CrawlConfig, WebsiteCrawler

logger = logging.getLogger(__name__)


async def run_trial(
    *,
    company_name: str,
    seed_url: str,
    max_depth: int,
    max_pages: int,
    skip_llm: bool,
    skip_mongo: bool,
    output_dir: Path,
    source_mode: str,
    external_results: int,
) -> None:
    settings = load_settings()

    if source_mode == "official":
        pages = await _crawl_official_site(seed_url=seed_url, max_depth=max_depth, max_pages=max_pages)
        source_metadata: dict[str, dict[str, str]] = {}
    elif source_mode == "external":
        pages, source_metadata = await _crawl_external_sources(
            company_name=company_name,
            official_url=seed_url,
            max_results=external_results,
            output_dir=output_dir,
        )
    else:
        raise ValueError("source_mode must be either 'external' or 'official'.")

    logger.info("trial_crawl_completed", extra={"page_count": len(pages), "source_mode": source_mode})
    if not pages:
        raise RuntimeError("No pages were collected. Check search API keys, result filters, or target availability.")

    output_dir.mkdir(parents=True, exist_ok=True)
    cleaned_json_path = output_dir / "phoenix_mills_cleaned_pages.json"
    cleaned_json_path.write_text(
        json.dumps(
            [
                _with_source_metadata(
                    page.cleaned_document(company_name, seed_url),
                    source_mode=source_mode,
                    source_metadata=source_metadata.get(page.url, {}),
                )
                for page in pages
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    storage: MongoStorageManager | None = None
    if not skip_mongo:
        storage = MongoStorageManager(settings)
        try:
            for page in pages:
                await storage.upsert_raw_page(
                    _with_source_metadata(
                        page.raw_document(company_name, seed_url),
                        source_mode=source_mode,
                        source_metadata=source_metadata.get(page.url, {}),
                    )
                )
                await storage.upsert_cleaned_page(
                    _with_source_metadata(
                        page.cleaned_document(company_name, seed_url),
                        source_mode=source_mode,
                        source_metadata=source_metadata.get(page.url, {}),
                    )
                )
            logger.info("trial_pages_persisted", extra={"raw_count": len(pages), "cleaned_count": len(pages)})
        finally:
            storage.close()

    if skip_llm:
        logger.info("trial_llm_skipped")
        return

    extractor = HuggingFaceCompanyExtractor(settings)
    profile = await extractor.extract_profile(company_name=company_name, website=seed_url, pages=pages)
    profile_json_path = output_dir / "phoenix_mills_company_profile.json"
    profile_json_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")

    if not skip_mongo:
        storage = MongoStorageManager(settings)
        try:
            await storage.upsert_company_profile(profile.model_dump(mode="json"))
            logger.info("trial_profile_persisted", extra={"company_name": profile.company_name})
        finally:
            storage.close()

    logger.info("trial_profile_extracted", extra={"profile_path": str(profile_json_path)})


async def _crawl_official_site(*, seed_url: str, max_depth: int, max_pages: int) -> list[CleanedPageOutput]:
    crawler = WebsiteCrawler(
        CrawlConfig(
            max_depth=max_depth,
            max_pages=max_pages,
            max_concurrent_requests=2,
            max_links_per_page=10,
        )
    )
    pages_by_url = await crawler.crawl(seed_url)
    return list(pages_by_url.values())


async def _crawl_external_sources(
    *,
    company_name: str,
    official_url: str,
    max_results: int,
    output_dir: Path,
) -> tuple[list[CleanedPageOutput], dict[str, dict[str, str]]]:
    settings = load_settings()
    search_client = ExternalSearchClient(settings)
    results = await search_client.search_company_sources(
        company_name=company_name,
        official_url=official_url,
        max_results=max_results,
    )
    if not results:
        return [], {}

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phoenix_mills_external_search_results.json").write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    pages: list[CleanedPageOutput] = []
    metadata: dict[str, dict[str, str]] = {}
    for result in results:
        try:
            crawler = WebsiteCrawler(
                CrawlConfig(
                    max_depth=0,
                    max_pages=1,
                    max_concurrent_requests=1,
                    max_links_per_page=1,
                )
            )
            crawled = await crawler.crawl(result.url)
            for page in crawled.values():
                pages.append(page)
                metadata[page.url] = _result_metadata(result)
        except Exception:
            logger.exception("external_source_crawl_failed", extra={"url": result.url})
    return pages, metadata


def _result_metadata(result: SearchResult) -> dict[str, str]:
    return {
        "source_title": result.title,
        "source_snippet": result.snippet,
        "search_provider": result.provider,
        "search_result_url": result.url,
    }


def _with_source_metadata(
    document: dict[str, object],
    *,
    source_mode: str,
    source_metadata: dict[str, str],
) -> dict[str, object]:
    document["source_mode"] = source_mode
    document["source_scope"] = "third_party_web" if source_mode == "external" else "official_site"
    document.update(source_metadata)
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a small crawl/extraction trial for a target company.")
    parser.add_argument("--company-name", default="The Phoenix Mills Limited")
    parser.add_argument("--seed-url", default="https://www.thephoenixmills.com/")
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=6)
    parser.add_argument("--external-results", type=int, default=6)
    parser.add_argument("--source-mode", choices=["external", "official"], default="external")
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--skip-mongo", action="store_true")
    parser.add_argument("--output-dir", default="data/trial_runs")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    asyncio.run(
        run_trial(
            company_name=args.company_name,
            seed_url=args.seed_url,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            skip_llm=args.skip_llm,
            skip_mongo=args.skip_mongo,
            output_dir=Path(args.output_dir),
            source_mode=args.source_mode,
            external_results=args.external_results,
        )
    )


if __name__ == "__main__":
    main()
