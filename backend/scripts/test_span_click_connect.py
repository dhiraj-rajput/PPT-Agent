import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def test_span_click():
    print("=" * 70)
    print("TESTING SPAN / BUTTON CONNECT DISPATCH...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            print("1. Loading profile: https://www.linkedin.com/in/dhiraj-rajput-/")
            await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            print(f"2. Loaded Page: '{await page.title()}' at URL: {page.url}")

            # Find Connect inner span or role button
            connect_span = page.locator("a[aria-label*='to connect' i] span:has-text('Connect'), button:has-text('Connect')").first
            
            if await connect_span.count() > 0:
                print("3. Found Connect span element! Scrolling into view...")
                await connect_span.scroll_into_view_if_needed()
                await page.wait_for_timeout(1000)
                print("4. Clicking Connect span element...")
                await connect_span.click()
                await page.wait_for_timeout(3000)

                print(f"5. Post-click URL: {page.url}")
                print(f"   Post-click Page Title: '{await page.title()}'")

                # Check modal
                dialog = page.locator("div[role='dialog'], div.artdeco-modal")
                if await dialog.count() > 0:
                    print("6. [SUCCESS] Modal dialog opened!")
                    dialog_el = dialog.first

                    add_note_btn = dialog_el.locator("button:has-text('Add a note'), button[aria-label*='Add a note' i]")
                    if await add_note_btn.count() > 0:
                        print("7. Clicking 'Add a note' button...")
                        await add_note_btn.first.click()
                        await page.wait_for_timeout(1500)

                        textarea = dialog_el.locator("textarea")
                        if await textarea.count() > 0:
                            note_text = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"
                            print(f"8. Filling connection note: '{note_text}'")
                            await textarea.first.fill(note_text)
                            await page.wait_for_timeout(1000)

                            send_btn = dialog_el.locator("button:has-text('Send'), button[aria-label*='Send' i]")
                            if await send_btn.count() > 0:
                                print("9. Clicking 'Send' button to deliver connection request...")
                                await send_btn.first.click()
                                await page.wait_for_timeout(3000)
                                print("\n🎉 [SUCCESS] Connection request with note SENT SUCCESSFULLY to Dhiraj Rajput!")
                            else:
                                print("[ERROR] Could not find Send button in modal.")
                        else:
                            print("[ERROR] Textarea not found in modal.")
                    else:
                        print("[ERROR] 'Add a note' button not found in modal.")
                else:
                    print("[ERROR] Modal dialog did not open.")
            else:
                print("[ERROR] Connect span element not found on page.")

            await browser.close()
        except Exception as e:
            print(f"[ERROR] Error during test: {e}")

if __name__ == "__main__":
    asyncio.run(test_span_click())
