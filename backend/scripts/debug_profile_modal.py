import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def debug_modal():
    print("=" * 70)
    print("DEBUGGING PROFILE MODAL OPENING...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            
            print("1. Loading profile with networkidle...")
            await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="networkidle")
            await page.wait_for_timeout(3000)

            print(f"Loaded page: {page.url} | Title: '{await page.title()}'")

            # Check all elements with aria-label containing 'connect' or 'More'
            elements = page.locator("a[aria-label*='connect' i], button[aria-label*='More' i], button:has-text('More')")
            cnt = await elements.count()
            print(f"Found {cnt} potential action elements:")
            for i in range(cnt):
                el = elements.nth(i)
                txt = (await el.inner_text()).strip().replace("\n", " ")
                aria = await el.get_attribute("aria-label") or ""
                href = await el.get_attribute("href") or ""
                tag = await el.evaluate("e => e.tagName")
                print(f"  [{i+1}] {tag} | text='{txt}' | aria='{aria}' | href='{href}'")

            # Prevent navigation to /preload/ via JS on all <a> tags with preload in href
            print("\n2. Injecting preventDefault on preload links...")
            await page.evaluate("""
                document.querySelectorAll("a[href*='/preload/']").forEach(a => {
                    a.addEventListener('click', (e) => {
                        console.log('Intercepted preload link click');
                    });
                });
            """)

            # Try clicking the Connect link
            connect_link = page.locator("a[href*='/preload/custom-invite/']").first
            if await connect_link.count() > 0:
                print("3. Clicking Connect link...")
                await connect_link.click()
                await page.wait_for_timeout(3000)

                print(f"Post-click URL: {page.url}")
                dialogs = page.locator("div[role='dialog'], div.artdeco-modal")
                print(f"Dialog count: {await dialogs.count()}")
                if await dialogs.count() > 0:
                    print("SUCCESS! Dialog opened!")
                    print(f"Dialog content snippet: {(await dialogs.first.inner_text())[:200]}")
                else:
                    print("Dialog did not open. Trying profile card 'More' button...")
                    # Click the 2nd 'More' button (profile top-card More button)
                    more_btns = page.locator("button[aria-label='More'], button:has-text('More')")
                    for k in range(await more_btns.count()):
                        m_btn = more_btns.nth(k)
                        if await m_btn.is_visible():
                            print(f"Clicking visible More button #{k+1}...")
                            await m_btn.click()
                            await page.wait_for_timeout(1500)
                            
                            dropdown = page.locator("div.artdeco-dropdown__content, div[role='menu']")
                            if await dropdown.count() > 0 and await dropdown.first.is_visible():
                                print(f"Dropdown items snippet: {(await dropdown.first.inner_text())[:200]}")
                                connect_opt = dropdown.locator("*:has-text('Connect')").first
                                if await connect_opt.count() > 0:
                                    print("Found Connect inside More dropdown! Clicking...")
                                    await connect_opt.click()
                                    await page.wait_for_timeout(2500)
                                    print(f"Dialog count post dropdown click: {await page.locator('div[role=\"dialog\"], div.artdeco-modal').count()}")
                                    break

            await browser.close()
        except Exception as e:
            print(f"Error during debug: {e}")

if __name__ == "__main__":
    asyncio.run(debug_modal())
