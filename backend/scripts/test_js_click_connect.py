import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def test_js_click():
    print("=" * 70)
    print("TESTING NATIVE MOUSE-EVENT DISPATCH ON CONNECT LINK...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            print("1. Loading profile page: https://www.linkedin.com/in/dhiraj-rajput-/")
            await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            print(f"2. Loaded Page: '{await page.title()}' at URL: {page.url}")

            # Locate Connect link
            connect_link = page.locator("a[aria-label*='to connect' i], a[href*='/preload/custom-invite/']").first

            if await connect_link.count() > 0:
                print("3. Found Connect link! Dispatching native MouseEvent 'click'...")
                
                # Dispatch native click event via JS so browser doesn't do a full page navigation to href
                await connect_link.evaluate("el => el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))")
                await page.wait_for_timeout(2500)

                print(f"4. Post-click URL: {page.url}")

                dialog = page.locator("div[role='dialog'], div.artdeco-modal")
                print(f"5. Dialog count post-click: {await dialog.count()}")

                if await dialog.count() > 0:
                    dialog_el = dialog.first
                    print(f"6. [SUCCESS] Connection modal dialog opened! Header text: {(await dialog_el.inner_text())[:150]}")

                    add_note_btn = dialog_el.locator("button:has-text('Add a note'), button[aria-label*='Add a note' i]")
                    if await add_note_btn.count() > 0:
                        print("7. Clicking 'Add a note' button...")
                        await add_note_btn.first.evaluate("el => el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))")
                        await page.wait_for_timeout(1000)

                        textarea = dialog_el.locator("textarea")
                        if await textarea.count() > 0:
                            note_text = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"
                            print(f"8. Filling connection note: '{note_text}'")
                            await textarea.first.fill(note_text)
                            await page.wait_for_timeout(1000)

                            send_btn = dialog_el.locator("button:has-text('Send'), button[aria-label*='Send' i]")
                            if await send_btn.count() > 0:
                                print("9. Clicking 'Send' button to deliver connection request...")
                                await send_btn.first.evaluate("el => el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))")
                                await page.wait_for_timeout(3000)
                                print("\n🎉 [SUCCESS] Real Connection Request sent to Dhiraj Rajput on LinkedIn!")
                            else:
                                print("[ERROR] Send button not found in modal.")
                        else:
                            print("[ERROR] Textarea not found in modal.")
                    else:
                        print("[ERROR] 'Add a note' button not found in modal.")
                else:
                    print("[ERROR] Modal dialog did not open after JS click dispatch.")
            else:
                print("[ERROR] Connect link not found on page.")

            await browser.close()
        except Exception as e:
            print(f"[ERROR] Error during JS click test: {e}")

if __name__ == "__main__":
    asyncio.run(test_js_click())
