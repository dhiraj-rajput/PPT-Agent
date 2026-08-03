import asyncio
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import select, update, insert, func
from playwright.async_api import async_playwright

from utils.db_client import get_db_session, get_sync_db_session, _mysql_available
from utils.encryption import decrypt_data
from app.core.action_scheduler import get_account_caps
from models.sql_models import (
    LinkedInAccount,
    LinkedInMessageLog,
    LinkedInTarget,
    LinkedInCampaign,
    SystemStatus,
    AuditLog
)

logger = logging.getLogger("linkedin_worker")

async def send_connection_request_playwright(account_id: int, cookies: dict, profile_url: str, note_text: str) -> bool:
    """
    Automates sending a connection request with a personalized note via Playwright.
    """
    logger.info(f"Attempting to send connection request to {profile_url} from account {account_id}")
    
    # Check for mock url / development testing
    if "mock" in profile_url or "example.com" in profile_url:
        logger.info(f"[Mock Send] Successfully simulated connection request to {profile_url} with note: {note_text}")
        return True

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

        await context.add_cookies([
            {
                "name": "li_at",
                "value": cookies["li_at"],
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            }
        ])

        page = await context.new_page()
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # 1. Look for Connect button
        # LinkedIn profile page structure Connect buttons can be in different places:
        # e.g., primary button with text "Connect" or inside "More" dropdown
        connect_btn = None
        
        # Try to find visible Connect button in the top card
        buttons = await page.query_selector_all("button")
        for btn in buttons:
            text = await btn.inner_text()
            if "Connect" in text:
                connect_btn = btn
                break

        if not connect_btn:
            # Try to find "More" button to open dropdown
            more_btn = None
            for btn in buttons:
                text = await btn.inner_text()
                if "More" in text:
                    more_btn = btn
                    break
            
            if more_btn:
                await more_btn.click()
                await page.wait_for_timeout(1000)
                dropdown_buttons = await page.query_selector_all("div.artdeco-dropdown__content button")
                for btn in dropdown_buttons:
                    text = await btn.inner_text()
                    if "Connect" in text:
                        connect_btn = btn
                        break

        if not connect_btn:
            logger.warning(f"Could not find Connect button on page for {profile_url}. Might already be connected or pending.")
            return False

        await connect_btn.click()
        await page.wait_for_timeout(1500)

        # 2. Check for connection dialog note request
        # Look for "Add a note" button in the modal
        add_note_btn = await page.query_selector("button[aria-label='Add a note']")
        if add_note_btn and note_text:
            await add_note_btn.click()
            await page.wait_for_timeout(1000)
            
            # Fill the note textarea
            textarea = await page.query_selector("textarea[name='message']")
            if textarea:
                await textarea.fill(note_text)
                await page.wait_for_timeout(1000)
            
            # Click "Send"
            send_btn = await page.query_selector("button[aria-label='Send now']")
            if send_btn:
                await send_btn.click()
                await page.wait_for_timeout(2000)
                logger.info(f"Connection request sent with note to {profile_url}")
                return True
        else:
            # Try to click Send directly if no note or note button not found
            send_btn = await page.query_selector("button[aria-label='Send without a note']") or await page.query_selector("button[aria-label='Send now']")
            if send_btn:
                await send_btn.click()
                await page.wait_for_timeout(2000)
                logger.info(f"Connection request sent without note to {profile_url}")
                return True

        return False

    except Exception as e:
        logger.error(f"Failed connection request automation to {profile_url}: {e}")
        return False
    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright_ctx:
            await playwright_ctx.stop()

