"""Asynchronous website crawler and content parser."""

from __future__ import annotations

import asyncio
import logging
import posixpath
import re
import time
import socket
import ipaddress
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit, urlparse

import trafilatura
from bs4 import BeautifulSoup
from playwright.async_api import Browser, Page, Playwright, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ScrapeException(RuntimeError):
    """Raised when a page cannot be fetched safely."""


class CrawlConfig(BaseModel):
    """Configuration for bounded asynchronous crawling."""

    model_config = ConfigDict(frozen=True)

    max_concurrent_requests: int = Field(default=3, ge=1, le=16)
    timeout_ms: int = Field(default=30_000, ge=1_000)
    max_depth: int = Field(default=1, ge=0, le=5)
    user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )
    )
    max_pages: int = Field(default=8, ge=1, le=500)
    max_links_per_page: int = Field(default=12, ge=1, le=200)
    include_subdomains: bool = True
    retry_attempts: int = Field(default=1, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.75, ge=0.0, le=30.0)


class CleanedPageOutput(BaseModel):
    """Cleaned output for one crawled page."""

    model_config = ConfigDict(frozen=True)

    url: str
    raw_html: str
    cleaned_markdown: str
    extracted_links: list[str]
    timestamp: float
    depth: int

    def raw_document(self, company_name: str, seed_url: str) -> dict[str, Any]:
        return {
            "company_name": company_name,
            "seed_url": seed_url,
            "url": self.url,
            "raw_html": self.raw_html,
            "depth": self.depth,
            "timestamp": self.timestamp,
        }

    def cleaned_document(self, company_name: str, seed_url: str) -> dict[str, Any]:
        return {
            "company_name": company_name,
            "seed_url": seed_url,
            "url": self.url,
            "cleaned_markdown": self.cleaned_markdown,
            "extracted_links": self.extracted_links,
            "depth": self.depth,
            "timestamp": self.timestamp,
        }


BLACKLIST_PATTERN = re.compile(
    r"(terms(?:-of-service)?|privacy(?:-policy)?|cookie(?:-policy)?|share=|"
    r"\blogin\b|\bsign[-_]?up\b|checkout|logout|wp-admin|/cart\b|/account\b|rss|/feed\b)",
    re.IGNORECASE,
)
TRACKING_PARAM_PATTERN = re.compile(r"^(utm_.+|fbclid|gclid|msclkid|yclid|igshid|mc_.+|_hs.+|ref|source|share)$", re.IGNORECASE)
HIGH_VALUE_KEYWORDS = (
    "about",
    "business",
    "retail",
    "commercial",
    "hospitality",
    "residential",
    "investor",
    "presentation",
    "financial",
    "sustainability",
    "news",
    "media",
    "careers",
    "contact",
)


@dataclass(frozen=True, slots=True)
class LinkFilter:
    """Extract same-company links and prioritize business-relevant pages."""

    base_url: str
    include_subdomains: bool = True

    def extract_and_filter_links(self, html_content: str) -> list[str]:
        normalized_base = normalize_url(self.base_url, self.base_url)
        base_host = _strip_www(urlsplit(normalized_base).hostname or "")
        soup = BeautifulSoup(html_content, "lxml")
        scored: dict[str, int] = {}

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            if not href or href.lower().startswith(("mailto:", "tel:", "javascript:", "data:", "sms:")):
                continue
            normalized = normalize_url(urljoin(normalized_base, href), normalized_base)
            if not normalized or BLACKLIST_PATTERN.search(normalized):
                continue
            if not _is_allowed_host(normalized, base_host, self.include_subdomains):
                continue
            scored[normalized] = max(scored.get(normalized, 0), _score_url(normalized))

        return sorted(scored, key=lambda url: (-scored[url], url))


