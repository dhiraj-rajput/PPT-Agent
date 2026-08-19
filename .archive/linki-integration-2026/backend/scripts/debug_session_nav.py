import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def test_session():
    print("=" * 60)
    print("Testing session navigation to target profile...")
    print("=" * 60)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            print("1. Opening authenticated context...")
            resp = await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            print(f"2. Response status: {resp.status if resp else 'None'}")
            print(f"3. Page URL: {page.url}")
            print(f"4. Page title: '{await page.title()}'")

            buttons = page.get_by_role("button")
            print(f"5. Total buttons count: {await buttons.count()}")

            # Print first 10 button text labels
            b_count = min(await buttons.count(), 15)
            for i in range(b_count):
                txt = (await buttons.nth(i).inner_text()).strip().replace("\n", " ")
                print(f"   Button #{i+1}: '{txt}'")

            connect_elems = page.locator("a[aria-label*='connect' i], button:has-text('Connect'), a:has-text('Connect')")
            print(f"6. Connect elements count: {await connect_elems.count()}")

            await browser.close()
        except Exception as e:
            print(f"❌ Error during test: {e}")

if __name__ == "__main__":
    asyncio.run(test_session())
