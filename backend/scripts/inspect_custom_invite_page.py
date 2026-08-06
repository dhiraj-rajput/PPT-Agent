import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def inspect_invite_page():
    print("=" * 70)
    print("INSPECTING PRELOAD CUSTOM INVITE PAGE...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            url = "https://www.linkedin.com/preload/custom-invite/?vanityName=dhiraj-rajput-"
            print(f"Navigating directly to: {url}")
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            print(f"Page Title: '{await page.title()}' | URL: {page.url}")

            textareas = page.locator("textarea")
            t_count = await textareas.count()
            print(f"Textareas count: {t_count}")
            for i in range(t_count):
                ta = textareas.nth(i)
                print(f"   Textarea #{i+1}: name='{await ta.get_attribute('name')}' id='{await ta.get_attribute('id')}' placeholder='{await ta.get_attribute('placeholder')}'")

            buttons = page.locator("button, a.artdeco-button")
            b_count = await buttons.count()
            print(f"Buttons count: {b_count}")
            for i in range(min(b_count, 15)):
                btn = buttons.nth(i)
                txt = (await btn.inner_text()).strip().replace("\n", " ")
                print(f"   Button #{i+1}: Text: '{txt}' | Aria: '{await btn.get_attribute('aria-label')}'")

            if t_count > 0:
                print("\nFilling textarea with connection note...")
                note = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"
                await textareas.first.fill(note)
                await page.wait_for_timeout(1000)

                send_btn = page.locator("button:has-text('Send'), button[aria-label*='Send' i]")
                if await send_btn.count() > 0:
                    print("Clicking Send button to dispatch connection request...")
                    await send_btn.first.click()
                    await page.wait_for_timeout(3000)
                    print("\n🎉 [SUCCESS] Connection request sent via custom-invite page!")

            await browser.close()
        except Exception as e:
            print(f"Error inspecting invite page: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_invite_page())
