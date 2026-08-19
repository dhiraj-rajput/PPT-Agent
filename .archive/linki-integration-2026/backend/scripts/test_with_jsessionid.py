import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session
from utils.encryption import encrypt_data
from models.sql_models import LinkedInAccount
from sqlalchemy import update, select

async def update_full_cookies_and_test(jsession_val: str = ""):
    print("=" * 70)
    print("TESTING FULL COOKIE JAR (li_at + JSESSIONID)...")
    print("=" * 70)

    li_at_val = "AQEDAWrVNbsAgETwAAABn8c1Cz0AAAGf60GPPVYAn28wJNWqzOKqbXn6kaiW6i-8u603SyLV8KeokwpFroTXQox4SqERwP3BDHUc34Nyfn-ejB9YtoW43XIIRCdTPA1VR4Gp3zRAJwynxHvBamRC24bd"

    cookies_list = [
        {
            "name": "li_at",
            "value": li_at_val,
            "domain": ".linkedin.com",
            "path": "/",
            "secure": True,
            "sameSite": "None",
        }
    ]

    if jsession_val:
        cookies_list.append({
            "name": "JSESSIONID",
            "value": jsession_val if jsession_val.startswith('"') else f'"{jsession_val}"',
            "domain": ".linkedin.com",
            "path": "/",
            "secure": True,
            "sameSite": "None",
        })

    encrypted = encrypt_data(json.dumps({"cookies": cookies_list}))

    async for db in get_db_session():
        await db.execute(
            update(LinkedInAccount)
            .where(LinkedInAccount.id == 6)
            .values(session_cookie_encrypted=encrypted, status="active")
        )
        await db.commit()

        # Test session navigation
        p_ctx, browser, context, page = await open_authenticated_context(6)
        print(f"Loaded {len(cookies_list)} cookies into Playwright context.")
        
        await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        print(f"Page Title: '{await page.title()}' at URL: {page.url}")

        # Intercept or click Connect using e.preventDefault() via JS evaluate or locator click
        connect_link = page.locator("a[aria-label*='to connect' i], a[href*='/preload/custom-invite/']").first
        if await connect_link.count() > 0:
            print("Clicking Connect element...")
            await connect_link.click()
            await page.wait_for_timeout(3000)

            print(f"Post-click URL: {page.url}")
            dialog = page.locator("div[role='dialog'], div.artdeco-modal")
            print(f"Dialog count post-click: {await dialog.count()}")

        await browser.close()

if __name__ == "__main__":
    js_val = sys.argv[1] if len(sys.argv) > 1 else ""
    asyncio.run(update_full_cookies_and_test(js_val))
