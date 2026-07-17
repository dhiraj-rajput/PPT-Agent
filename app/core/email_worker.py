import asyncio
import logging
import re
from datetime import datetime, timezone
from bson import ObjectId
from config.settings import settings
from utils.db_client import get_collection
from app.core.tracking_helpers import (
    rewrite_links_for_tracking,
    open_pixel_tag,
    unsubscribe_url,
    new_tracking_id,
)

logger = logging.getLogger("email_worker")

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


def add_score(lead_id: ObjectId, delta: int):
    """Add delta to lead score and update grade."""
    try:
        leads_col = get_collection("leads")
        lead = leads_col.find_one({"_id": lead_id})
        if not lead:
            return None
        new_score = lead.get("score", 0) + delta
        new_grade = classify_score(new_score)
        leads_col.update_one(
            {"_id": lead_id},
            {"$set": {"score": new_score, "grade": new_grade}}
        )
    except Exception as e:
        logger.error(f"Failed to add score to lead {lead_id}: {e}")


def score_email_sent(lead_id: ObjectId):
    add_score(lead_id, SCORE_RULES["emailSent"])


def score_email_opened(lead_id: ObjectId):
    add_score(lead_id, SCORE_RULES["emailOpened"])


def score_link_clicked(lead_id: ObjectId):
    add_score(lead_id, SCORE_RULES["linkClicked"])


def score_replied(lead_id: ObjectId):
    add_score(lead_id, SCORE_RULES["replied"])


def score_meeting_booked(lead_id: ObjectId):
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
        res = re.sub(r"{{\s*campaignId\s*}}", str(campaign.get("_id") or ""), res, flags=re.IGNORECASE)
        res = re.sub(r"{{\s*leadId\s*}}", str(lead_data.get("_id") or ""), res, flags=re.IGNORECASE)
        res = re.sub(r"{{\s*clientUrl\s*}}", settings.CLIENT_URL.rstrip("/"), res, flags=re.IGNORECASE)
        return res

    html_body = fill_placeholders(body_tmpl, lead)
    subject = fill_placeholders(subject_tmpl, lead)

    # Rewrite links for tracking
    click_tracked_html, links = rewrite_links_for_tracking(html_body)

    open_tracking_id = new_tracking_id()
    unsub_link = unsubscribe_url(str(lead["_id"]), str(campaign["_id"]))

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
        
        # Attach PDF
        try:
            with open(attach_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=attach_name)
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
    sender_email = campaign.get("senderEmail") or settings.SMTP_USER
    if sender_name:
        msg["From"] = f'"{sender_name}" <{sender_email}>'
    else:
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER

    msg["To"] = lead["email"]

    # Send SMTP email if configured
    if settings.SMTP_USER and settings.SMTP_PASS:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASS,
            use_tls=(settings.SMTP_PORT == 465),
            start_tls=(settings.SMTP_PORT == 587),
        )
    else:
        logger.warning(
            f"[Email Worker Mock Send] SMTP not configured — skipping live send to: {lead['email']}"
        )

    # Pre-register tracking events in MongoDB
    tracking_events_col = get_collection("tracking_events")
    docs = [
        {
            "trackingId": open_tracking_id,
            "leadId": lead["_id"],
            "campaignId": campaign["_id"],
            "type": "open",
            "destinationUrl": "",
            "timestamp": None,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        }
    ]
    for link in links:
        docs.append({
            "trackingId": link["trackingId"],
            "leadId": lead["_id"],
            "campaignId": campaign["_id"],
            "type": "click",
            "destinationUrl": link["destinationUrl"],
            "timestamp": None,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        })

    try:
        tracking_events_col.insert_many(docs, ordered=False)
    except Exception as e:
        logger.error(f"Failed to pre-register tracking events: {e}")

    return {"openTrackingId": open_tracking_id, "links": links}


