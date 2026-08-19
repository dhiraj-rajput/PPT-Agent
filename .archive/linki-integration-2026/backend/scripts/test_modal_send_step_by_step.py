import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def step_by_step_send():
    print("=" * 70)
    print("STEP-BY-STEP PLAYWRIGHT CONNECT MODAL DISPATCHER")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            print("1. Navigating to profile: https://www.linkedin.com/in/dhiraj-rajput-/")
            await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            print(f"2. Page loaded! Title: '{await page.title()}'")

            # Connect link locator
            connect_link = page.locator("a[href*='/preload/custom-invite/'], a[aria-label*='to connect' i]").first
            if await connect_link.count() > 0:
                print("3. Found Connect link! Scrolling into view...")
                await connect_link.scroll_into_view_if_needed()
                await page.wait_for_timeout(1000)
                print("4. Clicking Connect link...")
                await connect_link.click()
                await page.wait_for_timeout(3000)

                print(f"5. Post-click URL: {page.url}")
                print(f"   Post-click Page Title: '{await page.title()}'")

                # Check if any dialog, modal, or custom invite textarea exists on page or frames
                dialog = page.locator("div[role='dialog'], div.artdeco-modal, div[class*='custom-invite']")
                dialog_count = await dialog.count()
                print(f"6. Dialogs/Modals count: {dialog_count}")

                textarea = page.locator("textarea")
                textarea_count = await textarea.count()
                print(f"7. Textareas count anywhere on page: {textarea_count}")

                buttons = page.locator("button")
                b_count = min(await buttons.count(), 20)
                print(f"8. Visible buttons post-click count: {b_count}")
                for i in range(b_count):
                    try:
                        txt = (await buttons.nth(i).inner_text()).strip().replace("\n", " ")
                        print(f"   Button #{i+1}: '{txt}'")
                    except Exception:
                        pass

                if textarea_count > 0:
                    note_text = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"
                    print(f"9. Filling textarea with note: '{note_text}'")
                    await textarea.first.fill(note_text)
                    await page.wait_for_timeout(1000)

                    send_btn = page.locator("button:has-text('Send'), button[aria-label*='Send' i]")
                    if await send_btn.count() > 0:
                        print("10. Clicking 'Send' button to deliver connection request...")
                        await send_btn.first.click()
                        await page.wait_for_timeout(3000)
                        print("\n[SUCCESS] Connection request successfully sent on LinkedIn to Dhiraj Rajput!")
                    else:
                        print("[ERROR] Could not find Send button.")
                else:
                    # Check if 'Add a note' button exists
                    add_note_btn = page.locator("button:has-text('Add a note'), button[aria-label*='Add a note' i], a:has-text('Add a note')")
                    if await add_note_btn.count() > 0:
                        print("Clicking 'Add a note' button...")
                        await add_note_btn.first.click()
                        await page.wait_for_timeout(1500)

                        textarea2 = page.locator("textarea")
                        if await textarea2.count() > 0:
                            note_text = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"
                            await textarea2.first.fill(note_text)
                            await page.wait_for_timeout(1000)

                            send_btn2 = page.locator("button:has-text('Send'), button[aria-label*='Send' i]")
                            if await send_btn2.count() > 0:
                                await send_btn2.first.click()
                                await page.wait_for_timeout(3000)
                                print("\n[SUCCESS] Connection request successfully sent on LinkedIn to Dhiraj Rajput!")
                            else:
                                print("[ERROR] Send button not found after clicking Add a note.")
                    else:
                        print("[NOTICE] Neither textarea nor 'Add a note' button was found post-click.")

            else:
                print("[ERROR] Could not find Connect link on profile page.")

            await browser.close()
        except Exception as e:
            print(f"[ERROR] Error during step-by-step send: {e}")

if __name__ == "__main__":
    asyncio.run(step_by_step_send())
