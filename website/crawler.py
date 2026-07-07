"""
website/crawler.py
------------------
Layer 1 of the website agent: Playwright-based website crawler.

Starts from the homepage URL, discovers and crawls internal pages using a
priority queue (about, products, services, team pages first), and returns
raw HTML for each page.

Key features:
  - JavaScript rendering via Playwright Chromium
  - Priority-based URL queue (important pages crawled first)
  - Configurable max pages and timeout
  - Only follows internal (same-domain) links
  - Strips tracking parameters, avoids binary files and ignored pages
"""

import time
from typing import Dict, List, Set, Any

from utils.helpers import is_valid_url, setup_logger
from website.urls import normalize_url, is_internal_link, should_ignore_url, get_url_priority
from website.parser import extract_links, parse_html_metadata
from config.settings import settings

logger = setup_logger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def crawl_website(
    homepage_url: str,
    max_pages: int = None,
    timeout_ms: int = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Crawl a company website starting from the homepage.

    Args:
        homepage_url: The company website homepage URL.
        max_pages:    Maximum number of pages to visit (default from settings).
        timeout_ms:   Playwright page timeout in milliseconds (default 30000).

    Returns:
        Dict mapping visited URL → {url, html, status, error (optional)}
    """
    if not is_valid_url(homepage_url):
        logger.error(f"Invalid starting URL: {homepage_url}")
        return {}

    max_pages = max_pages or getattr(settings, "MAX_CRAWL_PAGES", 15)
    timeout_ms = timeout_ms or getattr(settings, "CRAWL_TIMEOUT", 30000)

    logger.info(f"Starting crawl: {homepage_url} (max_pages={max_pages}, timeout={timeout_ms}ms)")

    visited_pages: Dict[str, Dict[str, Any]] = {}
    visited_urls_set: Set[str] = set()
    queue: List[tuple] = [(normalize_url(homepage_url, homepage_url), 10)]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return {}

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=getattr(settings, "BROWSER_HEADLESS", True))
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            context.set_default_timeout(timeout_ms)
            page = context.new_page()
        except Exception as e:
            logger.critical(f"Failed to start Playwright: {e}")
            return {}

        try:
            while queue and len(visited_pages) < max_pages:
                queue.sort(key=lambda x: x[1], reverse=True)
                current_url, _ = queue.pop(0)

                if current_url in visited_urls_set:
                    continue
                visited_urls_set.add(current_url)

                logger.info(f"[{len(visited_pages)+1}/{max_pages}] Crawling: {current_url}")
                try:
                    response = page.goto(current_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(800)  # Allow JS to settle

                    final_url = page.url
                    html_content = page.content()
                    status_code = response.status if response else 200

                    if status_code >= 400:
                        logger.warning(f"HTTP {status_code} for {current_url}")
                        visited_pages[current_url] = {
                            "url": current_url, "html": html_content,
                            "status": "failed", "error": f"HTTP {status_code}"
                        }
                        continue

                    # Skip if redirected to an external domain
                    if not is_internal_link(final_url, homepage_url):
                        logger.warning(f"Redirected to external domain: {final_url}")
                        visited_pages[current_url] = {
                            "url": final_url, "html": html_content, "status": "success"
                        }
                        continue

                    visited_pages[current_url] = {
                        "url": final_url, "html": html_content, "status": "success"
                    }

                    # Discover new internal links
                    raw_links = extract_links(html_content)
                    for raw_link in raw_links:
                        norm = normalize_url(raw_link, current_url)
                        if (
                            norm
                            and norm not in visited_urls_set
                            and is_internal_link(norm, homepage_url)
                            and not should_ignore_url(norm)
                            and not any(item[0] == norm for item in queue)
                        ):
                            queue.append((norm, get_url_priority(norm)))

                except Exception as ex:
                    logger.warning(f"Error crawling {current_url}: {ex}")
                    visited_pages[current_url] = {
                        "url": current_url, "html": "", "status": "failed", "error": str(ex)
                    }

                time.sleep(0.4)  # Polite delay

        finally:
            browser.close()

    success_count = sum(1 for p in visited_pages.values() if p["status"] == "success")
    logger.info(f"Crawl complete: {success_count}/{len(visited_pages)} pages successful")
    return visited_pages
