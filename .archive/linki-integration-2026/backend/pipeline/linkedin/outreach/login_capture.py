import asyncio
import base64
import json
import logging
import random
from typing import Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
from playwright.async_api import async_playwright

from utils.db_client import get_db_session
from utils.encryption import encrypt_data
from models.sql_models import LinkedInAccount, FingerprintProfile, Proxy
from sqlalchemy import insert, select, update

logger = logging.getLogger(__name__)

# Map regions to realistic timezones and locales
REGION_CONFIGS = {
    "usa": {"timezone": "America/New_York", "locale": "en-US"},
    "asia": {"timezone": "Asia/Singapore", "locale": "en-SG"},
    "eu": {"timezone": "Europe/London", "locale": "en-GB"},
    "mea": {"timezone": "Asia/Dubai", "locale": "en-AE"},
    "other": {"timezone": "UTC", "locale": "en-US"},
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
]

def generate_fingerprint(region: str) -> Dict[str, Any]:
    config = REGION_CONFIGS.get(region, REGION_CONFIGS["other"])
    return {
        "user_agent": random.choice(USER_AGENTS),
        "viewport": "1280x800",
        "timezone": config["timezone"],
        "locale": config["locale"],
        "webgl_seed": f"{random.randint(100000, 999999)}"
    }