class PlaywrightFetcher:
    """Reusable Chromium-backed HTML fetcher."""

    def __init__(self, config: CrawlConfig) -> None:
        self._config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> "PlaywrightFetcher":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        logger.info("playwright_started")
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._browser is not None:
            with suppress(Exception):
                await self._browser.close()
        if self._playwright is not None:
            with suppress(Exception):
                await self._playwright.stop()
        logger.info("playwright_stopped")

    async def fetch_page_html(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self._config.retry_attempts + 1):
            try:
                return await self._fetch_once(url)
            except ScrapeException as exc:
                last_error = exc
                if attempt >= self._config.retry_attempts:
                    break
                delay = self._config.retry_backoff_seconds * (2 ** attempt)
                logger.warning("fetch_retry", extra={"url": url, "attempt": attempt + 1, "delay": delay})
                await asyncio.sleep(delay)
        raise ScrapeException(f"Failed to fetch {url}: {last_error}") from last_error

    async def _fetch_once(self, url: str) -> str:
        if self._browser is None:
            raise ScrapeException("PlaywrightFetcher must be used as an async context manager.")

        context = None
        page: Page | None = None
        try:
            context = await self._browser.new_context(
                user_agent=self._config.user_agent,
                viewport={"width": 1366, "height": 768},
                ignore_https_errors=True,
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            page = await context.new_page()
            await self._block_heavy_assets(page)
            response = await page.goto(url, wait_until="domcontentloaded", timeout=self._config.timeout_ms)
            if response is None:
                raise ScrapeException("No response returned by page.goto")
            if response.status >= 400:
                raise ScrapeException(f"HTTP {response.status}")
            content_type = response.headers.get("content-type", "").lower()
            if content_type and "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                raise ScrapeException(f"Non-HTML content type: {content_type}")
            html = await page.content()
            if not html.strip():
                raise ScrapeException("Empty HTML response")
            logger.info("page_fetched", extra={"url": url, "status": response.status, "bytes": len(html.encode("utf-8"))})
            return html
        except PlaywrightTimeoutError as exc:
            logger.exception("page_fetch_timeout", extra={"url": url, "timeout_ms": self._config.timeout_ms})
            raise ScrapeException(f"Timed out fetching {url}") from exc
        except ScrapeException:
            raise
        except Exception as exc:
            logger.exception("page_fetch_failed", extra={"url": url})
            raise ScrapeException(f"Unexpected fetch failure for {url}") from exc
        finally:
            if page is not None:
                with suppress(Exception):
                    await page.close()
            if context is not None:
                with suppress(Exception):
                    await context.close()

    async def _block_heavy_assets(self, page: Page) -> None:
        async def handler(route: Any) -> None:
            if route.request.resource_type in {"image", "media", "font"}:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", handler)


class WebsiteCrawler:
    """Bounded async crawler that returns cleaned page outputs."""

    def __init__(self, config: CrawlConfig) -> None:
        self._config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent_requests)

    async def crawl(self, seed_url: str) -> dict[str, CleanedPageOutput]:
        normalized_seed = normalize_url(seed_url, seed_url)
        if not normalized_seed:
            raise ValueError(f"Invalid seed URL: {seed_url}")

        queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        visited = {normalized_seed}
        results: dict[str, CleanedPageOutput] = {}
        scheduling_lock = asyncio.Lock()
        await queue.put((normalized_seed, 0))

        async with PlaywrightFetcher(self._config) as fetcher:
            workers = [
                asyncio.create_task(self._worker(queue, fetcher, visited, results, scheduling_lock))
                for _ in range(self._config.max_concurrent_requests)
            ]
            await queue.join()
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        return results

    async def _worker(
        self,
        queue: asyncio.Queue[tuple[str, int]],
        fetcher: PlaywrightFetcher,
        visited: set[str],
        results: dict[str, CleanedPageOutput],
        scheduling_lock: asyncio.Lock,
    ) -> None:
        while True:
            url, depth = await queue.get()
            try:
                await self._process_url(url, depth, queue, fetcher, visited, results, scheduling_lock)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("page_processing_failed", extra={"url": url, "depth": depth})
            finally:
                queue.task_done()

    async def _process_url(
        self,
        url: str,
        depth: int,
        queue: asyncio.Queue[tuple[str, int]],
        fetcher: PlaywrightFetcher,
        visited: set[str],
        results: dict[str, CleanedPageOutput],
        scheduling_lock: asyncio.Lock,
    ) -> None:
        async with self._semaphore:
            html = await fetcher.fetch_page_html(url)

        links = LinkFilter(url, self._config.include_subdomains).extract_and_filter_links(html)
        cleaned = extract_clean_content(html)
        results[url] = CleanedPageOutput(
            url=url,
            raw_html=html,
            cleaned_markdown=cleaned,
            extracted_links=links,
            timestamp=time.time(),
            depth=depth,
        )

        if depth >= self._config.max_depth:
            return

        async with scheduling_lock:
            for link in links[: self._config.max_links_per_page]:
                if len(visited) >= self._config.max_pages:
                    break
                if link in visited:
                    continue
                visited.add(link)
                await queue.put((link, depth + 1))


