import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def inspect_buttons():
    print("=" * 70)
    print("INSPECTING PROFILE BUTTONS FOR patilakbar88@gmail.com...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            print(f"Loaded Page Title: '{await page.title()}' at URL: {page.url}")

            # Grab all visible text inside profile header section
            header = page.locator("div.ph5, div[class*='pv-top-card'], main").first
            
            buttons = header.locator("button, a")
            b_count = await buttons.count()
            print(f"Found {b_count} buttons/links in profile section:")

            for i in range(min(b_count, 35)):
                btn = buttons.nth(i)
                txt = (await btn.inner_text()).strip().replace("\n", " ")
                aria = await btn.get_attribute("aria-label") or ""
                href = await btn.get_attribute("href") or ""
                print(f"  [{i+1}] Tag: {await btn.evaluate('el => el.tagName')} | Text: '{txt}' | Aria: '{aria}' | Href: '{href}'")

            # Check if 'More' button exists and click it
            more_btn = header.locator("button:has-text('More'), button[aria-label*='More' i]").first
            if await more_btn.count() > 0:
                print("\nClicking profile 'More' button...")
                await more_btn.click()
                await page.wait_for_timeout(2000)

                dropdown_items = page.locator("div.artdeco-dropdown__content button, div.artdeco-dropdown__content a, div[role='menu'] button, div[role='menu'] a")
                d_count = await dropdown_items.count()
                print(f"Found {d_count} items inside 'More' dropdown:")
                for j in range(min(d_count, 20)):
                    item = dropdown_items.nth(j)
                    txt = (await item.inner_text()).strip().replace("\n", " ")
                    aria = await item.get_attribute("aria-label") or ""
                    print(f"   Dropdown #{j+1}: Text: '{txt}' | Aria: '{aria}'")

            await browser.close()
        except Exception as e:
            print(f"Error inspecting profile: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_buttons())
