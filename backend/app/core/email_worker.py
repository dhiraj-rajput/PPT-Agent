import asyncio
import logging
import re
import zoneinfo
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from config.settings import settings
from utils.db_client import get_db_session, get_sync_db_session, _mysql_available
from models.sql_models import (
    Campaign as SQL_Campaign,
    Lead as SQL_Lead,
    Suppression as SQL_Suppression,
    TrackingEvent as SQL_TrackingEvent,
    AuditLog as SQL_AuditLog,
    Edition as SQL_Edition,
    SystemStatus as SQL_SystemStatus,
)
from sqlalchemy import select, insert, update, delete, func

from app.core.tracking_helpers import (
    rewrite_links_for_tracking,
    new_tracking_id,
    unsubscribe_url,
    open_pixel_tag,
)

logger = logging.getLogger("email_worker")

_worker_tasks: set = set()

def _spawn_worker_task(coro_or_future) -> None:
    """Create an asyncio task and keep a strong reference until complete."""
    task = asyncio.ensure_future(coro_or_future)
    _worker_tasks.add(task)
    task.add_done_callback(_worker_tasks.discard)


def is_within_working_hours(tz_str: str) -> bool:
    """Check if local time in tz_str is Monday-Friday 9:00 AM to 5:00 PM."""
    try:
        tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
    
    local_time = datetime.now(tz)
    weekday = local_time.weekday()
    if weekday > 4:  # 5 is Saturday, 6 is Sunday
        return False
        
    hour = local_time.hour
    if 9 <= hour < 17:
        return True
    return False


def get_next_working_hour(tz_str: str) -> datetime:
    """Calculate the next working hour window start in UTC."""
    try:
        tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
        
    local_now = datetime.now(tz)
    candidate = local_now + timedelta(hours=1)
    candidate = candidate.replace(minute=0, second=0, microsecond=0)
    
    for _ in range(24 * 7):  # check hourly up to 1 week
        if candidate.weekday() < 5 and 9 <= candidate.hour < 17:
            return candidate.astimezone(timezone.utc)
        candidate += timedelta(hours=1)
        
    return datetime.now(timezone.utc) + timedelta(minutes=15)


SCORE_RULES = {
    "emailSent": 5,
    "emailOpened": 10,
    "linkClicked": 20,
    "websiteVisited": 20,
    "pricingPageViewed": 25,
    "caseStudiesViewed": 15,
    "stayedOver5Min": 20,
    "formSubmitted": 30,
    "replied": 50,
    "meetingBooked": 100,
}


def classify_score(score: int) -> str:
    """Classify lead score into cold/warm/hot/sql grades."""
    if score > 100:
        return "sql"
    if score >= 61:
        return "hot"
    if score >= 31:
        return "warm"
    return "cold"


def _sql_lead_to_dict(u) -> dict:
    if not u:
        return {}
    return {
        "_id": u.id,
        "id": u.id,
        "campaignId": u.campaign_id,
        "createdBy": u.created_by,
        "email": u.email,
        "contactName": u.contact_name or "",
        "companyName": u.company_name or "",
        "companyKey": u.company_key or "",
        "companyUei": u.company_uei or "",
        "title": u.title or "",
        "website": u.website or "",
        "linkedin": u.linkedin or "",
        "status": u.status or "pending",
        "score": u.score or 0,
        "grade": u.grade or "cold",
        "sendAfter": u.send_after,
        "sendAttempts": u.send_attempts or 0,
        "resendCount": u.resend_count or 0,
        "lastSendError": u.last_send_error or "",
        "replySubject": u.reply_subject or "",
        "replyMessage": u.reply_message or "",
        "replyPreview": u.reply_preview or "",
        "sentAt": u.sent_at,
        "openedAt": u.opened_at,
        "clickedAt": u.clicked_at,
        "repliedAt": u.replied_at,
        "bouncedAt": u.bounced_at,
        "unsubscribedAt": u.unsubscribed_at,
        "createdAt": u.created_at,
        "updatedAt": u.updated_at,
    }


def _sql_campaign_to_dict(c) -> dict:
    if not c:
        return {}
    return {
        "_id": c.id,
        "id": c.id,
        "userId": c.user_id,
        "name": c.name or "",
        "description": c.description or "",
        "subject": c.subject or "",
        "body": c.body or "",
        "senderEmail": c.sender_email or "",
        "senderName": c.sender_name or "",
        "status": c.status or "draft",
        "stats": c.stats or {},
        "workingHoursOnly": bool(c.working_hours_only),
        "timezone": c.timezone or "America/Chicago",
        "dailyLimit": c.daily_limit or 200,
        "scheduleStart": c.schedule_start,
        "attachmentPath": c.attachment_path or "",
        "attachmentFilename": c.attachment_filename or "",
        "createdAt": c.created_at,
        "updatedAt": c.updated_at,
    }


