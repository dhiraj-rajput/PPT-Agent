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
        return res

    html_body = fill_placeholders(body_tmpl, lead)
    subject = fill_placeholders(subject_tmpl, lead)

    # Rewrite links for tracking
    click_tracked_html, links = rewrite_links_for_tracking(html_body)

    open_tracking_id = new_tracking_id()
    unsub_link = unsubscribe_url(str(lead["_id"]), str(campaign["_id"]))

    final_html = f"""
    {click_tracked_html}
    <p style="font-size:11px;color:#9ca3af;margin-top:24px;">
      Don't want these emails? <a href="{unsub_link}">Unsubscribe</a>.
    </p>
    {open_pixel_tag(open_tracking_id)}
    """

    # Build MIME message
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject

    sender_name = campaign.get("senderName")
    sender_email = campaign.get("senderEmail") or settings.SMTP_USER
    if sender_name:
        msg["From"] = f'"{sender_name}" <{sender_email}>'
    else:
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER

    msg["To"] = lead["email"]
    msg.attach(MIMEText(final_html, "html"))

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


async def start_email_worker_loop():
    """Background loop polling MongoDB for scheduled campaign emails to process."""
    logger.info("Email worker background polling loop started.")
    campaigns_col = get_collection("campaigns")
    leads_col = get_collection("leads")

    while True:
        try:
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