def extract_clean_content(html_content: str) -> str:
    try:
        extracted = trafilatura.extract(
            html_content,
            include_tables=True,
            include_links=False,
            include_images=False,
            output_format="markdown",
        )
        if extracted and extracted.strip():
            return extracted.strip()
    except Exception:
        logger.exception("trafilatura_failed")

    soup = BeautifulSoup(html_content, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line)).strip()


def normalize_url(url: str, base_url: str) -> str:
    absolute = urljoin(base_url, url.strip())
    parsed = urlsplit(absolute)
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    netloc = hostname
    if port is not None and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    path = _normalize_path(parsed.path)
    query = _normalize_query(parsed.query)
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


def _normalize_path(path: str) -> str:
    decoded = unquote(path or "/")
    normalized = posixpath.normpath(decoded)
    if decoded.endswith("/") and not normalized.endswith("/"):
        normalized = f"{normalized}/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return quote(normalized, safe="/:@")


def _normalize_query(query: str) -> str:
    params = [(key, value) for key, value in parse_qsl(query, keep_blank_values=False) if not TRACKING_PARAM_PATTERN.match(key)]
    return urlencode(sorted(params), doseq=True)


def _is_allowed_host(url: str, base_host: str, include_subdomains: bool) -> bool:
    host = _strip_www(urlsplit(url).hostname or "")
    return host == base_host or (include_subdomains and host.endswith(f".{base_host}"))


def _strip_www(hostname: str) -> str:
    return hostname[4:] if hostname.startswith("www.") else hostname


def _score_url(url: str) -> int:
    lowered = url.lower()
    score = sum(100 - index for index, keyword in enumerate(HIGH_VALUE_KEYWORDS) if keyword in lowered)
    return score - max(urlsplit(url).path.count("/") - 1, 0)