async def add_score_async(lead_id: int, delta: int):
    """Async add delta to lead score and update grade."""
    try:
        async for db in get_db_session():
            stmt = select(SQL_Lead).where(SQL_Lead.id == lead_id)
            res = await db.execute(stmt)
            lead = res.scalar_one_or_none()
            if not lead:
                return
            new_score = int(str(getattr(lead, "score", 0) or 0)) + delta
            new_grade = classify_score(new_score)
            await db.execute(
                update(SQL_Lead)
                .where(SQL_Lead.id == lead_id)
                .values(score=new_score, grade=new_grade, updated_at=datetime.utcnow())
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to add score to lead {lead_id}: {e}")


def add_score(lead_id: int, delta: int):
    """Sync fallback to add delta to lead score and update grade."""
    try:
        with get_sync_db_session() as db:
            stmt = select(SQL_Lead).where(SQL_Lead.id == lead_id)
            lead = db.execute(stmt).scalar_one_or_none()
            if not lead:
                return
            new_score = int(str(getattr(lead, "score", 0) or 0)) + delta
            new_grade = classify_score(new_score)


            db.execute(
                update(SQL_Lead)
                .where(SQL_Lead.id == lead_id)
                .values(score=new_score, grade=new_grade, updated_at=datetime.utcnow())
            )
            db.commit()
    except Exception as e:
        logger.error(f"Failed to add score to lead {lead_id}: {e}")


async def score_email_sent_async(lead_id: int):
    await add_score_async(lead_id, SCORE_RULES["emailSent"])


async def score_replied_async(lead_id: int):
    await add_score_async(lead_id, SCORE_RULES["replied"])


def score_email_sent(lead_id: int):
    add_score(lead_id, SCORE_RULES["emailSent"])


def score_email_opened(lead_id: int):
    add_score(lead_id, SCORE_RULES["emailOpened"])


def score_link_clicked(lead_id: int):
    add_score(lead_id, SCORE_RULES["linkClicked"])


def score_replied(lead_id: int):
    add_score(lead_id, SCORE_RULES["replied"])


def score_meeting_booked(lead_id: int):
    add_score(lead_id, SCORE_RULES["meetingBooked"])


async def send_campaign_email_to_lead(campaign: dict, lead: dict) -> dict:
    """Sends a single campaign email to a lead and registers tracking IDs."""
    body_tmpl = campaign.get("body") or "<p>Hello {{firstName}},</p>"
    subject_tmpl = campaign.get("subject") or ""

    def fill_placeholders(template: str, lead_data: dict) -> str:
        first_name = lead_data.get("contactName", "").split(" ")[0] if lead_data.get("contactName") else "there"
        res = template
        res = re.sub(r"{{\s*firstName\s*}}", first_name, res, flags=re.IGNORECASE)
        res = re.sub(r"{{\s*contactName\s*}}", lead_data.get("contactName") or "", res, flags=re.IGNORECASE)
        res = re.sub(r"{{\s*companyName\s*}}", lead_data.get("companyName") or "", res, flags=re.IGNORECASE)
        res = re.sub(r"{{\s*title\s*}}", lead_data.get("title") or "", res, flags=re.IGNORECASE)
        res = re.sub(r"{{\s*campaignId\s*}}", str(campaign.get("id") or ""), res, flags=re.IGNORECASE)
        res = re.sub(r"{{\s*leadId\s*}}", str(lead_data.get("id") or ""), res, flags=re.IGNORECASE)
        res = re.sub(r"{{\s*clientUrl\s*}}", settings.CLIENT_URL.rstrip("/"), res, flags=re.IGNORECASE)
        return res

    html_body = fill_placeholders(body_tmpl, lead)
    subject = fill_placeholders(subject_tmpl, lead)

    # Rewrite links for tracking
    click_tracked_html, links = rewrite_links_for_tracking(html_body)

    open_tracking_id = new_tracking_id()
    unsub_link = unsubscribe_url(str(lead["id"]), str(campaign["id"]))

    final_html = f"""
    {click_tracked_html}
    {open_pixel_tag(open_tracking_id)}
    """

    # Build MIME message
    import aiosmtplib
    import os
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    attach_path = campaign.get("attachmentPath")
    attach_name = campaign.get("attachmentFilename") or "attachment.pdf"

    if attach_path and os.path.exists(attach_path):
        msg = MIMEMultipart("mixed")
        
        # Attach HTML as alternative
        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(final_html, "html"))
        msg.attach(alt_part)
        
        # Attach PDF using non-blocking read
        try:
            def read_file(p):
                with open(p, "rb") as f:
                    return f.read()
            pdf_bytes = await asyncio.to_thread(read_file, attach_path)
            part = MIMEApplication(pdf_bytes, Name=attach_name)
            part['Content-Disposition'] = f'attachment; filename="{attach_name}"'
            msg.attach(part)
        except Exception as e:
            logger.error(f"Failed to read/attach campaign PDF: {e}")
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(final_html, "html"))

    msg["Subject"] = subject
    msg["List-Unsubscribe"] = f"<{unsub_link}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    sender_name = campaign.get("senderName")
    smtp_from = settings.SMTP_FROM or settings.SMTP_USER
    sender_email = campaign.get("senderEmail") or smtp_from

    # Prevent SMTP Sender Misalignment errors when using cPanel SMTP
    if settings.SMTP_USER and "@" in settings.SMTP_USER and smtp_from:
        smtp_domain = settings.SMTP_USER.split("@")[1].lower()
        if "@" in sender_email:
            sender_domain = sender_email.split("@")[1].lower()
            if sender_domain != smtp_domain:
                logger.info(f"[Email Worker] Aligning sender email from {sender_email} to {smtp_from} to match SMTP server {settings.SMTP_HOST}")
                sender_email = smtp_from

    if sender_name:
        msg["From"] = f'"{sender_name}" <{sender_email}>'
    else:
        msg["From"] = sender_email

    msg["To"] = lead["email"]

    if not (settings.SMTP_USER and settings.SMTP_PASS):
        raise RuntimeError(
            "SMTP is not configured (SMTP_USER / SMTP_PASS are empty)."
        )

    await aiosmtplib.send(
        msg,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASS,
        use_tls=(settings.SMTP_PORT == 465),
        start_tls=(settings.SMTP_PORT == 587),
    )

    # Pre-register tracking events in MySQL
    if _mysql_available:
        try:
            async for db in get_db_session():
                events_to_insert = [{
                    "tracking_id": open_tracking_id,
                    "lead_id": lead["id"],
                    "campaign_id": campaign["id"],
                    "event_type": "open",
                    "destination_url": "",
                    "timestamp": None,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }]
                
                if links:
                    events_to_insert.extend([{
                        "tracking_id": link["trackingId"],
                        "lead_id": lead["id"],
                        "campaign_id": campaign["id"],
                        "event_type": "click",
                        "destination_url": link["destinationUrl"],
                        "timestamp": None,
                        "created_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc)
                    } for link in links])
                
                await db.execute(insert(SQL_TrackingEvent).values(events_to_insert))
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to pre-register tracking events in MySQL: {e}")

    return {"openTrackingId": open_tracking_id, "links": links}


