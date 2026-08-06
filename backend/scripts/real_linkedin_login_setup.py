import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.async_api import async_playwright
from utils.encryption import encrypt_data
from utils.db_client import get_db_session
from sqlalchemy import update, select
from models.sql_models import LinkedInAccount, LinkedInTarget, LinkedInMessageLog, Person

logging.basicConfig(level=logging.INFO)

async def login_and_setup_real_outreach():
    print("=" * 60)
    print("Logging into LinkedIn with real credentials for Akbar Patil...")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="Asia/Kolkata"
        )
        page = await context.new_page()
        
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Multi-selector fallback for email and password fields
        user_selector = "input[type='email'], input#username, input#session_key, input[name='session_key'], input[autocomplete='username']"
        pass_selector = "input[type='password'], input#password, input#session_password, input[name='session_password']"

        user_el = await page.wait_for_selector(user_selector, state="attached", timeout=15000)
        await user_el.fill("patilakbar88@gmail.com")

        pass_el = await page.wait_for_selector(pass_selector, state="attached", timeout=15000)
        await pass_el.fill("PatilAkbar@14")
        
        btn_selector = "button[type='submit'], button.btn__primary--large, button[data-litms-control-text='Sign in']"
        btn_el = await page.wait_for_selector(btn_selector, state="attached", timeout=15000)
        await btn_el.click()
        await page.wait_for_timeout(6000)

        current_url = page.url
        print(f"Post-login URL: {current_url}")

        if "/checkpoint" in current_url or "/challenge" in current_url:
            print("❌ LinkedIn requires a 2FA OTP code or CAPTCHA verification.")
            print("   Please use the Guided Login feature on the PPT-Agent Frontend to complete 2FA once.")
            await browser.close()
            return False

        cookies = await context.cookies()
        li_at_cookie = next((c for c in cookies if c["name"] == "li_at"), None)

        if not li_at_cookie:
            print("❌ Could not extract 'li_at' cookie after submission. Current page title:", await page.title())
            await browser.close()
            return False

        print("✅ Successfully authenticated! Retried 'li_at' session cookie.")

        cookie_data = {
            "cookies": [
                {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ".linkedin.com"),
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", True),
                    "sameSite": c.get("sameSite", "None") or "None",
                }
                for c in cookies
                if c["name"] in ("li_at", "JSESSIONID", "bcookie", "bscookie", "lidc", "lang")
            ]
        }
        encrypted_cookies = encrypt_data(json.dumps(cookie_data))

        async for db in get_db_session():
            # Update Account 6 with real session and active settings
            await db.execute(
                update(LinkedInAccount)
                .where(LinkedInAccount.id == 6)
                .values(
                    session_cookie_encrypted=encrypted_cookies,
                    status="active",
                    label="Akbar Patil",
                    timezone="Asia/Kolkata",
                    working_hours_start=0,
                    working_hours_end=24,
                    working_days="1,2,3,4,5,6,7"
                )
            )
            await db.commit()
            print("✅ Updated Account 6 ('Akbar Patil') in database with real session cookies & 24/7 window!")

            # Update target person URL to https://www.linkedin.com/in/dhiraj-rajput-/
            stmt_log = select(LinkedInMessageLog).where(LinkedInMessageLog.id == 8)
            msg = (await db.execute(stmt_log)).scalar_one_or_none()
            if msg:
                stmt_target = select(LinkedInTarget).where(LinkedInTarget.id == msg.target_id)
                target = (await db.execute(stmt_target)).scalar_one_or_none()
                if target:
                    stmt_person = select(Person).where(Person.id == target.person_id)
                    person = (await db.execute(stmt_person)).scalar_one_or_none()
                    if person:
                        person.linkedin_url = "https://www.linkedin.com/in/dhiraj-rajput-/"
                        person.full_name = "Dhiraj Rajput"
                        msg.status = "approved"
                        await db.commit()
                        print(f"✅ Updated target Person (ID={person.id}) URL to '{person.linkedin_url}' and approved message 8 for outreach send!")

        await browser.close()
        return True

if __name__ == "__main__":
    asyncio.run(login_and_setup_real_outreach())