def is_safe_url(url: str) -> bool:
    """Validate that the URL has a safe scheme and resolves to a public, non-local IP address to prevent SSRF."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # Resolve hostname to all possible IP addresses
        ip_info = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in ip_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                logger.warning(f"[SSRF Protection] Blocked URL resolving to private/local IP: {url} ({ip_str})")
                return False
        return True
    except Exception as e:
        logger.warning(f"[SSRF Protection] Error resolving URL {url}: {e}")
        return False


def crawl_website(
    homepage_url: str,
    max_pages: int | None = None,
    timeout_ms: int | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Crawl a company website starting from the homepage.

    Primary:  crawl4ai — async, JS-rendered, faster, Markdown extraction.
    Fallback: Playwright sync crawler — used if crawl4ai is not installed
              or raises an unrecoverable error.

    Returns a dict mapping URL → {"url": str, "html": str, "status": str}.
    """
    from config.settings import settings

    if not is_safe_url(homepage_url):
        logger.error(f"[SSRF Protection] Blocked crawling request to unsafe starting URL: {homepage_url}")
        return {}

    limit_pages: int = max_pages if max_pages is not None else int(
        getattr(settings, "MAX_CRAWL_PAGES", 15)
    )
    limit_timeout: float = float(
        timeout_ms if timeout_ms is not None else int(
            getattr(settings, "CRAWL_TIMEOUT", 30000)
        )
    )

    # ------------------------------------------------------------------ #
    # Primary: crawl4ai                                                    #
    # ------------------------------------------------------------------ #
    try:
        import asyncio
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
        from urllib.parse import urljoin as _urljoin
        from bs4 import BeautifulSoup as _BSoup

        logger.info(
            f"[crawl_website] Starting crawl4ai crawl: {homepage_url} "
            f"(max_pages={limit_pages}, timeout={limit_timeout}ms)"
        )

        async def _run_crawl4ai() -> dict[str, dict[str, Any]]:
            browser_cfg = BrowserConfig(
                headless=getattr(settings, "BROWSER_HEADLESS", True),
                verbose=False,
            )
            run_cfg = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                page_timeout=int(limit_timeout),
                js_code="window.scrollTo(0, document.body.scrollHeight);",
                wait_for="body",
                word_count_threshold=20,
            )

            pages: dict[str, dict[str, Any]] = {}
            link_filter = LinkFilter(homepage_url)

            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                # Start with the seed
                urls_to_visit: list[str] = [homepage_url]
                visited: set[str] = set()

                while urls_to_visit and len(pages) < limit_pages:
                    batch = []
                    for u in urls_to_visit[:3]:       # crawl up to 3 in parallel
                        if u not in visited:
                            visited.add(u)
                            if is_safe_url(u):
                                batch.append(u)
                    urls_to_visit = [u for u in urls_to_visit if u not in visited]

                    if not batch:
                        continue

                    results = await crawler.arun_many(batch, config=run_cfg)
                    res_raw: Any = results
                    res_items = []
                    if hasattr(res_raw, "__aiter__"):
                        async for res in res_raw:
                            res_items.append(res)
                    elif hasattr(res_raw, "__iter__"):
                        res_items = list(res_raw)
                    else:
                        res_items = [res_raw]

                    for res in res_items:
                        url = getattr(res, "url", "")
                        if not url or not is_safe_url(url):
                            logger.warning(f"[SSRF Protection] Blocked unsafe redirected URL: {url}")
                            continue
                        if getattr(res, "success", False):
                            html = getattr(res, "html", "") or ""
                            # Discover new links via crawl4ai's extracted links + link filter
                            discovered = link_filter.extract_and_filter_links(html)
                            for new_link in discovered[:20]:
                                if new_link not in visited and new_link not in urls_to_visit:
                                    if is_safe_url(new_link):
                                        urls_to_visit.append(new_link)

                            pages[url] = {
                                "url": url,
                                "html": html,
                                "markdown": getattr(getattr(res, "markdown", None), "raw_markdown", str(getattr(res, "markdown", ""))),
                                "status": "success",
                            }
                            logger.info(
                                f"[crawl4ai] Crawled: {url} "
                                f"({len(html)} bytes, markdown={len(res.markdown or '')} chars)"
                            )
                        else:
                            logger.warning(f"[crawl4ai] Failed: {url} — {res.error_message}")
                            pages[url] = {
                                "url": url,
                                "html": "",
                                "status": "failed",
                                "error": res.error_message or "Unknown error",
                            }

            return pages

        def _thread_worker():
            return asyncio.run(_run_crawl4ai())

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(_thread_worker)
                    result = future.result(timeout=int(limit_timeout / 1000) + 120)
            else:
                result = _thread_worker()
        except Exception as run_err:
            logger.error(f"[crawl4ai] Failed to execute crawl thread: {run_err}")
            result = {}

        success_count = sum(1 for p in result.values() if p["status"] == "success")
        logger.info(
            f"[crawl4ai] Crawl complete: {success_count}/{len(result)} pages successful"
        )
        return result

    except ImportError:
        logger.warning(
            "[crawl_website] crawl4ai not available — falling back to Playwright crawler. "
            "Install it with: pip install crawl4ai"
        )
    except Exception as exc:
        logger.warning(
            f"[crawl_website] crawl4ai raised an error ({exc}) — falling back to Playwright crawler."
        )

    # ------------------------------------------------------------------ #
    # Fallback: Playwright sync crawler                                    #
    # ------------------------------------------------------------------ #
    return _playwright_crawl_website(homepage_url, limit_pages, limit_timeout)


