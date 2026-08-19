import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def execute_real_send():
    print("=" * 70)
    print("EXECUTING REAL VOYAGER API CONNECTION SEND (GUARANTEED)...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            
            # Step 1: Visit main profile
            print("1. Loading target profile page...")
            await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            print(f"Page Title: '{await page.title()}'")

            # Step 2: Retrieve JSESSIONID token from context cookies
            cookies = await context.cookies()
            jsession = next((c["value"].strip('"') for c in cookies if c["name"] == "JSESSIONID"), "")
            print(f"CSRF Token (JSESSIONID): {jsession}")

            # Step 3: Dispatch Voyager API connection request via page.evaluate
            target_urn = "ACoAAEWFPOQBPNiqODy13bNwYd0hPmshUqBsGzw"
            note_message = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Would love to connect!"

            api_script = """
            async ({ csrfToken, targetUrn, note }) => {
                const payload = {
                    "invitee": {
                        "com.linkedin.voyager.growth.invitation.InviteeProfile": {
                            "profileId": targetUrn
                        }
                    },
                    "customMessage": note
                };

                const res = await fetch("/voyager/api/growth/normInvitations", {
                    method: "POST",
                    headers: {
                        "csrf-token": csrfToken,
                        "x-restli-protocol-version": "2.0.0",
                        "content-type": "application/json",
                        "accept": "application/vnd.linkedin.normalized+json+2.0.0"
                    },
                    body: JSON.stringify(payload)
                });
                return { status: res.status, text: await res.text() };
            }
            """

            print("\n2. Dispatching connection request via Voyager REST API...")
            res = await page.evaluate(api_script, {
                "csrfToken": jsession,
                "targetUrn": target_urn,
                "note": note_message
            })

            print("=" * 70)
            print(f"Voyager API Status: {res.get('status')}")
            print(f"Voyager API Response: {res.get('text')[:300]}")
            print("=" * 70)

            if res.get("status") in (200, 201):
                print("\n🎉🎉 [SUCCESS] CONNECTION REQUEST WITH CUSTOM NOTE SENT TO DHIRAJ RAJPUT ON LINKEDIN!")
            else:
                print("Checking secondary Voyager payload format...")
                api_script2 = """
                async ({ csrfToken, targetUrn, note }) => {
                    const payload = {
                        "trackingId": "",
                        "invitee": {
                            "com.linkedin.voyager.growth.invitation.InviteeProfile": {
                                "profileId": targetUrn
                            }
                        },
                        "customMessage": note
                    };

                    const res = await fetch("/voyager/api/growth/normInvitations", {
                        method: "POST",
                        headers: {
                            "csrf-token": csrfToken,
                            "x-restli-protocol-version": "2.0.0",
                            "content-type": "application/json; charset=UTF-8",
                            "accept": "application/json"
                        },
                        body: JSON.stringify(payload)
                    });
                    return { status: res.status, text: await res.text() };
                }
                """
                res2 = await page.evaluate(api_script2, {
                    "csrfToken": jsession,
                    "targetUrn": target_urn,
                    "note": note_message
                })
                print(f"Secondary Voyager Status: {res2.get('status')}")
                print(f"Secondary Voyager Response: {res2.get('text')[:300]}")
                if res2.get("status") in (200, 201):
                    print("\n🎉🎉 [SUCCESS] CONNECTION REQUEST WITH CUSTOM NOTE SENT TO DHIRAJ RAJPUT ON LINKEDIN!")

            await browser.close()
        except Exception as e:
            print(f"[ERROR] {e}")

if __name__ == "__main__":
    asyncio.run(execute_real_send())
