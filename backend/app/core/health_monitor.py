import asyncio
import json
import logging
from datetime import datetime
from sqlalchemy import select, update, insert
from playwright.async_api import async_playwright

from utils.db_client import get_db_session
from utils.encryption import decrypt_data
from models.sql_models import LinkedInAccount, Notification, AuditLog

logger = logging.getLogger(__name__)

async def check_account_health_with_playwright(account_id: int, decrypted_cookies: dict) -> str:
    """
    Checks the cookie session health of a single LinkedIn account.
    Returns: 'active', 'expired', 'flagged', or 'error'
    """
    playwright_ctx = None
    browser = None
    context = None
    try:
        playwright_ctx = await async_playwright().start()
        browser = await playwright_ctx.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Inject session cookie
        await context.add_cookies([
            {
                "name": "li_at",
                "value": decrypted_cookies["li_at"],
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            }
        ])

        page = await context.new_page()
        # Navigate to a lightweight authenticated endpoint
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)

        current_url = page.url
        logger.info(f"Health check navigation complete for account {account_id}. Current URL: {current_url}")

        if "/login" in current_url or "/signup" in current_url:
            return "expired"
        elif "/checkpoint" in current_url or "checkpoint" in current_url or "/restricted" in current_url:
            return "flagged"
        else:
            return "active"

    except Exception as e:
        logger.error(f"Health check browser error for account {account_id}: {e}")
        return "error"
    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright_ctx:
            await playwright_ctx.stop()

async def check_all_accounts_health():
    """
    Loads all accounts with active/warming_up/connecting/flagged states
    and validates their sessions.
    """
    logger.info("Starting LinkedIn account health monitoring routine.")
    accounts = []
    
    async for db in get_db_session():
        stmt = select(LinkedInAccount).where(
            LinkedInAccount.status.in_(["active", "warming_up", "connecting", "flagged"])
        )
        res = await db.execute(stmt)
        accounts = res.scalars().all()

        for acc in accounts:
            if not acc.session_cookie_encrypted:
                continue

            try:
                decrypted = json.loads(decrypt_data(acc.session_cookie_encrypted))
            except Exception as e:
                logger.error(f"Failed to decrypt cookies for account {acc.id}: {e}")
                continue

            logger.info(f"Running health check for account ID={acc.id} ({acc.label})")
            status_result = await check_account_health_with_playwright(acc.id, decrypted)

            if status_result == "active" and acc.status in ["connecting", "flagged"]:
                # Restore status
                new_status = "active" if acc.warmup_stage > 0 else "warming_up"
                await db.execute(
                    update(LinkedInAccount)
                    .where(LinkedInAccount.id == acc.id)
                    .values(status=new_status, health_score=100, updated_at=datetime.utcnow())
                )
                await db.execute(
                    insert(AuditLog).values(
                        action="health_restore",
                        entity_type="linkedin_accounts",
                        entity_id=str(acc.id),
                        performed_by=acc.user_id,
                        details={"message": f"Account session validated. Status restored to {new_status}."},
                        created_at=datetime.utcnow()
                    )
                )
                logger.info(f"Account {acc.id} health restored.")

            elif status_result in ["expired", "flagged"]:
                # Session is dead or challenged
                new_status = "expired" if status_result == "expired" else "flagged"
                new_score = 50 if status_result == "expired" else 20
                
                await db.execute(
                    update(LinkedInAccount)
                    .where(LinkedInAccount.id == acc.id)
                    .values(status=new_status, health_score=new_score, updated_at=datetime.utcnow())
                )

                # Send Notification
                title = "LinkedIn Session Expired" if status_result == "expired" else "LinkedIn Account Flagged"
                msg = (
                    f"Your LinkedIn account '{acc.label}' session has expired. Please reconnect it."
                    if status_result == "expired" else
                    f"Your LinkedIn account '{acc.label}' requires checkpoint verification. Please log in again."
                )

                await db.execute(
                    insert(Notification).values(
                        user_id=acc.user_id,
                        notification_type="linkedin_health_alert",
                        title=title,
                        message=msg,
                        is_read=False,
                        link="/linkedin/accounts",
                        related_id=str(acc.id),
                        created_at=datetime.utcnow()
                    )
                )

                await db.execute(
                    insert(AuditLog).values(
                        action="health_alert",
                        entity_type="linkedin_accounts",
                        entity_id=str(acc.id),
                        performed_by=acc.user_id,
                        details={"status": new_status, "health_score": new_score, "reason": status_result},
                        created_at=datetime.utcnow()
                    )
                )
                logger.warning(f"Account {acc.id} session issue identified: {status_result}. Status updated to {new_status}.")

        await db.commit()
    logger.info("LinkedIn health check cycle finished.")
