import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def test_all_endpoints():
    print("=" * 70)
    print("TESTING VOYAGER API ENDPOINT VARIANTS...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            cookies = await context.cookies()
            jsession = next((c["value"].strip('"') for c in cookies if c["name"] == "JSESSIONID"), "")
            print(f"CSRF Token (JSESSIONID): {jsession}")

            profile_urn = "ACoAAEWFPOQBPNiqODy13bNwYd0hPmshUqBsGzw"
            note_msg = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!"

            headers = {
                "csrf-token": jsession,
                "x-restli-protocol-version": "2.0.0",
                "content-type": "application/json",
                "accept": "application/vnd.linkedin.normalized+json+2.0.0",
            }

            endpoints = [
                (
                    "https://www.linkedin.com/voyager/api/voyagerGrowthNormInvitations",
                    {
                        "invitee": {
                            "com.linkedin.voyager.growth.invitation.InviteeProfile": {
                                "profileId": profile_urn
                            }
                        },
                        "customMessage": note_msg
                    }
                ),
                (
                    "https://www.linkedin.com/voyager/api/voyagerGrowthNormInvitations",
                    {
                        "invitee": {
                            "com.linkedin.voyager.growth.invitation.InviteeProfile": {
                                "profileUrn": f"urn:li:fsd_profile:{profile_urn}"
                            }
                        },
                        "customMessage": note_msg
                    }
                ),
                (
                    "https://www.linkedin.com/voyager/api/voyagerRelationshipsDashMemberRelationships?action=verifyQuotaAndConnect",
                    {
                        "invitee": {
                            "com.linkedin.voyager.dash.relationships.InviteeProfile": {
                                "profileUrn": f"urn:li:fsd_profile:{profile_urn}"
                            }
                        },
                        "customMessage": note_msg
                    }
                )
            ]

            for idx, (url, payload) in enumerate(endpoints, start=1):
                print(f"\n[{idx}] Testing POST {url}...")
                res = await context.request.post(
                    url,
                    headers=headers,
                    data=json.dumps(payload)
                )
                print(f"    Status: {res.status}")
                body = await res.text()
                print(f"    Response Snippet: {body[:250]}")

                if res.status in (200, 201):
                    print(f"\n🎉🎉 [SUCCESS!] Endpoint #{idx} succeeded with status {res.status}!")
                    break

            await browser.close()
        except Exception as e:
            print(f"Error during endpoint sweep: {e}")

if __name__ == "__main__":
    asyncio.run(test_all_endpoints())
