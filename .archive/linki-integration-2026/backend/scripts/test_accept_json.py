import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def test_accept_json():
    print("=" * 70)
    print("TESTING ACCEPT: APPLICATION/JSON ON VOYAGER ENDPOINTS...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            cookies = await context.cookies()
            jsession = next((c["value"].strip('"') for c in cookies if c["name"] == "JSESSIONID"), "")
            print(f"CSRF Token: {jsession}")

            profile_urn = "ACoAAEWFPOQBPNiqODy13bNwYd0hPmshUqBsGzw"
            note_msg = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"

            headers = {
                "csrf-token": jsession,
                "x-restli-protocol-version": "2.0.0",
                "x-li-lang": "en_US",
                "content-type": "application/json; charset=UTF-8",
                "accept": "application/json",
            }

            payload = {
                "invitee": {
                    "com.linkedin.voyager.growth.invitation.InviteeProfile": {
                        "profileId": profile_urn
                    }
                },
                "customMessage": note_msg
            }

            endpoints = [
                "https://www.linkedin.com/voyager/api/growth/normInvitations",
                "https://www.linkedin.com/voyager/api/relationships/invitations",
                "https://www.linkedin.com/voyager/api/voyagerGrowthNormInvitations",
            ]

            for url in endpoints:
                print(f"\nTesting POST {url}...")
                res = await context.request.post(
                    url,
                    headers=headers,
                    data=json.dumps(payload)
                )
                print(f"   Status: {res.status}")
                body = await res.text()
                print(f"   Response: {body[:300]}")
                if res.status in (200, 201):
                    print(f"\n🎉🎉 [SUCCESS] Connection request sent via {url}!")
                    break

            await browser.close()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_accept_json())