async def process_lead_send(campaign: dict, lead: dict):
    """Processes suppression check, updates delivery status, sends email, and scores lead."""
    leads_col = get_collection("leads")
    campaigns_col = get_collection("campaigns")
    suppressions_col = get_collection("suppressions")

    # 1. Suppression check
    suppressed = suppressions_col.find_one({"email": lead["email"]})
    if suppressed:
        leads_col.update_one(
            {"_id": lead["_id"]},
            {"$set": {"status": "unsubscribed", "updatedAt": datetime.now(timezone.utc)}}
        )
        return

    # Increment attempt counter
    leads_col.update_one(
        {"_id": lead["_id"]},
        {"$inc": {"sendAttempts": 1}}
    )

    try:
        # 2. Trigger send
        await send_campaign_email_to_lead(campaign, lead)

        # 3. Update lead to 'sent'
        leads_col.update_one(
            {"_id": lead["_id"]},
            {"$set": {
                "status": "sent",
                "sentAt": datetime.now(timezone.utc),
                "lastSendError": "",
                "updatedAt": datetime.now(timezone.utc)
            }}
        )

        # 4. Increment campaign sent stats
        campaigns_col.update_one(
            {"_id": campaign["_id"]},
            {"$inc": {"stats.totalSent": 1}}
        )

        # 5. Score lead
        score_email_sent(lead["_id"])

        # 6. Audit Log
        audit_col = get_collection("audit_logs")
        audit_col.insert_one({
            "action": "campaign.email_sent",
            "entityType": "Lead",
            "entityId": lead["_id"],
            "details": {"campaignId": campaign["_id"], "email": lead["email"]},
            "createdAt": datetime.now(timezone.utc)
        })

    except Exception as err:
        err_msg = str(err)
        leads_col.update_one(
            {"_id": lead["_id"]},
            {"$set": {"lastSendError": err_msg}}
        )

        # Treat SMTP rejection / bounced responses as bounces
        permanent = bool(re.search(r"invalid|not exist|no such user|mailbox unavailable", err_msg, re.IGNORECASE))
        if permanent:
            leads_col.update_one(
                {"_id": lead["_id"]},
                {"$set": {
                    "status": "bounced",
                    "bouncedAt": datetime.now(timezone.utc),
                    "updatedAt": datetime.now(timezone.utc)
                }}
            )
            campaigns_col.update_one(
                {"_id": campaign["_id"]},
                {"$inc": {"stats.totalBounced": 1}}
            )
            suppressions_col.update_one(
                {"email": lead["email"]},
                {
                    "$setOnInsert": {
                        "email": lead["email"],
                        "reason": "bounced",
                        "campaignId": campaign["_id"],
                        "createdAt": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )


def check_incoming_replies():
    """Poll the IMAP inbox for unread email replies from campaign outreach leads."""
    if not settings.SMTP_USER or not settings.SMTP_PASS:
        return

    import imaplib
    import email
    import time
    import socket
    from email.header import decode_header

    # Set connection timeout limits
    socket.setdefaulttimeout(15.0)

    # Determine IMAP server securely
    imap_host = "imap.gmail.com" if "gmail" in settings.SMTP_HOST.lower() else f"imap.{settings.SMTP_HOST.split('smtp.')[-1]}"
    
    try:
        mail = imaplib.IMAP4_SSL(imap_host, 993)
        mail.login(settings.SMTP_USER, settings.SMTP_PASS)
        mail.select("INBOX")

        status, messages = mail.search(None, "UNSEEN")
        if status == "OK" and messages[0]:
            mail_ids = messages[0].split()
            leads_col = get_collection("leads")
            campaigns_col = get_collection("campaigns")

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
                                    
                                    lead = leads_col.find_one({
                                        "email": sender_email,
                                        "status": {"$in": ["sent", "opened", "clicked"]}
                                    })
                                    if lead:
                                        leads_col.update_one(
                                            {"_id": lead["_id"]},
                                            {"$set": {
                                                "status": "replied",
                                                "repliedAt": datetime.now(timezone.utc),
                                                "updatedAt": datetime.now(timezone.utc)
                                            }}
                                        )
                                        
                                        campaigns_col.update_one(
                                            {"_id": lead["campaignId"]},
                                            {"$inc": {"stats.totalReplied": 1}}
                                        )
                                        
                                        get_collection("audit_logs").insert_one({
                                            "action": "lead.reply",
                                            "entityType": "Lead",
                                            "entityId": lead["_id"],
                                            "details": {"email": sender_email, "subject": msg.get("Subject")},
                                            "createdAt": datetime.now(timezone.utc)
                                        })
                                        
                                        score_replied(lead["_id"])
                                        logger.info(f"[Email Worker] Detected incoming email reply from {sender_email}")
                                        
                                    mail.store(mail_id, "+FLAGS", "\\Seen")
                except Exception as parse_err:
                    logger.error(f"[Email Worker] Failed to parse IMAP message: {parse_err}")
        
        mail.close()
        mail.logout()
    except Exception as imap_err:
        logger.debug(f"[Email Worker] IMAP polling skipped or failed: {imap_err}")


async def start_email_worker_loop():
    """Background loop polling MongoDB for scheduled campaign emails to process."""
    logger.info("Email worker background polling loop started.")
    campaigns_col = get_collection("campaigns")
    leads_col = get_collection("leads")
    sys_col = get_collection("system_status")

    import time
    last_reply_check = 0

    while True:
        try:
            # Update heartbeat
            try:
                sys_col.update_one(
                    {"key": "email_worker"},
                    {"$set": {"last_active": datetime.now(timezone.utc), "status": "running"}},
                    upsert=True
                )
            except Exception as e:
                logger.error(f"Failed to update worker heartbeat: {e}")

            # Check replies every 30 seconds
            current_time = time.time()
            if current_time - last_reply_check >= 30:
                last_reply_check = current_time
                asyncio.create_task(asyncio.to_thread(check_incoming_replies))

            # Query for active running campaigns
            running_campaigns = list(campaigns_col.find({"status": "running"}))
            if running_campaigns:
                campaign_ids = [c["_id"] for c in running_campaigns]
                campaign_map = {c["_id"]: c for c in running_campaigns}

                # Find up to 10 pending leads whose send_after is in the past
                now = datetime.now(timezone.utc)
                pending_leads = list(leads_col.find({
                    "campaignId": {"$in": campaign_ids},
                    "status": "pending",
                    "send_after": {"$lte": now}
                }).limit(10))

                for lead in pending_leads:
                    campaign = campaign_map.get(lead["campaignId"])
                    if campaign:
                        await process_lead_send(campaign, lead)
        except Exception as e:
            logger.error(f"Email worker loop encountered an error: {e}")
        await asyncio.sleep(5)
