import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def test_preload_invite():
    print("=" * 70)
    print("TESTING DIRECT PRELOAD CUSTOM-INVITE MODAL DISPATCH...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)

            # Step 1: Visit main profile first to set referrer context
            profile_url = "https://www.linkedin.com/in/dhiraj-rajput-/"
            vanity_name = profile_url.rstrip("/").split("/")[-1]
            print(f"1. Loading profile: {profile_url} (vanityName={vanity_name})")
            await page.goto(profile_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # Step 2: Trigger custom-invite popup via evaluate dispatch or direct preload URL
            preload_url = f"https://www.linkedin.com/preload/custom-invite/?vanityName={vanity_name}"
            print(f"2. Navigating to preload custom-invite modal URL: {preload_url}")
            await page.goto(preload_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            print(f"   Current URL: {page.url} | Title: '{await page.title()}'")

            # Look for "Add a note to your invitation?" modal or dialog
            dialog = page.locator("div[role='dialog'], div.artdeco-modal, main")
            
            # Check for Add a note button
            add_note_btn = page.locator("button:has-text('Add a note'), button[aria-label*='Add a note' i], a:has-text('Add a note')")
            
            if await add_note_btn.count() > 0 and await add_note_btn.first.is_visible():
                print("3. [SUCCESS] Found 'Add a note' button in custom-invite modal! Clicking...")
                await add_note_btn.first.click()
                await page.wait_for_timeout(1500)

                textarea = page.locator("textarea")
                if await textarea.count() > 0:
                    note_msg = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"
                    print(f"4. Filling note: '{note_msg}'")
                    await textarea.first.fill(note_msg)
                    await page.wait_for_timeout(1000)

                    send_btn = page.locator("button:has-text('Send'), button[aria-label*='Send' i]")
                    if await send_btn.count() > 0:
                        print("5. Clicking 'Send' button to deliver connection request...")
                        await send_btn.first.click()
                        await page.wait_for_timeout(3000)
                        print("\n🎉 [SUCCESS] Real Connection Request sent to Dhiraj Rajput on LinkedIn!")
                    else:
                        print("[ERROR] Send button not found in modal.")
                else:
                    print("[ERROR] Textarea not found in modal.")
            else:
                # Check if textarea is already visible directly
                textarea = page.locator("textarea")
                if await textarea.count() > 0 and await textarea.first.is_visible():
                    print("3. [SUCCESS] Textarea already visible in custom-invite modal! Filling note...")
                    note_msg = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"
                    await textarea.first.fill(note_msg)
                    await page.wait_for_timeout(1000)

                    send_btn = page.locator("button:has-text('Send'), button[aria-label*='Send' i]")
                    if await send_btn.count() > 0:
                        print("4. Clicking 'Send' button to deliver connection request...")
                        await send_btn.first.click()
                        await page.wait_for_timeout(3000)
                        print("\n🎉 [SUCCESS] Real Connection Request sent to Dhiraj Rajput on LinkedIn!")

            await browser.close()
        except Exception as e:
            print(f"[ERROR] Error during preload invite test: {e}")

if __name__ == "__main__":
    asyncio.run(test_preload_invite())
