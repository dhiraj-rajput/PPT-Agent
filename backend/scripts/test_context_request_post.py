import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def test_context_request():
    print("=" * 70)
    print("TESTING PLAYWRIGHT CONTEXT.REQUEST DIRECT POST...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            
            print("1. Loading profile page to initialize session...")
            await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            print(f"Loaded page: {page.url} | Title: '{await page.title()}'")

            # Retrieve cookies from context
            cookies = await context.cookies()
            jsession = next((c["value"].strip('"') for c in cookies if c["name"] == "JSESSIONID"), "")
            print(f"CSRF Token (JSESSIONID): {jsession}")

            profile_urn = "ACoAAEWFPOQBPNiqODy13bNwYd0hPmshUqBsGzw"
            note_msg = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"

            # Endpoint 1: growth/normInvitations
            payload1 = {
                "invitee": {
                    "com.linkedin.voyager.growth.invitation.InviteeProfile": {
                        "profileId": profile_urn
                    }
                },
                "customMessage": note_msg
            }

            print("\n2. Sending POST via context.request with json.dumps to /voyager/api/growth/normInvitations...")
            res1 = await context.request.post(
                "https://www.linkedin.com/voyager/api/growth/normInvitations",
                headers={
                    "csrf-token": jsession,
                    "x-restli-protocol-version": "2.0.0",
                    "content-type": "application/json",
                    "accept": "application/vnd.linkedin.normalized+json+2.0.0",
                },
                data=json.dumps(payload1)
            )

            print(f"Endpoint 1 Status: {res1.status}")
            body1 = await res1.text()
            print(f"Endpoint 1 Response Body: {body1[:300]}")

            if res1.status in (200, 201):
                print("\n🎉🎉 [SUCCESS] Direct API Connection Request sent to Dhiraj Rajput!")
            else:
                # Endpoint 2: voyager/api/relationships/invitations
                payload2 = {
                    "trackingId": "",
                    "invitee": {
                        "com.linkedin.voyager.growth.invitation.InviteeProfile": {
                            "profileId": profile_urn
                        }
                    },
                    "customMessage": note_msg
                }

                print("\n3. Sending POST via context.request with secondary payload...")
                res2 = await context.request.post(
                    "https://www.linkedin.com/voyager/api/growth/normInvitations",
                    headers={
                        "csrf-token": jsession,
                        "x-restli-protocol-version": "2.0.0",
                        "content-type": "application/json; charset=UTF-8",
                        "accept": "application/json",
                    },
                    data=payload2
                )
                print(f"Endpoint 2 Status: {res2.status}")
                body2 = await res2.text()
                print(f"Endpoint 2 Response Body: {body2[:300]}")

                if res2.status in (200, 201):
                    print("\n🎉🎉 [SUCCESS] Direct API Connection Request sent to Dhiraj Rajput!")

            await browser.close()
        except Exception as e:
            print(f"Error during context request test: {e}")

if __name__ == "__main__":
    asyncio.run(test_context_request())