async def process_lead_send(campaign: dict, lead: dict):
    """Processes suppression check, updates delivery status, sends email, and scores lead."""
    suppressed = None
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Suppression).where(SQL_Suppression.email == lead["email"])
                suppressed = (await db.execute(stmt)).scalar_one_or_none()
        except Exception as e:
            logger.error(f"MySQL suppression check failed: {e}")

    if suppressed:
        if _mysql_available:
            try:
                async for db in get_db_session():
                    await db.execute(
                        update(SQL_Lead)
                        .where(SQL_Lead.id == lead["id"])
                        .values(status="unsubscribed", updated_at=datetime.utcnow())
                    )
                    await db.commit()
            except Exception:
                pass
        return

    # Increment attempt counter
    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(
                    update(SQL_Lead)
                    .where(SQL_Lead.id == lead["id"])
                    .values(send_attempts=SQL_Lead.send_attempts + 1, updated_at=datetime.utcnow())
                )
                await db.commit()
        except Exception:
            pass

    try:
        # 2. Trigger send
        await send_campaign_email_to_lead(campaign, lead)

        # 3. Update lead to 'sent' and increment campaign stats
        if _mysql_available:
            try:
                async for db in get_db_session():
                    await db.execute(
                        update(SQL_Lead)
                        .where(SQL_Lead.id == lead["id"])
                        .values(
                            status="sent",
                            sent_at=datetime.utcnow(),
                            last_send_error="",
                            updated_at=datetime.utcnow()
                        )
                    )
                    
                    campaign_row = (await db.execute(select(SQL_Campaign).where(SQL_Campaign.id == campaign["id"]))).scalar_one()
                    raw_stats = getattr(campaign_row, "stats", {})
                    stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                    stats["totalSent"] = int(str(stats.get("totalSent", 0) or 0)) + 1


                    await db.execute(
                        update(SQL_Campaign)
                        .where(SQL_Campaign.id == campaign["id"])
                        .values(stats=stats, updated_at=datetime.utcnow())
                    )


                    # Audit Log
                    await db.execute(insert(SQL_AuditLog).values(
                        action="campaign.email_sent",
                        entity_type="Lead",
                        entity_id=str(lead["id"]),
                        performed_by=campaign.get("userId"),
                        details={"campaignId": campaign["id"], "email": lead["email"]},
                        created_at=datetime.utcnow()
                    ))
                    await db.commit()
            except Exception as e:
                logger.error(f"MySQL update send state failed: {e}")

        # 5. Score lead
        await score_email_sent_async(lead["id"])

    except Exception as err:
        err_msg = str(err)
        if _mysql_available:
            try:
                async for db in get_db_session():
                    await db.execute(
                        update(SQL_Lead)
                        .where(SQL_Lead.id == lead["id"])
                        .values(last_send_error=err_msg, updated_at=datetime.utcnow())
                    )
                    await db.commit()
            except Exception:
                pass

        # Treat SMTP rejection / bounced responses as bounces
        permanent = bool(re.search(r"invalid|not exist|no such user|mailbox unavailable", err_msg, re.IGNORECASE))
        if permanent:
            if _mysql_available:
                try:
                    async for db in get_db_session():
                        await db.execute(
                            update(SQL_Lead)
                            .where(SQL_Lead.id == lead["id"])
                            .values(status="bounced", bounced_at=datetime.utcnow(), updated_at=datetime.utcnow())
                        )
                        
                        campaign_row = (await db.execute(select(SQL_Campaign).where(SQL_Campaign.id == campaign["id"]))).scalar_one()
                        raw_stats = getattr(campaign_row, "stats", {})
                        stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                        stats["totalBounced"] = int(str(stats.get("totalBounced", 0) or 0)) + 1



                        await db.execute(
                            update(SQL_Campaign)
                            .where(SQL_Campaign.id == campaign["id"])
                            .values(stats=stats, updated_at=datetime.utcnow())
                        )

                        # Suppression upsert
                        exist_sup = (await db.execute(
                            select(SQL_Suppression).where(SQL_Suppression.email == lead["email"])
                        )).scalar_one_or_none()
                        if not exist_sup:
                            await db.execute(insert(SQL_Suppression).values(
                                email=lead["email"],
                                reason="bounced",
                                campaign_id=campaign["id"],
                                created_at=datetime.utcnow()
                            ))
                        await db.commit()
                except Exception as e:
                    logger.error(f"MySQL bounce update failed: {e}")


