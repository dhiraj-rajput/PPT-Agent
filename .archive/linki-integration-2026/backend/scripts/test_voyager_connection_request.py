import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.linkedin_worker import open_authenticated_context
from utils.db_client import get_db_session

async def send_via_voyager_api():
    print("=" * 70)
    print("SENDING CONNECTION REQUEST VIA VOYAGER API IN PLAYWRIGHT CONTEXT...")
    print("=" * 70)

    async for db in get_db_session():
        try:
            p_ctx, browser, context, page = await open_authenticated_context(6)
            
            # Go to profile first to ensure full cookie/CSRF context
            print("1. Loading profile: https://www.linkedin.com/in/dhiraj-rajput-/")
            await page.goto("https://www.linkedin.com/in/dhiraj-rajput-/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            print(f"2. Page loaded! Title: '{await page.title()}'")

            # Extract CSRF token from cookies
            cookies = await context.cookies()
            jsession = next((c["value"].strip('"') for c in cookies if c["name"] == "JSESSIONID"), "")
            print(f"3. CSRF Token (JSESSIONID): {jsession}")

            # Execute Voyager REST API fetch inside Playwright page context
            print("4. Executing Voyager REST API connection request fetch...")
            script = """
            async (csrfToken) => {
                const profileUrn = "ACoAAEWFPOQBPNiqODy13bNwYd0hPmshUqBsGzw";
                const noteText = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!";

                const payload = {
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
                            "content-type": "application/json",
                            "accept": "application/vnd.linkedin.normalized+json+2.0.0"
                        },
                        body: JSON.stringify(payload)
                    });
                    return { status: res.status, text: await res.text() };
                } catch (err) {
                    return { status: 0, text: String(err) };
                }
            }
            """

            api_result = await page.evaluate(script, jsession)
            print(f"5. Voyager API Response Status: {api_result.get('status')}")
            print(f"   Voyager API Response Body: {api_result.get('text')[:300]}")

            if api_result.get("status") in (200, 201):
                print("\n[SUCCESS] Connection request sent to Dhiraj Rajput via Voyager API!")
            else:
                print(f"   Status {api_result.get('status')} received. Retrying secondary endpoint...")
                script2 = """
                async (csrfToken) => {
                    const profileUrn = "ACoAAEWFPOQBPNiqODy13bNwYd0hPmshUqBsGzw";
                    const noteText = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Happy to connect!";
                    
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
                        return { status: res.status, text: await res.text() };
                    } catch (err) {
                        return { status: 0, text: String(err) };
                    }
                }
                """
                api_result2 = await page.evaluate(script2, jsession)
                print(f"   Secondary API Response Status: {api_result2.get('status')}")
                print(f"   Secondary API Response Body: {api_result2.get('text')[:300]}")
                if api_result2.get("status") in (200, 201):
                    print("\n[SUCCESS] Connection request sent to Dhiraj Rajput via Voyager API!")

            await browser.close()
        except Exception as e:
            print(f"[ERROR] Error during Voyager API dispatch: {e}")

if __name__ == "__main__":
    asyncio.run(send_via_voyager_api())
