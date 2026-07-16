"""
linkedin/authenticated_scraper.py
----------------------------------
Layer 3: Authenticated scraping using the LinkedIn li_at session cookie.

This is the most data-rich layer. By injecting a real LinkedIn session
cookie into the Playwright browser, we gain access to:

  - Full employee directory with names, titles, and profile links
  - Detailed employee growth charts (% change over 6 and 12 months)
  - Complete followers and engagement metrics
  - Full posts feed with engagement counts
  - Funded rounds and investor details
  - All affiliated companies and showcase pages
  - Leadership team with full bios

IMPORTANT: This layer only runs if LINKEDIN_LI_AT is set in .env.
           Never use your primary LinkedIn account for this.
           See linkedin/GUIDE.md for burner account setup instructions.

How to get your li_at cookie:
  1. Log into LinkedIn in Chrome
  2. Open DevTools → Application → Cookies → www.linkedin.com
  3. Find the cookie named "li_at"
  4. Copy its value into LINKEDIN_LI_AT in your .env file
"""

import asyncio
from typing import Optional

from playwright.async_api import BrowserContext, Page, async_playwright

from config.settings import settings
from linkedin.constants import (
    LINKEDIN_BASE_URL,
    SCRAPE_LAYER_AUTHENTICATED,
    build_company_about_url,
    build_company_page_url,
    build_company_people_url,
    build_company_posts_url,
)
from linkedin.models import (
    CompanyPost,
    EmployeeInsights,
    FundingInfo,
    LeadershipMember,
    RawLinkedInScrapedData,
)
from utils.helpers import get_utc_now, setup_logger, wait_random_delay

logger = setup_logger(__name__)

# How long to wait for page content to load (in milliseconds)
PAGE_LOAD_WAIT_MS = 5000

# Number of recent posts to try to collect
MAX_POSTS_TO_COLLECT = 15

# Number of jobs to try to collect
MAX_JOBS_TO_COLLECT = 25