def check_incoming_replies():
    """Poll the IMAP inbox for unread email replies from campaign outreach leads."""
    if not settings.SMTP_USER or not settings.SMTP_PASS:
        return

    import imaplib
    import email
    from email.header import decode_header

    # Determine IMAP server
    smtp_host = settings.SMTP_HOST.lower()
    if settings.IMAP_HOST:
        imap_host = settings.IMAP_HOST
    elif "gmail" in smtp_host:
        imap_host = "imap.gmail.com"
    elif "outlook" in smtp_host or "office365" in smtp_host or "hotmail" in smtp_host or "live.com" in smtp_host:
        imap_host = "outlook.office365.com"
    elif "yahoo" in smtp_host:
        imap_host = "imap.mail.yahoo.com"
    elif "zoho" in smtp_host:
        imap_host = "imap.zoho.com"
    elif smtp_host.startswith("smtp."):
        imap_host = "imap." + smtp_host.split("smtp.", 1)[1]
    else:
        imap_host = settings.SMTP_HOST

    try:
        mail = imaplib.IMAP4_SSL(imap_host, settings.IMAP_PORT, timeout=30.0)
        mail.login(settings.SMTP_USER, settings.SMTP_PASS)
        mail.select("INBOX")

        status, messages = mail.search(None, "UNSEEN")
        if status == "OK" and messages[0]:
            mail_ids = messages[0].split()[-30:]

            for mail_id in mail_ids:
                try:
                    res, msg_data = mail.fetch(mail_id, "(RFC822)")
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            from_header = msg.get("From")
                            if from_header:
                                email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", from_header)
                                if email_match:
                                    sender_email = email_match.group(0).lower().strip()
                                    
                                    # Find lead in MySQL
                                    with get_sync_db_session() as db:
                                        stmt = select(SQL_Lead).where(
                                            SQL_Lead.email == sender_email,
                                            SQL_Lead.status.in_(["sent", "opened", "clicked"])
                                        )
                                        lead_row = db.execute(stmt).scalar_one_or_none()
                                        if lead_row:
                                            body_text = ""
                                            if msg.is_multipart():
                                                for part in msg.walk():
                                                    if part.get_content_type() == "text/plain":
                                                        payload = part.get_payload(decode=True)
                                                        body_text = payload.decode(errors="ignore") if isinstance(payload, bytes) else str(payload)
                                                        break
                                            else:
                                                payload = msg.get_payload(decode=True)
                                                body_text = payload.decode(errors="ignore") if isinstance(payload, bytes) else str(payload)

                                            body_text = body_text.strip() or "Reply received."
                                            reply_subj = str(msg.get("Subject") or "Re: Outreach").strip()

                                            db.execute(
                                                update(SQL_Lead)
                                                .where(SQL_Lead.id == lead_row.id)
                                                .values(
                                                    status="replied",
                                                    reply_subject=reply_subj,
                                                    reply_message=body_text,
                                                    reply_preview=body_text[:200],
                                                    replied_at=datetime.utcnow(),
                                                    updated_at=datetime.utcnow()
                                                )
                                            )
                                            
                                            campaign_row = db.execute(
                                                select(SQL_Campaign).where(SQL_Campaign.id == lead_row.campaign_id)
                                            ).scalar_one()
                                            raw_stats = getattr(campaign_row, "stats", {})
                                            stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                                            stats["totalReplied"] = int(str(stats.get("totalReplied", 0) or 0)) + 1


                                            
                                            db.execute(
                                                update(SQL_Campaign)
                                                .where(SQL_Campaign.id == lead_row.campaign_id)
                                                .values(stats=stats, updated_at=datetime.utcnow())
                                            )
                                            
                                            db.execute(insert(SQL_AuditLog).values(
                                                action="lead.reply",
                                                entity_type="Lead",
                                                entity_id=str(lead_row.id),
                                                details={"email": sender_email, "subject": reply_subj, "preview": body_text[:200]},
                                                created_at=datetime.utcnow()
                                            ))
                                            db.commit()
                                            
                                            score_replied(int(str(lead_row.id)))
                                            logger.info(f"[Email Worker] Detected incoming email reply from {sender_email}")
                                            
                                        mail.store(mail_id, "+FLAGS", "\\Seen")
                except Exception as parse_err:
                    logger.error(f"[Email Worker] Failed to parse IMAP message: {parse_err}")
        
        mail.close()
        mail.logout()
    except Exception as imap_err:
        logger.warning(f"[Email Worker] IMAP polling failed: {imap_err}")


