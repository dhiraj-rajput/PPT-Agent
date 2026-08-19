import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def test_click_connect():
    print("=" * 60)
    print("[TEST] Testing profile Connect button interaction...")
    print("=" * 60)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            resp = await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            print(f"Loaded page: '{await page.title()}' at URL: {page.url}")

            # 1. Target main profile card container
            profile_card = page.locator("div.ph5, div[class*='pv-top-card'], section.artdeco-card").first
            
            # Direct Connect button/link inside profile card
            direct_connect = profile_card.locator("button:has-text('Connect'), a:has-text('Connect'), button[aria-label*='Connect' i], a[aria-label*='Connect' i]")
            
            connect_target = None
            if await direct_connect.count() > 0 and await direct_connect.first.is_visible():
                print(f"✓ Found direct Connect button inside profile card!")
                connect_target = direct_connect.first
            else:
                print("Direct Connect not visible. Checking profile card 'More' menu...")
                card_more = profile_card.locator("button:has-text('More'), button[aria-label*='More' i], button[aria-label*='actions' i]")
                if await card_more.count() > 0:
                    print("Found profile card 'More' button. Clicking...")
                    await card_more.first.click()
                    await page.wait_for_timeout(1500)
                    
                    dropdown = page.locator("div.artdeco-dropdown__content, div[role='menu']")
                    dropdown_connect = dropdown.locator("button:has-text('Connect'), a:has-text('Connect'), div:has-text('Connect'), span:has-text('Connect')")
                    if await dropdown_connect.count() > 0:
                        print("✓ Found Connect option inside profile 'More' dropdown!")
                        connect_target = dropdown_connect.first

            if connect_target:
                print("Clicking Connect button...")
                await connect_target.click()
                await page.wait_for_timeout(2500)

                # Check modal
                dialog = page.locator("div[role='dialog'], div.artdeco-modal")
                if await dialog.count() > 0:
                    print(f"✓ Modal opened! Dialog text snippet: {(await dialog.first.inner_text())[:150]}")
                    
                    # Fill note
                    add_note_btn = dialog.get_by_role("button", name="Add a note", exact=False)
                    if await add_note_btn.count() > 0:
                        print("Clicking 'Add a note' button...")
                        await add_note_btn.first.click()
                        await page.wait_for_timeout(1000)

                        textarea = dialog.locator("textarea")
                        if await textarea.count() > 0:
                            note_msg = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"
                            await textarea.first.fill(note_msg)
                            print(f"✓ Filled note into textarea: '{note_msg}'")

                            send_btn = dialog.get_by_role("button", name="Send", exact=False)
                            if await send_btn.count() > 0:
                                print("Clicking 'Send' button to dispatch connection request...")
                                await send_btn.first.click()
                                await page.wait_for_timeout(3000)
                                print("🎉 SUCCESS: Connection request sent with note!")
            else:
                print("❌ Could not locate Connect button in profile card or 'More' menu.")

            await browser.close()
        except Exception as e:
            print(f"❌ Error during test: {e}")

if __name__ == "__main__":
    asyncio.run(test_click_connect())