def _playwright_crawl_website(
    homepage_url: str,
    limit_pages: int,
    limit_timeout: float,
) -> dict[str, dict[str, Any]]:
    """Playwright-based synchronous website crawler (fallback when crawl4ai is unavailable)."""
    from utils.helpers import is_valid_url
    from pipeline.website.urls import normalize_url as p_normalize_url, is_internal_link, should_ignore_url, get_url_priority
    from pipeline.website.parser import extract_links
    from config.settings import settings
    from playwright.sync_api import sync_playwright

    if not is_valid_url(homepage_url):
        logger.error(f"Invalid starting URL: {homepage_url}")
        return {}

    logger.info(
        f"[Playwright] Starting sync crawl: {homepage_url} "
        f"(max_pages={limit_pages}, timeout={limit_timeout}ms)"
    )

    visited_pages: dict[str, dict[str, Any]] = {}
    visited_urls_set: set[str] = set()
    queue: list[tuple] = [(p_normalize_url(homepage_url, homepage_url), 10)]

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=getattr(settings, "BROWSER_HEADLESS", True))
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            context.set_default_timeout(limit_timeout)
            page = context.new_page()
        except Exception as e:
            logger.critical(f"Failed to start Playwright: {e}")
            return {}

        try:
            while queue and len(visited_pages) < limit_pages:
                queue.sort(key=lambda x: x[1], reverse=True)
                current_url, _ = queue.pop(0)

                if current_url in visited_urls_set:
                    continue
                visited_urls_set.add(current_url)

                if not is_safe_url(current_url):
                    logger.warning(f"[SSRF Protection] Skipping unsafe URL in Playwright crawl: {current_url}")
                    continue

                logger.info(f"[Playwright] [{len(visited_pages)+1}/{limit_pages}] Crawling: {current_url}")
                try:
                    response = page.goto(current_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(800)

                    final_url = page.url
                    if not is_safe_url(final_url):
                        logger.warning(f"[SSRF Protection] Blocked unsafe redirected URL: {final_url}")
                        continue

                    html_content = page.content()
                    status_code = response.status if response else 200

                    if status_code >= 400:
                        logger.warning(f"HTTP {status_code} for {current_url}")
                        visited_pages[current_url] = {
                            "url": current_url, "html": html_content,
                            "status": "failed", "error": f"HTTP {status_code}"
                        }
                        continue

                    if not is_internal_link(final_url, homepage_url):
                        logger.warning(f"Redirected to external domain: {final_url}")
                        visited_pages[current_url] = {
                            "url": final_url, "html": html_content, "status": "success"
                        }
                        continue

                    visited_pages[current_url] = {
                        "url": final_url, "html": html_content, "status": "success"
                    }

                    raw_links = extract_links(html_content)
                    for raw_link in raw_links:
                        norm = p_normalize_url(raw_link, current_url)
                        if (
                            norm
                            and norm not in visited_urls_set
                            and is_internal_link(norm, homepage_url)
                            and is_safe_url(norm)
                            and not should_ignore_url(norm)
                            and not any(item[0] == norm for item in queue)
                        ):
                            queue.append((norm, get_url_priority(norm)))

                except Exception as ex:
                    logger.warning(f"Error crawling {current_url}: {ex}")
                    visited_pages[current_url] = {
                        "url": current_url, "html": "", "status": "failed", "error": str(ex)
                    }

                time.sleep(0.4)

        finally:
            browser.close()

    success_count = sum(1 for p in visited_pages.values() if p["status"] == "success")
    logger.info(f"[Playwright] Crawl complete: {success_count}/{len(visited_pages)} pages successful")
    return visited_pages