async def check_scheduled_newsletters():
    """Dispatch newsletter editions whose exact scheduled send time has arrived."""
    now = datetime.utcnow()
    editions = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Edition).where(
                    SQL_Edition.status == "scheduled",
                    SQL_Edition.scheduled_at <= now
                ).limit(10)
                res = await db.execute(stmt)
                editions = res.scalars().all()
        except Exception as e:
            logger.error(f"MySQL fetch scheduled editions failed: {e}")

    if not editions:
        return

    # Import lazily to avoid a circular import at module load time
    from app.routes.newsletters import _send_newsletter_background
    base_url = (settings.API_BASE_URL or "http://localhost:5050").rstrip("/") + "/"

    for edition in editions:
        e_id = edition.id
        claimed = False
        async for db in get_db_session():
            stmt = select(SQL_Edition).where(SQL_Edition.id == e_id, SQL_Edition.status == "scheduled")
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row:
                await db.execute(
                    update(SQL_Edition)
                    .where(SQL_Edition.id == e_id)
                    .values(status="sending", sent_at=datetime.utcnow(), updated_at=datetime.utcnow())
                )
                await db.commit()
                claimed = True
        
        if not claimed:
            continue

        try:
            await _send_newsletter_background(
                int(str(e_id)),
                int(str(getattr(edition, "newsletter_id", 0) or 0)),
                str(getattr(edition, "subject", "") or ""),
                str(getattr(edition, "body", "") or ""),
                base_url,
                None,
            )


            logger.info(f"[Email Worker] Dispatched scheduled newsletter edition {e_id}.")
        except Exception as e:
            logger.error(f"[Email Worker] Failed to dispatch scheduled edition {e_id}: {e}")
            async for db in get_db_session():
                await db.execute(
                    update(SQL_Edition)
                    .where(SQL_Edition.id == e_id)
                    .values(status="scheduled", updated_at=datetime.utcnow())
                )
                await db.commit()


