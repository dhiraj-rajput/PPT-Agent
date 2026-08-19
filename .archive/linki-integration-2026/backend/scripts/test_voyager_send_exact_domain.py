import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session
from utils.encryption import encrypt_data
from models.sql_models import LinkedInAccount, LinkedInTarget, LinkedInMessageLog, Person
from sqlalchemy import update, select

async def main():
    print("=" * 70)
    print("EXECUTING REAL VOYAGER CONNECTION SEND WITH EXACT COOKIE DOMAINS...")
    print("=" * 70)

    li_at_val = "AQEDAWrVNbsAgETwAAABn8c1Cz0AAAGf60GPPVYAn28wJNWqzOKqbXn6kaiW6i-8u603SyLV8KeokwpFroTXQox4SqERwP3BDHUc34Nyfn-ejB9YtoW43XIIRCdTPA1VR4Gp3zRAJwynxHvBamRC24bd"
    jsession_val = '"ajax:2294238019749696641"'

    cookies = [
        {"name": "li_at", "value": li_at_val, "domain": ".linkedin.com", "path": "/", "secure": True, "sameSite": "None"},
        {"name": "li_at", "value": li_at_val, "domain": ".www.linkedin.com", "path": "/", "secure": True, "sameSite": "None"},
        {"name": "JSESSIONID", "value": jsession_val, "domain": ".linkedin.com", "path": "/", "secure": True, "sameSite": "None"},
        {"name": "JSESSIONID", "value": jsession_val, "domain": ".www.linkedin.com", "path": "/", "secure": True, "sameSite": "None"},
        {"name": "JSESSIONID", "value": jsession_val, "domain": "www.linkedin.com", "path": "/", "secure": True, "sameSite": "None"},
    ]

    encrypted = encrypt_data(json.dumps({"cookies": cookies}))

    async for db in get_db_session():
        # Update Account 6
        await db.execute(
            update(LinkedInAccount)
            .where(LinkedInAccount.id == 6)
            .values(
                session_cookie_encrypted=encrypted,
                status="active",
                label="Akbar Patil",
                timezone="Asia/Kolkata",
                working_hours_start=0,
                working_hours_end=24,
                working_days="1,2,3,4,5,6,7"
            )
        )
        await db.commit()
        print("[OK] Updated Account 6 with multi-domain cookie jar!")

        # Open Playwright context
        p_ctx, browser, context, page = await open_authenticated_context(6)
        print("[OK] Opened authenticated Playwright context.")

        print("Navigating to profile: https://www.linkedin.com/in/dhiraj-rajput-/")
        await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        page_title = await page.title()
        print(f"Page Title: '{page_title}' | URL: {page.url}")

        # Execute Voyager Connection Request API via evaluate
        csrf_token = "ajax:2294238019749696641"
        note_text = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"
        target_profile_urn = "ACoAAEWFPOQBPNiqODy13bNwYd0hPmshUqBsGzw"

        voyager_script = """
        async ({ csrfToken, profileUrn, noteText }) => {
            const payload = {
                "invitee": {
                    "com.linkedin.voyager.growth.invitation.InviteeProfile": {
                        "profileId": profileUrn
                    }
                },
                "customMessage": noteText
            };

            try {
                const endpointUrl = window.location.origin + "/voyager/api/growth/normInvitations";
                const res = await fetch(endpointUrl, {
                    method: "POST",
                    headers: {
                        "csrf-token": csrfToken,
                        "x-restli-protocol-version": "2.0.0",
                        "content-type": "application/json",
                        "accept": "application/vnd.linkedin.normalized+json+2.0.0"
                    },
                    body: JSON.stringify(payload)
                });
                return { status: res.status, body: await res.text() };
            } catch (err) {
                return { status: 0, body: String(err) };
            }
        }
        """

        print("\n[DISPATCH] Invoking Voyager API connection request fetch...")
        res = await page.evaluate(voyager_script, {
            "csrfToken": csrf_token,
            "profileUrn": target_profile_urn,
            "noteText": note_text
        })

        print("=" * 70)
        print(f"Voyager API Status: {res.get('status')}")
        print(f"Voyager API Body:   {res.get('body')[:300]}")
        print("=" * 70)

        if res.get("status") in (200, 201):
            print("\n🎉 [SUCCESS] Real Connection Request sent to Dhiraj Rajput on LinkedIn!")
        else:
            print("Notice: Checking secondary normInvitations format...")
            voyager_script2 = """
            async ({ csrfToken, profileUrn, noteText }) => {
                const payload = {
                    "trackingId": "",
                    "invitee": {
                        "com.linkedin.voyager.growth.invitation.InviteeProfile": {
                            "profileId": profileUrn
                        }
                    },
                    "customMessage": noteText
                };

                try {
                    const res = await fetch("https://www.linkedin.com/voyager/api/growth/normInvitations", {
                        method: "POST",
                        credentials: "include",
                        headers: {
                            "csrf-token": csrfToken,
                            "x-restli-protocol-version": "2.0.0",
                            "content-type": "application/json; charset=UTF-8",
                            "accept": "application/json"
                        },
                        body: JSON.stringify(payload)
                    });
                    return { status: res.status, body: await res.text() };
                } catch (err) {
                    return { status: 0, body: String(err) };
                }
            }
            """
            res2 = await page.evaluate(voyager_script2, {
                "csrfToken": csrf_token,
                "profileUrn": target_profile_urn,
                "noteText": note_text
            })
            print(f"Secondary Voyager Status: {res2.get('status')}")
            print(f"Secondary Voyager Body:   {res2.get('body')[:300]}")
            if res2.get("status") in (200, 201):
                print("\n🎉 [SUCCESS] Real Connection Request sent to Dhiraj Rajput on LinkedIn!")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
