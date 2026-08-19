import asyncio
import json
import logging
from datetime import datetime
from sqlalchemy import select, update, insert
from playwright.async_api import async_playwright

from utils.db_client import get_db_session
from utils.encryption import decrypt_data
from pipeline.linkedin.outreach.session_loader import (
    open_authenticated_context,
    close_authenticated_context,
    SessionExpiredError,
)
from models.sql_models import LinkedInAccount, Notification, AuditLog

logger = logging.getLogger(__name__)

async def check_account_health_with_playwright(account_id: int, decrypted_cookies: dict = None) -> str:
    """
    Checks the cookie session health of a single LinkedIn account.
    Returns: 'active', 'expired', 'flagged', or 'error'

    NOTE: this used to open its own ad-hoc browser context with a hardcoded
    UA/timezone and no proxy, replaying only the li_at cookie — the exact
    same identity mismatch that caused send_connection_request_playwright()'s
    ERR_TOO_MANY_REDIRECTS bug (see linkedin_worker.py). That meant a
    perfectly healthy session could get flagged 'expired' here just because
    the health-check's own browser fingerprint didn't match what the account
    actually logged in with. Now uses session_loader.open_authenticated_context()
    — the same identity-consistent path the real send flow uses — so a
    session is only ever reported unhealthy because LinkedIn actually says so,
    not because of how we're checking it.

    The `decrypted_cookies` parameter is kept (unused) for backward
    compatibility with existing callers; session_loader re-loads and decrypts
    the account's stored session itself.
    """
    playwright_ctx = None
    browser = None
    context = None
    try:
        try:
            playwright_ctx, browser, context, page = await open_authenticated_context(account_id)
        except SessionExpiredError:
            return "expired"

        # Navigate to profile shortcut endpoint instead of /feed/ which triggers redirect loops
        await page.goto("https://www.linkedin.com/in/me/", wait_until="domcontentloaded", timeout=20000)
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass

        current_url = page.url
        logger.info(f"Health check navigation complete for account {account_id}. Current URL: {current_url}")

        if "/login" in current_url or "/signup" in current_url:
            return "expired"
        elif "/checkpoint" in current_url or "checkpoint" in current_url or "/restricted" in current_url:
            return "flagged"
        else:
            return "active"

    except Exception as e:
        err_text = str(e)
        # LinkedIn bounces an invalid/expired li_at cookie between the login and
        # feed URLs, which Playwright surfaces as a redirect-loop navigation error
        # rather than a normal /login redirect. Treat that the same as an expired
        # session so the account gets flagged for reconnection instead of failing
        # silently on every poll.
        if "ERR_TOO_MANY_REDIRECTS" in err_text or "ERR_CONNECTION" in err_text or "net::ERR" in err_text:
            logger.warning(f"Health check for account {account_id} hit a navigation/redirect error ({err_text}); treating session as expired.")
            return "expired"
        logger.error(f"Health check browser error for account {account_id}: {e}")
        return "error"
    finally:
        await close_authenticated_context(playwright_ctx, browser, context)

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