async def start_email_worker_loop():
    """Background loop polling MySQL for scheduled campaign emails to process concurrently."""
    logger.info("Email worker background polling loop started.")
    import time
    last_reply_check = 0
    semaphore = asyncio.Semaphore(5)  # Limit concurrent email sends to 5

    async def bounded_process_lead(campaign: dict, lead: dict):
        async with semaphore:
            await process_lead_send(campaign, lead)

    while True:
        try:
            # Update heartbeat in MySQL
            if _mysql_available:
                try:
                    async for db in get_db_session():
                        stmt = select(SQL_SystemStatus).where(SQL_SystemStatus.key_name == "email_worker")
                        row = (await db.execute(stmt)).scalar_one_or_none()
                        if row:
                            await db.execute(
                                update(SQL_SystemStatus)
                                .where(SQL_SystemStatus.key_name == "email_worker")
                                .values(last_active=datetime.utcnow(), status="running")
                            )
                        else:
                            await db.execute(insert(SQL_SystemStatus).values(
                                key_name="email_worker",
                                status="running",
                                last_active=datetime.utcnow(),
                                extra_data={}
                            ))
                        await db.commit()
                except Exception as e:
                    logger.error(f"Failed to update worker heartbeat: {e}")

            # Check replies every 30 seconds
            current_time = time.time()
            if current_time - last_reply_check >= 30:
                last_reply_check = current_time
                try:
                    _spawn_worker_task(asyncio.to_thread(check_incoming_replies))
                except Exception as e:
                    logger.warning(f"[Email Worker] Could not spawn thread for reply check: {e}")

            # Dispatch scheduled newsletters
            _spawn_worker_task(check_scheduled_newsletters())

            # Query active campaigns
            running_campaigns = []
            if _mysql_available:
                try:
                    async for db in get_db_session():
                        stmt = select(SQL_Campaign).where(SQL_Campaign.status == "running")
                        res = await db.execute(stmt)
                        running_campaigns = [_sql_campaign_to_dict(c) for c in res.scalars().all()]
                except Exception as e:
                    logger.error(f"MySQL running campaigns query failed: {e}")

            if running_campaigns:
                campaign_ids = [c["id"] for c in running_campaigns]
                campaign_map = {c["id"]: c for c in running_campaigns}

                now = datetime.utcnow()
                pending_leads = []
                if _mysql_available:
                    try:
                        async for db in get_db_session():
                            stmt = select(SQL_Lead).where(
                                SQL_Lead.campaign_id.in_(campaign_ids),
                                SQL_Lead.status == "pending",
                                (SQL_Lead.send_after <= now) | (SQL_Lead.send_after == None)
                            ).limit(10)
                            res = await db.execute(stmt)
                            pending_leads = [_sql_lead_to_dict(l) for l in res.scalars().all()]
                    except Exception as e:
                        logger.error(f"MySQL pending leads query failed: {e}")

                tasks = []
                for lead in pending_leads:
                    campaign = campaign_map.get(lead["campaignId"])
                    if campaign:
                        if campaign.get("workingHoursOnly") and not is_within_working_hours(campaign.get("timezone", "America/Chicago")):
                            next_send = get_next_working_hour(campaign.get("timezone", "America/Chicago"))
                            if _mysql_available:
                                try:
                                    async for db in get_db_session():
                                        await db.execute(
                                            update(SQL_Lead)
                                            .where(SQL_Lead.id == lead["id"])
                                            .values(send_after=next_send, updated_at=datetime.utcnow())
                                        )
                                        await db.commit()
                                except Exception:
                                    pass
                            logger.info(f"[Email Worker] Lead {lead['email']} postponed to {next_send.isoformat()}")
                            continue
                        tasks.append(bounded_process_lead(campaign, lead))

                if tasks:
                    await asyncio.gather(*tasks)

        except Exception as e:
            logger.error(f"Email worker loop encountered an error: {e}")
        await asyncio.sleep(5)
