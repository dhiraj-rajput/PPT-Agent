import asyncio
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import select, update, insert, func
from playwright.async_api import async_playwright

from utils.db_client import get_db_session, get_sync_db_session, _mysql_available
from utils.encryption import decrypt_data
from app.core.action_scheduler import get_account_caps
from pipeline.linkedin.outreach.session_loader import (
    open_authenticated_context,
    close_authenticated_context,
    SessionExpiredError,
    is_redirect_loop_error,
)
from models.sql_models import (
    LinkedInAccount,
    LinkedInMessageLog,
    LinkedInTarget,
    LinkedInCampaign,
    SystemStatus,
    AuditLog
)

logger = logging.getLogger("linkedin_worker")

async def send_connection_request_playwright(account_id: int, profile_url: str, note_text: str) -> bool:
    """
    Automates sending a connection request with a personalized note via Playwright.

    NOTE: this now opens the browser session via session_loader.open_authenticated_context(),
    which replays the account's FULL cookie jar under the SAME fingerprint (user-agent/
    viewport/locale/timezone) and proxy it logged in with. The previous version launched a
    brand-new context with a hardcoded UA/timezone, no proxy, and only the li_at cookie —
    LinkedIn's fraud-detection layer treats that mismatch as a hijacked session and force-
    redirects between the profile page and an auth/checkpoint wall, which is what was
    surfacing as "net::ERR_TOO_MANY_REDIRECTS".
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
        try:
            playwright_ctx, browser, context, page = await open_authenticated_context(account_id)
        except SessionExpiredError as exc:
            logger.error(f"Session expired for account {account_id}: {exc}")
            await _mark_account_expired(account_id, str(exc))
            return False

        # chrome-error://chromewebdata/ showing up AFTER goto() returns
        # without raising means the initial navigation succeeded, but some
        # LATER client-side navigation (LinkedIn's own app JS redirecting,
        # or a sub-resource fetch) failed at the network level and Playwright's
        # goto() call never saw it. Track every failed request and every
        # frame navigation so, if this happens again, we know exactly which
        # URL failed and why instead of just seeing a blank error page.
        nav_diagnostics: list[str] = []

        def _on_request_failed(request):
            try:
                nav_diagnostics.append(f"REQUEST FAILED: {request.method} {request.url} -> {request.failure}")
            except Exception:
                pass

        def _on_frame_navigated(frame):
            try:
                if frame == page.main_frame:
                    nav_diagnostics.append(f"NAVIGATED: {frame.url}")
            except Exception:
                pass

        page.on("requestfailed", _on_request_failed)
        page.on("framenavigated", _on_frame_navigated)

        goto_response = await page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
        if goto_response is not None:
            nav_diagnostics.append(f"INITIAL RESPONSE: {goto_response.status} {goto_response.url}")

        # LinkedIn's profile page keeps client-side re-rendering / soft-
        # navigating for a few seconds after domcontentloaded. A fixed
        # wait_for_timeout() was racy — if a navigation was still in flight
        # when we queried for buttons, Playwright's element handles from
        # query_selector_all() went stale mid-loop ("Execution context was
        # destroyed"). Wait for the network to actually settle instead, and
        # tolerate it timing out (some LinkedIn pages keep long-polling and
        # never go fully idle).
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await page.wait_for_timeout(1000)

        # If LinkedIn bounced us to an auth wall or checkpoint despite a
        # clean context load, treat this the same as a redirect-loop failure
        # rather than blindly trying (and failing) to find a Connect button.
        current_url = page.url
        if "/login" in current_url or "/checkpoint" in current_url or "authwall" in current_url:
            raise SessionExpiredError(f"Redirected to {current_url} — session no longer valid.")

        # LinkedIn's top-card action buttons (Connect/Follow/Message/Pending)
        # mount asynchronously even after the network goes idle — give them
        # a real chance to appear instead of immediately concluding "not
        # found" the moment networkidle fires.
        try:
            await page.wait_for_selector(
                "button:has-text('Connect'), button:has-text('Message'), "
                "button:has-text('Follow'), button:has-text('Pending'), "
                "button:has-text('More')",
                timeout=10000,
            )
        except Exception:
            logger.warning(f"No recognizable profile action button rendered at all for {profile_url} within 10s.")

        # 1. Look for the Connect action. Real DOM inspection of a LinkedIn
        # profile page confirms this is an <a> tag with
        # aria-label="Invite <Name> to connect" — NOT a <button> element:
        #
        #   <a aria-label="Invite Dr. Umesh Raut to connect"
        #      componentkey="ConnectButtonstate:invitation:...">
        #     <span>Connect</span>
        #   </a>
        #
        # get_by_role("button", name="Connect") can never match this — its
        # implicit ARIA role is "link", not "button". That's the actual
        # reason every earlier attempt found zero buttons even on pages
        # that rendered fine. Target the real markup: match on the
        # aria-label pattern LinkedIn uses consistently for this action.
        connect_btn = None

        connect_link_locator = page.locator("a[aria-label*='to connect' i]")
        try:
            if await connect_link_locator.count() > 0 and await connect_link_locator.first.is_visible(timeout=3000):
                connect_btn = connect_link_locator.first
        except Exception:
            connect_btn = None

        if not connect_btn:
            # Some LinkedIn surfaces (search results, "People you may know"
            # cards) render Connect as a real <button> instead of an <a> —
            # keep the role-based check as a fallback for those contexts.
            connect_button_locator = page.get_by_role("button", name="Connect", exact=False)
            try:
                if await connect_button_locator.count() > 0 and await connect_button_locator.first.is_visible(timeout=2000):
                    connect_btn = connect_button_locator.first
            except Exception:
                connect_btn = None

        if not connect_btn:
            # Broader link-role fallback in case the aria-label wording
            # varies ("Invite ... to connect" vs some other phrasing).
            connect_link_role_locator = page.get_by_role("link", name="Invite", exact=False)
            try:
                if await connect_link_role_locator.count() > 0:
                    connect_btn = connect_link_role_locator.first
            except Exception:
                pass

        if not connect_btn:
            # Try the "More" overflow menu — Connect is sometimes tucked in there.
            more_locator = page.get_by_role("button", name="More", exact=False)
            try:
                if await more_locator.count() > 0:
                    await more_locator.first.click(timeout=5000)
                    await page.wait_for_timeout(800)
                    dropdown = page.locator("div.artdeco-dropdown__content")
                    dropdown_connect_link = dropdown.locator("a[aria-label*='to connect' i]")
                    dropdown_connect_btn = dropdown.get_by_role("button", name="Connect", exact=False)
                    if await dropdown_connect_link.count() > 0:
                        connect_btn = dropdown_connect_link.first
                    elif await dropdown_connect_btn.count() > 0:
                        connect_btn = dropdown_connect_btn.first
            except Exception as exc:
                logger.warning(f"Could not check 'More' menu for {profile_url}: {exc}")

        if not connect_btn:
            # Diagnostic: log every visible button's accessible name so it's
            # obvious from the logs whether this is "already Pending/1st
            # degree connection" (nothing to do, not a bug) vs. "LinkedIn
            # changed its markup and our selectors need updating" vs. "the
            # page just never finished rendering."
            visible_labels = []
            try:
                all_buttons = page.get_by_role("button")
                n = min(await all_buttons.count(), 20)
                for i in range(n):
                    try:
                        label = (await all_buttons.nth(i).inner_text(timeout=500)).strip()
                        if label:
                            visible_labels.append(f"button:{label}")
                    except Exception:
                        continue

                # Connect is often an <a role=link> per real DOM inspection —
                # capture visible link accessible-names too, since a
                # 'button' name is only half the picture now.
                all_links = page.get_by_role("link")
                n_links = min(await all_links.count(), 30)
                for i in range(n_links):
                    try:
                        aria = await all_links.nth(i).get_attribute("aria-label", timeout=500)
                        if aria and ("connect" in aria.lower() or "invite" in aria.lower()):
                            visible_labels.append(f"link:{aria}")
                    except Exception:
                        continue
            except Exception:
                pass

            lowered = [l.lower() for l in visible_labels]
            if any("pending" in l for l in lowered):
                logger.info(f"Target {profile_url} already has a pending connection request — nothing to send.")
            elif any(l in ("message", "1st") for l in lowered) and not any("connect" in l for l in lowered):
                logger.info(f"Target {profile_url} appears to already be a 1st-degree connection — nothing to send.")
            else:
                # Zero (or near-zero) buttons on a profile a real logged-in
                # browser renders fine almost always means LinkedIn's bot
                # detection served a stripped/limited page to this headless
                # session rather than the real markup being different. Dump
                # enough evidence to tell the two apart without guessing.
                debug_dir = "/tmp/linkedin_debug"
                try:
                    import os
                    os.makedirs(debug_dir, exist_ok=True)
                    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
                    screenshot_path = f"{debug_dir}/{account_id}_{stamp}.png"
                    html_path = f"{debug_dir}/{account_id}_{stamp}.html"
                    await page.screenshot(path=screenshot_path, full_page=True)
                    html_content = await page.content()
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    page_title = await page.title()
                    nav_trail = " | ".join(nav_diagnostics[-10:]) if nav_diagnostics else "(no failed requests or navigations captured)"
                    logger.warning(
                        f"Could not find Connect button on page for {profile_url}. "
                        f"Visible buttons were: {visible_labels or '[]'}. "
                        f"Page title was '{page_title}' at URL {page.url}. "
                        f"Navigation trail: {nav_trail}. "
                        f"Saved a screenshot+HTML dump to {screenshot_path} / {html_path} for inspection. "
                        f"Zero buttons on a profile a normal logged-in browser renders fine almost always means "
                        f"LinkedIn served a stripped/bot-detection page to this automated session rather than "
                        f"the real profile markup — check the screenshot before assuming selectors need updating."
                    )
                except Exception as dump_exc:
                    logger.warning(
                        f"Could not find Connect button on page for {profile_url}. "
                        f"Visible buttons were: {visible_labels or '[]'}. Also failed to save a debug dump: {dump_exc}"
                    )
            return False

        await connect_btn.click(timeout=5000)
        await page.wait_for_timeout(1500)

        # 2. The "Add a note to your invitation?" modal (confirmed from a
        # live screenshot: header "Add a note to your invitation?" with
        # "Add a note" / "Send without a note" buttons). Scope everything
        # to the dialog itself so we're never at risk of matching an
        # unrelated same-labeled button elsewhere on the page.
        dialog = page.locator("div[role='dialog']")
        try:
            await dialog.first.wait_for(state="visible", timeout=5000)
        except Exception:
            dialog = page  # fall back to page-wide search if no dialog role found

        add_note_locator = dialog.get_by_role("button", name="Add a note", exact=False)
        has_note_option = await add_note_locator.count() > 0

        if has_note_option and note_text:
            await add_note_locator.first.click(timeout=5000)
            await page.wait_for_timeout(1000)

            textarea = page.locator("textarea[name='message'], textarea#custom-message")
            if await textarea.count() > 0:
                await textarea.first.fill(note_text)
                await page.wait_for_timeout(1000)

            # LinkedIn's exact label on the final send button after adding a
            # note varies by surface ("Send", "Send now", "Send invitation")
            # — try them in order rather than assuming one.
            for send_name in ("Send invitation", "Send now", "Send"):
                send_locator = dialog.get_by_role("button", name=send_name, exact=False)
                if await send_locator.count() > 0:
                    await send_locator.first.click(timeout=5000)
                    await page.wait_for_timeout(2000)
                    logger.info(f"Connection request sent with note to {profile_url}")
                    return True
        else:
            send_locator = dialog.get_by_role("button", name="Send without a note", exact=False)
            if await send_locator.count() == 0:
                send_locator = dialog.get_by_role("button", name="Send now", exact=False)
            if await send_locator.count() > 0:
                await send_locator.first.click(timeout=5000)
                await page.wait_for_timeout(2000)
                logger.info(f"Connection request sent without note to {profile_url}")
                return True

        return False

    except SessionExpiredError as e:
        logger.error(f"Session expired sending to {profile_url} from account {account_id}: {e}")
        await _mark_account_expired(account_id, str(e))
        return False
    except Exception as e:
        if is_redirect_loop_error(e):
            logger.error(
                f"Redirect loop from account {account_id} navigating to {profile_url} — "
                f"session is no longer valid, marking account expired: {e}"
            )
            await _mark_account_expired(account_id, "LinkedIn kept redirecting to a login/checkpoint page — reconnect this account.")
        elif "Execution context was destroyed" in str(e) or "context was destroyed" in str(e):
            # Transient: the page was still soft-navigating/re-rendering when
            # we tried to interact with it. Not a dead session — just retry
            # this target on the worker's next pass rather than expiring the
            # account.
            logger.warning(
                f"Page was still navigating when interacting with {profile_url} (account {account_id}) — "
                f"will retry on next queue pass: {e}"
            )
        else:
            logger.error(f"Failed connection request automation to {profile_url}: {e}")
        return False
    finally:
        await close_authenticated_context(playwright_ctx, browser, context)


async def _mark_account_expired(account_id: int, reason: str) -> None:
    """Flips the account to 'expired' and records why, so:
      (a) the scheduler/action_scheduler stops handing it more work, and
      (b) the Accounts UI shows a clear 'reconnect this account' prompt
    instead of the worker quietly retrying a dead session against every
    queued target until they're all burned through as 'failed'.
    """
    if not _mysql_available:
        return
    async for db in get_db_session():
        await db.execute(
            update(LinkedInAccount)
            .where(LinkedInAccount.id == account_id)
            .values(status="expired", last_error=reason, updated_at=datetime.utcnow())
        )
        await db.commit()


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
        logger.error(f"LinkedInAccount {account_id} not found. Marking message {msg_log.id} as failed (no sender account assigned to campaign).")
        msg_log.status = "failed"
        msg_log.updated_at = datetime.utcnow()
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

    # 2. Quick sanity check that a session is even stored. The actual
    # decrypt + full-cookie-jar replay now happens inside
    # session_loader.open_authenticated_context(), called from
    # send_connection_request_playwright() below — this keeps cookie
    # handling in one place instead of duplicated here and there.
    if not acc.session_cookie_encrypted:
        logger.error(f"No session stored for account {account_id}. Marking message {msg_log.id} as failed.")
        msg_log.status = "failed"
        msg_log.updated_at = datetime.utcnow()
        return False

    # 3. Retrieve target profile URL
    stmt_target = select(LinkedInTarget).where(LinkedInTarget.id == msg_log.target_id)
    res_target = await db.execute(stmt_target)
    target = res_target.scalar_one_or_none()
    
    if not target:
        logger.error(f"LinkedInTarget {msg_log.target_id} not found. Marking message {msg_log.id} as failed.")
        msg_log.status = "failed"
        msg_log.updated_at = datetime.utcnow()
        return False

    # Reuses existing Person table for profile URL
    from models.sql_models import Person
    stmt_person = select(Person).where(Person.id == target.person_id)
    res_person = await db.execute(stmt_person)
    person = res_person.scalar_one_or_none()

    target_url = person.linkedin_url if person else ""
    if not target_url:
        logger.error(f"No LinkedIn URL found for person ID={target.person_id}. Marking message {msg_log.id} as failed.")
        msg_log.status = "failed"
        msg_log.updated_at = datetime.utcnow()
        return False

    # 4. Automate send
    send_success = await send_connection_request_playwright(
        account_id=acc.id,
        profile_url=target_url,
        note_text=msg_log.content or ""
    )

    if send_success:
        # Update message log status
        msg_log.status = "sent"
        msg_log.sent_at = datetime.utcnow()
        msg_log.updated_at = datetime.utcnow()

        # Update the target's outreach status so the UI reflects the real state
        target.connection_status = "pending"
        target.last_action_at = datetime.utcnow()
        target.updated_at = datetime.utcnow()

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
                    # 1. Scrape pending targets for running campaigns
                    #
                    # IMPORTANT: this whole block used to be able to take down
                    # EVERY campaign's sends, system-wide, on EVERY loop pass.
                    # If any single campaign's linkedin_account_id pointed at
                    # an account that no longer existed (e.g. disconnected/
                    # deleted after the campaign was created), the INSERT
                    # below violated the account_id_used foreign key, and
                    # since this block shares one big try/except with the
                    # actual send step further down, that exception aborted
                    # the ENTIRE loop pass before step 2 (sending) ever ran —
                    # for every account, not just the broken campaign. This
                    # is why sends could silently stop working system-wide
                    # while looking fine in the logs (the traceback was
                    # there, just buried under routine polling noise).
                    #
                    # Fix: validate the account up front and skip campaigns
                    # with no valid connected account, and isolate each
                    # campaign's work + commit in its own try/except so one
                    # broken campaign can never block anyone else's sends.
                    stmt_camps = select(LinkedInCampaign).where(LinkedInCampaign.status == "running")
                    res_camps = await db.execute(stmt_camps)
                    running_campaigns = res_camps.scalars().all()

                    for camp in running_campaigns:
                        try:
                            if camp.linkedin_account_id:
                                acc_check = (
                                    await db.execute(
                                        select(LinkedInAccount).where(LinkedInAccount.id == camp.linkedin_account_id)
                                    )
                                ).scalar_one_or_none()
                            else:
                                acc_check = None

                            if not acc_check:
                                logger.warning(
                                    f"Campaign {camp.id} ('{camp.name if hasattr(camp, 'name') else camp.id}') has no "
                                    f"valid connected LinkedIn account (linkedin_account_id={camp.linkedin_account_id} "
                                    f"does not exist — likely disconnected/deleted after the campaign was created). "
                                    f"Skipping note generation for this campaign until it's reassigned to a live account."
                                )
                                continue

                            stmt_tg = select(LinkedInTarget).where(
                                LinkedInTarget.campaign_id == camp.id,
                                LinkedInTarget.scrape_status == "pending"
                            )
                            res_tg = await db.execute(stmt_tg)
                            pending_targets = res_tg.scalars().all()

                            for target in pending_targets:
                                try:
                                    target.scrape_status = "scraped"
                                    target.updated_at = datetime.utcnow()

                                    from models.sql_models import Person
                                    stmt_p = select(Person).where(Person.id == target.person_id)
                                    p_res = await db.execute(stmt_p)
                                    person = p_res.scalar_one_or_none()

                                    if person:
                                        profile_dict = {
                                            "full_name": person.full_name,
                                            "title": person.title,
                                            "organization_name": person.organization_name,
                                            "linkedin_url": person.linkedin_url
                                        }
                                        from pipeline.ai.outreach_prompts import generate_connection_note
                                        our_company_desc = "Orbitavanya Tech - AI-driven B2B lead generation and outreach automation platform."
                                        note_content = generate_connection_note(
                                            target_profile=profile_dict,
                                            our_company=our_company_desc,
                                            custom_prompt=camp.connection_note_prompt or ""
                                        )

                                        new_log = LinkedInMessageLog(
                                            campaign_id=camp.id,
                                            target_id=target.id,
                                            account_id_used=camp.linkedin_account_id,
                                            direction="out",
                                            content=note_content,
                                            generated_by=camp.message_generation_mode if camp.message_generation_mode in ("llm", "manual", "template") else "llm",
                                            status="needs_review" if camp.require_approval else "approved",
                                            created_at=datetime.utcnow(),
                                            updated_at=datetime.utcnow()
                                        )
                                        db.add(new_log)
                                except Exception as ex:
                                    logger.error(f"Error auto-scraping/generating note for target {target.id}: {ex}")

                            # Commit per-campaign so one campaign's bad data
                            # can't roll back another campaign's good work,
                            # and so a failure here is caught right where it
                            # happened instead of bubbling out of the whole loop.
                            await db.commit()
                        except Exception as camp_exc:
                            logger.error(f"Failed to process campaign {camp.id} in note-generation pass: {camp_exc}")
                            await db.rollback()
                            continue


                # 2. Process approved outreach messages
                async for db in get_db_session():
                    stmt = select(LinkedInMessageLog).where(
                        LinkedInMessageLog.status == "approved",
                        LinkedInMessageLog.direction == "out",
                        (LinkedInMessageLog.scheduled_send_at == None) | (LinkedInMessageLog.scheduled_send_at <= datetime.utcnow())
                    ).limit(5)
                    res = await db.execute(stmt)
                    approved_messages = res.scalars().all()

                    for msg in approved_messages:
                        await process_approved_message(db, msg)
                    
                    await db.commit()

        except Exception as e:
            logger.error(f"LinkedIn worker loop encountered an error: {e}", exc_info=True)

        await asyncio.sleep(15)  # Poll every 15 seconds