async def process_approved_message(db, msg_log: LinkedInMessageLog) -> bool:
    """
    Processes a single message: validates caps, decrypts cookies, calls playwright sending.
    """
    account_id = msg_log.account_id_used
    
    # 1. Fetch account and verify caps
    stmt_acc = select(LinkedInAccount).where(LinkedInAccount.id == account_id)
    res_acc = await db.execute(stmt_acc)
    acc = res_acc.scalar_one_or_none()

    if not acc:
        logger.error(f"LinkedInAccount {account_id} not found.")
        return False

    if acc.status not in ["active", "warming_up"]:
        logger.info(f"Skipping send for account {acc.id} because status is {acc.status}")
        return False

    # Check daily sending counts to enforce Action Scheduler caps
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt_sent_today = select(func.count(LinkedInMessageLog.id)).where(
        LinkedInMessageLog.account_id_used == account_id,
        LinkedInMessageLog.status == "sent",
        LinkedInMessageLog.sent_at >= today_start
    )
    res_sent_today = await db.execute(stmt_sent_today)
    sent_today = res_sent_today.scalar() or 0

    conn_cap, msg_cap = get_account_caps(acc.warmup_stage)

    # Determine limit based on message type
    # For now, let's treat connection notes or general outreach under limits
    if sent_today >= msg_cap:
        logger.warning(f"Account {acc.id} has reached its daily cap limit ({sent_today}/{msg_cap}). Postponing send.")
        return False

    # 2. Decrypt cookies
    try:
        cookies_data = json.loads(decrypt_data(acc.session_cookie_encrypted))
    except Exception as e:
        logger.error(f"Failed to decrypt cookies for account {account_id}: {e}")
        return False

    # 3. Retrieve target profile URL
    stmt_target = select(LinkedInTarget).where(LinkedInTarget.id == msg_log.target_id)
    res_target = await db.execute(stmt_target)
    target = res_target.scalar_one_or_none()
    
    if not target:
        logger.error(f"LinkedInTarget {msg_log.target_id} not found.")
        return False

    # Reuses existing Person table for profile URL
    from models.sql_models import Person
    stmt_person = select(Person).where(Person.id == target.person_id)
    res_person = await db.execute(stmt_person)
    person = res_person.scalar_one_or_none()

    target_url = person.linkedin_url if person else ""
    if not target_url:
        logger.error(f"No LinkedIn URL found for person ID={target.person_id}")
        return False

    # 4. Automate send
    send_success = await send_connection_request_playwright(
        account_id=acc.id,
        cookies=cookies_data,
        profile_url=target_url,
        note_text=msg_log.content or ""
    )

    if send_success:
        # Update message log status
        msg_log.status = "sent"
        msg_log.sent_at = datetime.utcnow()
        msg_log.updated_at = datetime.utcnow()

        # Update account action timestamp
        acc.last_action_at = datetime.utcnow()
        
        # Log audit trail
        await db.execute(
            insert(AuditLog).values(
                action="send_message",
                entity_type="linkedin_message_logs",
                entity_id=str(msg_log.id),
                performed_by=acc.user_id,
                details={"account_id": acc.id, "target_profile": target_url},
                created_at=datetime.utcnow()
            )
        )
        logger.info(f"Successfully processed and updated LinkedInMessageLog ID={msg_log.id}")
        return True
    else:
        # Set message status to failed
        msg_log.status = "failed"
        msg_log.updated_at = datetime.utcnow()
        logger.warning(f"Failed sending LinkedInMessageLog ID={msg_log.id}")
        return False

async def start_linkedin_worker_loop():
    """
    Background polling loop for scheduled/approved LinkedIn outreach messages.
    """
    logger.info("LinkedIn worker background polling loop started.")
    
    while True:
        try:
            if _mysql_available:
                # Update heartbeat status
                try:
                    async for db in get_db_session():
                        stmt = select(SystemStatus).where(SystemStatus.key_name == "linkedin_worker")
                        row = (await db.execute(stmt)).scalar_one_or_none()
                        if row:
                            await db.execute(
                                update(SystemStatus)
                                .where(SystemStatus.key_name == "linkedin_worker")
                                .values(last_active=datetime.utcnow(), status="running")
                            )
                        else:
                            await db.execute(
                                insert(SystemStatus).values(
                                    key_name="linkedin_worker",
                                    status="running",
                                    last_active=datetime.utcnow(),
                                    extra_data={}
                                )
                            )
                        await db.commit()
                except Exception as e:
                    logger.error(f"Failed to update LinkedIn worker heartbeat: {e}")

                # Poll for approved outreach messages to process
                async for db in get_db_session():
                    stmt = select(LinkedInMessageLog).where(
                        LinkedInMessageLog.status == "approved",
                        LinkedInMessageLog.direction == "out"
                    ).limit(5)
                    res = await db.execute(stmt)
                    approved_messages = res.scalars().all()

                    for msg in approved_messages:
                        # Process message
                        await process_approved_message(db, msg)
                    
                    await db.commit()

        except Exception as e:
            logger.error(f"LinkedIn worker loop encountered an error: {e}", exc_info=True)

        await asyncio.sleep(15)  # Poll every 15 seconds