class AuthenticatedLinkedInScraper:
    """
    Layer 3 scraper: uses a real LinkedIn session to access behind-login data.

    This layer runs only if LINKEDIN_LI_AT is configured.
    It injects the cookie into a Playwright browser context and navigates
    LinkedIn as if a user were logged in.

    Usage:
        scraper = AuthenticatedLinkedInScraper()
        if scraper.is_enabled():
            raw_records, auth_data = await scraper.scrape("infosys")
    """

    def is_enabled(self) -> bool:
        """
        Returns True if authenticated scraping is configured.
        Checks that LINKEDIN_LI_AT cookie is set in settings.
        """
        return settings.is_authenticated_linkedin_scraping_enabled

    async def scrape(
        self,
        company_slug: str,
    ) -> tuple[list[RawLinkedInScrapedData], dict]:
        """
        Runs authenticated scraping for a company using the li_at cookie.

        Args:
            company_slug: LinkedIn company slug, e.g. "infosys".

        Returns:
            A tuple of:
              - list[RawLinkedInScrapedData]: Raw records from each page.
              - dict: All extracted data fields combined.
        """
        if not self.is_enabled():
            logger.warning(
                "[Layer 3] Authenticated scraping is not enabled. "
                "Set LINKEDIN_LI_AT in your .env file."
            )
            return [], {}

        logger.info(
            f"[Layer 3 - Authenticated] Starting scrape for: '{company_slug}'"
        )

        raw_records: list[RawLinkedInScrapedData] = []
        combined_auth_data: dict = {}

        async with async_playwright() as playwright_instance:
            browser = await playwright_instance.chromium.launch(
                headless=settings.BROWSER_HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )

            # Create a browser context with the LinkedIn session cookie
            browser_context = await self._create_authenticated_browser_context(
                browser
            )

            try:
                # --- Main company page ---
                main_data, main_raw = await self._scrape_company_main_page(
                    browser_context, company_slug
                )
                raw_records.append(main_raw)
                if not main_raw.scrape_success:
                    logger.warning(
                        f"[Layer 3] LinkedIn authentication failed or main page failed to load: {main_raw.error_message}. "
                        f"Skipping authenticated subpages."
                    )
                    return raw_records, combined_auth_data
                if main_data:
                    combined_auth_data.update(main_data)

                # --- Leadership/People page ---
                people_data, people_raw = await self._scrape_people_page(
                    browser_context, company_slug
                )
                raw_records.append(people_raw)
                if people_data:
                    combined_auth_data["leadership_team"] = people_data.get(
                        "leadership_team", []
                    )
                    combined_auth_data["employee_insights"] = people_data.get(
                        "employee_insights", {}
                    )

                # --- Posts page (full engagement data) ---
                posts_data, posts_raw = await self._scrape_posts_page(
                    browser_context, company_slug
                )
                raw_records.append(posts_raw)
                if posts_data:
                    combined_auth_data["recent_posts"] = posts_data

                # --- About page (funding, affiliated companies) ---
                about_data, about_raw = await self._scrape_about_page(
                    browser_context, company_slug
                )
                raw_records.append(about_raw)
                if about_data:
                    combined_auth_data["funding_info"] = about_data.get("funding_info")
                    combined_auth_data["affiliated_companies"] = about_data.get(
                        "affiliated_companies", []
                    )

            finally:
                await browser_context.close()
                await browser.close()

        logger.info(
            f"[Layer 3] Completed | company='{company_slug}' "
            f"| pages_scraped={len(raw_records)}"
        )

        return raw_records, combined_auth_data

    # ---------------------------------------------------------------------------
    # Browser Context Setup
    # ---------------------------------------------------------------------------

    async def _create_authenticated_browser_context(
        self,
        browser,
    ) -> BrowserContext:
        """
        Creates a Playwright BrowserContext pre-loaded with the LinkedIn
        session cookie (li_at), making the browser appear as a logged-in user.

        The context also uses a realistic viewport and User-Agent to blend
        in with normal browser traffic.
        """
        browser_context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Inject the LinkedIn session cookie
        await browser_context.add_cookies([
            {
                "name": "li_at",
                "value": settings.LINKEDIN_LI_AT,
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            }
        ])

        logger.info("[Layer 3] LinkedIn session cookie injected into browser context.")
        return browser_context

    # ---------------------------------------------------------------------------
    # Authenticated Page Scrapers
    # ---------------------------------------------------------------------------

    async def _scrape_company_main_page(
        self,
        browser_context: BrowserContext,
        company_slug: str,
    ) -> tuple[Optional[dict], RawLinkedInScrapedData]:
        """
        Scrapes the main company page while authenticated.
        Extracts follower count, about text preview, specialties, and company type.
        """
        page_url = build_company_page_url(company_slug)
        page = await browser_context.new_page()

        try:
            await page.goto(page_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)

            # Scroll to load dynamic content
            await self._scroll_page_gradually(page)

            page_content = await page.content()
            page_text = await page.inner_text("body")

            raw_record = RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_AUTHENTICATED,
                page_url=page_url,
                raw_html=page_content[:50_000],
                raw_text=page_text[:20_000],
                scraped_at=get_utc_now(),
                scrape_success=True,
            )

            # Extract followers count from the page text
            followers_count = self._extract_followers_count_from_text(page_text)

            extracted_data = {}
            if followers_count:
                extracted_data["followers_count"] = followers_count

            logger.info(
                f"[Layer 3] Main page scraped | "
                f"followers={followers_count}"
            )
            return extracted_data if extracted_data else None, raw_record

        except Exception as scrape_error:
            if "ERR_TOO_MANY_REDIRECTS" in str(scrape_error) or "redirect" in str(scrape_error).lower():
                logger.error(
                    f"[Layer 3] LinkedIn authentication failed (Too Many Redirects). "
                    f"Your LINKEDIN_LI_AT session cookie is likely invalid, expired, or blocked. "
                    f"Skipping Layer 3."
                )
            else:
                logger.error(
                    f"[Layer 3] Error scraping main page for '{company_slug}': {scrape_error}",
                    exc_info=True,
                )
            return None, RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_AUTHENTICATED,
                page_url=page_url,
                scraped_at=get_utc_now(),
                scrape_success=False,
                error_message=str(scrape_error),
            )
        finally:
            await page.close()

    async def _scrape_people_page(
        self,
        browser_context: BrowserContext,
        company_slug: str,
    ) -> tuple[Optional[dict], RawLinkedInScrapedData]:
        """
        Scrapes the /people page for leadership team members and employee insights.
        This page requires authentication to show meaningful data.
        """
        page_url = build_company_people_url(company_slug)
        page = await browser_context.new_page()

        try:
            await page.goto(page_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)
            await self._scroll_page_gradually(page)

            try:
                page_text = await page.inner_text("body")
                page_content = await page.content()
            except Exception as e:
                logger.warning(f"[Layer 3] Failed to read page contents, page context was destroyed: {e}")
                page_text = "Page context destroyed"
                page_content = "<html><body>Context destroyed</body></html>"

            raw_record = RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_AUTHENTICATED,
                page_url=page_url,
                raw_html=page_content[:50_000],
                raw_text=page_text[:20_000],
                scraped_at=get_utc_now(),
                scrape_success=True,
            )

            # Extract leadership members listed on the page
            leadership_members = []
            try:
                leadership_members = await self._extract_leadership_members(page)
            except Exception as e:
                logger.warning(f"[Layer 3] Failed to extract leadership members, context destroyed: {e}")

            people_data = {
                "leadership_team": [member.model_dump() for member in leadership_members],
            }

            logger.info(
                f"[Layer 3] People page scraped | "
                f"leadership_members_found={len(leadership_members)}"
            )
            return people_data, raw_record

        except Exception as scrape_error:
            logger.error(
                f"[Layer 3] Error scraping people page for '{company_slug}': {scrape_error}",
                exc_info=True,
            )
            return None, RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_AUTHENTICATED,
                page_url=page_url,
                scraped_at=get_utc_now(),
                scrape_success=False,
                error_message=str(scrape_error),
            )
        finally:
            await page.close()

    async def _scrape_posts_page(
        self,
        browser_context: BrowserContext,
        company_slug: str,
    ) -> tuple[Optional[list], RawLinkedInScrapedData]:
        """
        Scrapes the company posts feed while authenticated to get full
        engagement data (reactions, comments, reshares).
        """
        page_url = build_company_posts_url(company_slug)
        page = await browser_context.new_page()

        try:
            await page.goto(page_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)

            # Scroll multiple times to load more posts
            for _ in range(3):
                await self._scroll_page_gradually(page)
                await page.wait_for_timeout(2000)

            page_text = await page.inner_text("body")
            page_content = await page.content()

            raw_record = RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_AUTHENTICATED,
                page_url=page_url,
                raw_html=page_content[:50_000],
                raw_text=page_text[:20_000],
                scraped_at=get_utc_now(),
                scrape_success=True,
            )

            logger.info(
                f"[Layer 3] Posts page scraped | "
                f"raw_text_length={len(page_text)}"
            )

            # Raw text is returned here — Rules structurer will extract posts from it
            return [{"raw_posts_page_text": page_text[:15_000]}], raw_record

        except Exception as scrape_error:
            logger.error(
                f"[Layer 3] Error scraping posts page for '{company_slug}': {scrape_error}",
                exc_info=True,
            )
            return None, RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_AUTHENTICATED,
                page_url=page_url,
                scraped_at=get_utc_now(),
                scrape_success=False,
                error_message=str(scrape_error),
            )
        finally:
            await page.close()

    async def _scrape_about_page(
        self,
        browser_context: BrowserContext,
        company_slug: str,
    ) -> tuple[Optional[dict], RawLinkedInScrapedData]:
        """
        Scrapes the /about page while authenticated to get funding info
        and affiliated company details that are hidden behind login.
        """
        page_url = build_company_about_url(company_slug)
        page = await browser_context.new_page()

        try:
            await page.goto(page_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)
            await self._scroll_page_gradually(page)

            page_text = await page.inner_text("body")
            page_content = await page.content()

            raw_record = RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_AUTHENTICATED,
                page_url=page_url,
                raw_html=page_content[:50_000],
                raw_text=page_text[:20_000],
                scraped_at=get_utc_now(),
                scrape_success=True,
            )

            # Pass raw text to Rules structurer for funding/affiliated extraction
            about_data = {"raw_about_page_text": page_text[:15_000]}

            logger.info(
                f"[Layer 3] About page scraped | "
                f"raw_text_length={len(page_text)}"
            )
            return about_data, raw_record

        except Exception as scrape_error:
            logger.error(
                f"[Layer 3] Error scraping about page for '{company_slug}': {scrape_error}",
                exc_info=True,
            )
            return None, RawLinkedInScrapedData(
                company_slug=company_slug,
                scrape_layer=SCRAPE_LAYER_AUTHENTICATED,
                page_url=page_url,
                scraped_at=get_utc_now(),
                scrape_success=False,
                error_message=str(scrape_error),
            )
        finally:
            await page.close()

    # ---------------------------------------------------------------------------
    # Page Interaction Helpers
    # ---------------------------------------------------------------------------

    async def _scroll_page_gradually(self, page: Page) -> None:
        """
        Scrolls the page gradually to simulate human reading behavior
        and trigger lazy-loaded content to appear.

        Scrolls in 3 steps from top to bottom with random delays between.
        """
        try:
            viewport_height = await page.evaluate("window.innerHeight")
            scroll_positions = [
                viewport_height * 0.5,
                viewport_height * 1.5,
                viewport_height * 3.0,
            ]

            for scroll_position in scroll_positions:
                await page.evaluate(f"window.scrollTo(0, {scroll_position})")
                # Random pause between scrolls to simulate reading
                await page.wait_for_timeout(1500 + (500 * asyncio.get_event_loop().time() % 3))

            # Scroll back to top
            await page.evaluate("window.scrollTo(0, 0)")
        except Exception as e:
            logger.warning(f"Gradual scroll interrupted: {e}")

    async def _extract_leadership_members(
        self,
        page: Page,
    ) -> list[LeadershipMember]:
        """
        Attempts to extract leadership member cards from the People page.

        LinkedIn displays leadership members in a dedicated section.
        This method looks for name + title pairs in the page DOM.

        Returns:
            A list of LeadershipMember objects found on the page.
        """
        leadership_members: list[LeadershipMember] = []

        try:
            # LinkedIn's leadership section containers (selectors may change with UI updates)
            leadership_card_selectors = [
                ".org-top-card-summary-info-list__info-item",
                "[data-test-id='about-us__leadership'] a",
                ".org-people-profiles-module__profile-link",
            ]

            for selector in leadership_card_selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    for element in elements[:10]:  # Limit to first 10 leaders
                        element_text = await element.inner_text()
                        lines = [line.strip() for line in element_text.split("\n") if line.strip()]

                        if len(lines) >= 2:
                            member = LeadershipMember(
                                full_name=lines[0],
                                job_title=lines[1] if len(lines) > 1 else "Unknown",
                                linkedin_profile_url=await element.get_attribute("href"),
                            )
                            leadership_members.append(member)
                    break  # Stop after first selector that finds results

        except Exception as extraction_error:
            logger.warning(
                f"[Layer 3] Could not extract leadership members: {extraction_error}"
            )

        return leadership_members

    def _extract_followers_count_from_text(self, page_text: str) -> Optional[int]:
        """
        Parses the followers count from raw page text using pattern matching.

        LinkedIn displays followers as "X,XXX followers" or "X.XM followers".
        This method finds and converts that to an integer.

        Args:
            page_text: The full text content of a LinkedIn company page.

        Returns:
            Followers count as an integer, or None if not found.
        """
        import re

        # Pattern: "123,456 followers" or "1.2M followers"
        followers_pattern = re.compile(
            r"([\d,]+\.?\d*\s*[Mm]?)\s+followers",
            re.IGNORECASE,
        )

        match = followers_pattern.search(page_text)
        if not match:
            return None

        raw_count_string = match.group(1).replace(",", "")

        try:
            # Handle "1.2M" → 1,200,000
            if "m" in raw_count_string.lower():
                return int(float(raw_count_string.lower().replace("m", "")) * 1_000_000)
            return int(float(raw_count_string))
        except ValueError:
            return None