async def run_guided_login_websocket(websocket: WebSocket, region: str, label: str, user_id: int):
    """
    Main WebSocket loop:
    1. Allocate/create Proxy and FingerprintProfile.
    2. Start Playwright.
    3. Load login page.
    4. Start concurrent tasks:
       - Screenshot loop to stream page updates to client.
       - Cookie check loop to see if user has completed login.
       - Event listener to process client mouse/keyboard inputs.
    """
    await websocket.accept()
    logger.info(f"WebSocket connection accepted for user={user_id}, region={region}")

    # Generate fixed fingerprint
    fp = generate_fingerprint(region)

    playwright_ctx = None
    browser = None
    context = None
    page = None
    page_lock = asyncio.Lock()
    is_success = False

    try:
        await websocket.send_text(json.dumps({
            "type": "status",
            "status": "connecting",
            "message": "Initializing secure browser session..."
        }))

        playwright_ctx = await async_playwright().start()
        
        # Configure browser launch options
        browser = await playwright_ctx.chromium.launch(
            headless=True,  # Always headless for guided login stream
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
        )

        # Create context using the generated fingerprint
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=fp["user_agent"],
            locale=fp["locale"],
            timezone_id=fp["timezone"],
        )

        # This session is BORN here — if LinkedIn fingerprints this browser
        # as automated at the moment of login (even though a real human is
        # typing the actual credentials into the live-streamed page), it can
        # issue a short-lived/flagged session that gets silently invalidated
        # within minutes. That would explain sessions "expiring" almost
        # immediately regardless of anything the send flow does afterward.
        # Full stealth patch (matching session_loader.py) — mask ALL the common
        # headless-Chromium tells before anything loads.
        await context.add_init_script(
            """
            // 1. Hide webdriver flag
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // 2. Restore window.chrome (headless Chromium omits it)
            window.chrome = window.chrome || { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };

            // 3. Realistic language + plugin arrays
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const arr = [1, 2, 3, 4, 5];
                    arr.__proto__ = PluginArray.prototype;
                    return arr;
                }
            });

            // 4. Fix permissions.query for 'notifications'
            const _origPermQuery = window.navigator.permissions && window.navigator.permissions.query;
            if (_origPermQuery) {
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : _origPermQuery(parameters)
                );
            }

            // 5. Spoof hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

            // 6. Spoof device memory
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

            // 7. Fix outerHeight / outerWidth
            if (window.outerHeight === 0) {
                Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight });
            }
            if (window.outerWidth === 0) {
                Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth });
            }

            // 8. WebGL renderer / vendor spoofing
            const _origGetContext = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function(type, attrs) {
                const ctx = _origGetContext.call(this, type, attrs);
                if (!ctx) return ctx;
                if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
                    const _origGetParam = ctx.getParameter.bind(ctx);
                    ctx.getParameter = function(param) {
                        if (param === 37445) return 'Intel Inc.';
                        if (param === 37446) return 'Intel Iris OpenGL Engine';
                        return _origGetParam(param);
                    };
                }
                return ctx;
            };

            // 9. Canvas fingerprint noise
            const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                if (type === 'image/png' && this.width > 0) {
                    const ctx2d = _origGetContext.call(this, '2d');
                    if (ctx2d) {
                        const imageData = ctx2d.getImageData(0, 0, 1, 1);
                        imageData.data[0] = (imageData.data[0] + 1) % 256;
                        ctx2d.putImageData(imageData, 0, 0);
                    }
                }
                return _origToDataURL.apply(this, arguments);
            };
            """
        )

        page = await context.new_page()
        
        async with page_lock:
            await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        await websocket.send_text(json.dumps({
            "type": "status",
            "status": "ready",
            "message": "Browser ready. Please enter your credentials."
        }))

        # Loops
        async def screenshot_loop():
            nonlocal is_success
            while not is_success:
                try:
                    async with page_lock:
                        screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
                    base64_img = base64.b64encode(screenshot_bytes).decode("utf-8")
                    await websocket.send_text(json.dumps({
                        "type": "screen",
                        "image": base64_img
                    }))
                    await asyncio.sleep(0.5)  # 2 frames per second is sufficient
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Screenshot stream error: {e}")
                    break

        async def check_cookies_loop():
            nonlocal is_success
            while not is_success:
                try:
                    cookies = await context.cookies()
                    li_at_cookie = next((c for c in cookies if c["name"] == "li_at"), None)
                    jsession_cookie = next((c for c in cookies if c["name"] == "JSESSIONID"), None)
                    
                    if li_at_cookie:
                        is_success = True
                        logger.info("Found li_at cookie! Authentication successful.")

                        # IMPORTANT: capture every cookie LinkedIn issued for this
                        # session, not just li_at/JSESSIONID. LinkedIn's device/
                        # fraud-detection layer keys off the full cookie set
                        # (bcookie, bscookie, lidc, lang, etc. alongside li_at).
                        # Replaying only li_at+JSESSIONID from a *different*
                        # browser fingerprint/IP later is exactly what forces
                        # LinkedIn into a login/checkpoint redirect loop — see
                        # session_loader.py for how this full set gets replayed.
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
                                if c["name"] in (
                                    "li_at", "JSESSIONID", "bcookie", "bscookie",
                                    "lidc", "lang", "li_gc", "li_mc", "liap",
                                )
                            ]
                        }
                        encrypted_cookies = encrypt_data(json.dumps(cookie_data))

                        # Save to database
                        async for db in get_db_session():
                            # 1. Create FingerprintProfile
                            stmt_fp = insert(FingerprintProfile).values(
                                user_agent=fp["user_agent"],
                                viewport=fp["viewport"],
                                timezone=fp["timezone"],
                                locale=fp["locale"],
                                webgl_seed=fp["webgl_seed"]
                            )
                            res_fp = await db.execute(stmt_fp)
                            fp_id = res_fp.lastrowid

                            # 2. Attach a real, unassigned proxy for this region if the
                            # pool has one. Deliberately do NOT fabricate a placeholder
                            # proxy row here — a fake "mock://" endpoint is worse than no
                            # proxy at all, since downstream send code could try to
                            # actually route Playwright traffic through it. Leaving
                            # proxy_id null when no real proxy exists is the correct
                            # Phase 1 behavior (see plan doc, Phase 3 = real pool mgmt).
                            stmt_pr_lookup = select(Proxy).where(
                                Proxy.region == region,
                                Proxy.assigned_account_id.is_(None),
                            ).limit(1)
                            existing_proxy = (await db.execute(stmt_pr_lookup)).scalar_one_or_none()
                            pr_id = existing_proxy.id if existing_proxy else None

                            # 3. Create LinkedInAccount
                            stmt_acc = insert(LinkedInAccount).values(
                                user_id=user_id,
                                label=label,
                                region=region,
                                auth_method="guided_login",
                                session_cookie_encrypted=encrypted_cookies,
                                fingerprint_profile_id=fp_id,
                                proxy_id=pr_id,
                                status="warming_up",
                                daily_connection_cap=8,
                                daily_message_cap=15,
                                warmup_stage=0,
                                health_score=100
                            )
                            res_acc = await db.execute(stmt_acc)
                            acc_id = res_acc.lastrowid

                            # Link account back to proxy and fingerprint
                            await db.execute(
                                update(FingerprintProfile)
                                .where(FingerprintProfile.id == fp_id)
                                .values(linkedin_account_id=acc_id)
                            )
                            if pr_id:
                                await db.execute(
                                    update(Proxy)
                                    .where(Proxy.id == pr_id)
                                    .values(assigned_account_id=acc_id)
                                )
                            await db.commit()
                            logger.info(f"LinkedInAccount saved in MySQL: ID={acc_id}")

                        await websocket.send_text(json.dumps({
                            "type": "status",
                            "status": "authenticated",
                            "message": "Successfully connected LinkedIn account!"
                        }))
                        break
                    
                    await asyncio.sleep(1.0)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Cookie check error: {e}")
                    await asyncio.sleep(1.0)

        # Start background helper tasks
        scr_task = asyncio.create_task(screenshot_loop())
        cookie_task = asyncio.create_task(check_cookies_loop())

        # Receive events loop
        while not is_success:
            data = await websocket.receive_text()
            event = json.loads(data)
            evt_type = event.get("type")

            if evt_type == "click":
                x = event.get("x")
                y = event.get("y")
                if x is not None and y is not None:
                    async with page_lock:
                        await page.mouse.click(x, y)
            elif evt_type == "type":
                text = event.get("text", "")
                async with page_lock:
                    await page.keyboard.type(text)
            elif evt_type == "press":
                key = event.get("key", "")
                if key:
                    async with page_lock:
                        await page.keyboard.press(key)

        # Cancel background streams
        scr_task.cancel()
        cookie_task.cancel()
        await asyncio.gather(scr_task, cookie_task, return_exceptions=True)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected.")
    except Exception as e:
        logger.error(f"Error in guided login loop: {e}", exc_info=True)
        try:
            await websocket.send_text(json.dumps({
                "type": "status",
                "status": "error",
                "message": f"Connection lost: {str(e)}"
            }))
        except Exception:
            pass
    finally:
        # Cleanup Playwright objects
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright_ctx:
            await playwright_ctx.stop()
        logger.info("Playwright session terminated and resources cleaned up.")
