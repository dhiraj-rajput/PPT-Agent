"""
pipeline/linkedin/outreach/profile_scraper.py
------------------------------------------------
Layer 3 profile scraping using Playwright with an authenticated session.
Extracts personal profile details for outreach personalization.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from config.settings import settings

logger = logging.getLogger(__name__)


class LinkedInProfileScraper:
    """
    Playwright-based scraper for individual LinkedIn personal profiles.
    Injects an active li_at (and optionally JSESSIONID) session cookie.
    """

    async def scrape_profile(
        self,
        profile_url: str,
        li_at: str,
        jsession_id: Optional[str] = None,
        proxy_url: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Scrape a LinkedIn profile page.

        Args:
            profile_url: The full LinkedIn URL of the target profile.
            li_at: Active 'li_at' session cookie value.
            jsession_id: Optional 'JSESSIONID' cookie value.
            proxy_url: Optional proxy URL to route request (e.g. http://host:port).
            user_agent: Optional custom User Agent.

        Returns:
            dict containing parsed profile details.
        """
        if not profile_url:
            return {"status": "failed", "error": "Profile URL is empty"}

        # Normalize profile URL
        if not profile_url.startswith("http"):
            profile_url = f"https://www.linkedin.com/in/{profile_url.strip('/')}"

        logger.info(f"[ProfileScraper] Starting scrape for URL: {profile_url}")
        
        async with async_playwright() as p:
            # Configure proxy if provided
            launch_args = ["--disable-blink-features=AutomationControlled"]
            proxy_config = None
            if proxy_url:
                proxy_config = {"server": proxy_url}
            elif getattr(settings, "SCRAPING_PROXY_URL", None):
                proxy_config = {"server": settings.SCRAPING_PROXY_URL}

            browser = await p.chromium.launch(
                headless=True,
                proxy=proxy_config,
                args=launch_args,
            )

            # Create context with fixed browser parameters
            ua = user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
            
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=ua,
                locale="en-US",
                timezone_id="America/New_York",
            )

            # Inject session cookies
            cookies = [
                {
                    "name": "li_at",
                    "value": li_at,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None",
                }
            ]
            if jsession_id:
                cookies.append({
                    "name": "JSESSIONID",
                    "value": f'"{jsession_id}"' if not jsession_id.startswith('"') else jsession_id,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "secure": True,
                    "sameSite": "None",
                })
            
            await context.add_cookies(cookies)
            
            page = await context.new_page()
            
            try:
                # Go to profile page
                await page.goto(profile_url, timeout=30000, wait_until="domcontentloaded")
                # Wait a few seconds to let JS run
                await page.wait_for_timeout(5000)
                
                # Check for login redirection or verification
                current_url = page.url
                if "login" in current_url or "checkpoint" in current_url:
                    logger.warning(f"[ProfileScraper] Scraper was redirected to checkpoint/login: {current_url}")
                    return {
                        "status": "failed",
                        "error": "Authentication expired or challenge encountered",
                        "redirect_url": current_url
                    }

                # Start extraction
                profile_data = await self._extract_details(page, profile_url)
                profile_data["status"] = "success"
                return profile_data

            except Exception as e:
                logger.error(f"[ProfileScraper] Error scraping profile {profile_url}: {e}", exc_info=True)
                return {"status": "failed", "error": str(e)}
            finally:
                await context.close()
                await browser.close()

    async def _extract_details(self, page: Page, url: str) -> Dict[str, Any]:
        """Extract core profile details using various selectors."""
        data = {
            "url": url,
            "full_name": "",
            "first_name": "",
            "last_name": "",
            "title": "",
            "headline": "",
            "organization_name": "",
            "summary": "",
            "experience": [],
        }

        # 1. Extract Full Name
        name_selectors = [
            "h1.text-heading-xlarge",
            "h1.vp-header__title",
            ".pv-text-details__left-panel h1",
            "h1"
        ]
        for sel in name_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible():
                    name_text = (await el.inner_text()).strip()
                    if name_text:
                        data["full_name"] = name_text
                        parts = name_text.split(" ", 1)
                        data["first_name"] = parts[0]
                        data["last_name"] = parts[1] if len(parts) > 1 else ""
                        break
            except Exception:
                pass

        # 2. Extract Headline
        headline_selectors = [
            ".text-body-medium",
            ".pv-text-details__left-panel .text-body-medium",
            "h2"
        ]
        for sel in headline_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible():
                    hl_text = (await el.inner_text()).strip()
                    if hl_text:
                        data["headline"] = hl_text
                        data["title"] = hl_text.split(" at ")[0] if " at " in hl_text else hl_text
                        if " at " in hl_text:
                            data["organization_name"] = hl_text.split(" at ")[1].split(" | ")[0].strip()
                        break
            except Exception:
                pass

        # 3. Extract About/Summary
        try:
            # Click "see more" if it exists in the about section
            about_section = page.locator("#about").first
            if await about_section.is_visible():
                see_more_btn = page.locator("#about ~ div .inline-show-more-text__button").first
                if await see_more_btn.is_visible():
                    await see_more_btn.click()
                    await page.wait_for_timeout(500)
                
                # Fetch text
                summary_el = page.locator("#about ~ div .pv-shared-text-with-see-more").first
                if await summary_el.is_visible():
                    data["summary"] = (await summary_el.inner_text()).strip()
                else:
                    # Fallback to direct text sibling
                    sibling_text = await page.evaluate(
                        "() => document.getElementById('about')?.nextElementSibling?.innerText"
                    )
                    if sibling_text:
                        data["summary"] = sibling_text.strip()
        except Exception as e:
            logger.debug(f"[ProfileScraper] Could not extract summary section: {e}")

        # 4. Extract Experience items
        try:
            exp_header = page.locator("#experience").first
            if await exp_header.is_visible():
                # Locate parent section container, scroll to it to trigger lazy loading
                await exp_header.scroll_into_view_if_needed()
                await page.wait_for_timeout(1000)

                # Get all experience items
                # LinkedIn structures experience as list items under the #experience sibling container
                items = page.locator("xpath=//div[@id='experience']/following-sibling::div//li[contains(@class, 'artdeco-list__item')]")
                count = await items.count()
                
                experiences = []
                for i in range(min(count, 5)):  # Cap at top 5 experiences
                    item = items.nth(i)
                    try:
                        # Extract title and company name
                        # Logged in layouts usually use nested spans
                        title_el = item.locator(".hoverable-link-text span[aria-hidden='true']").first
                        title_text = ""
                        if await title_el.is_visible():
                            title_text = (await title_el.inner_text()).strip()

                        company_el = item.locator("span.t-14.t-normal span[aria-hidden='true']").first
                        company_text = ""
                        if await company_el.is_visible():
                            company_text = (await company_el.inner_text()).strip()
                            # Strip out type information like " · Full-time"
                            if " · " in company_text:
                                company_text = company_text.split(" · ")[0].strip()

                        # Fallback parsing for flat texts inside list items
                        if not title_text:
                            text_lines = await item.all_inner_texts()
                            if text_lines:
                                lines = [line.strip() for line in text_lines[0].split("\n") if line.strip()]
                                if len(lines) > 0:
                                    title_text = lines[0]
                                if len(lines) > 1:
                                    company_text = lines[1]

                        if title_text or company_text:
                            experiences.append({
                                "title": title_text,
                                "company": company_text
                            })
                    except Exception:
                        pass
                
                data["experience"] = experiences
        except Exception as e:
            logger.debug(f"[ProfileScraper] Could not extract experience list: {e}")

        # Derive title and company if not set
        if not data["organization_name"] and data["experience"]:
            data["organization_name"] = data["experience"][0].get("company", "")
        if not data["title"] and data["experience"]:
            data["title"] = data["experience"][0].get("title", "")

        return data
