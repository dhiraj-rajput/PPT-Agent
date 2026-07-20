"""
app/routes/newsletters.py
--------------------------
Newsletter publication, persistent subscriber management, and edition distribution routes.
Shares mailer and suppression infrastructure with campaign tracking.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr

from app.core.auth import get_current_user
from app.core.mailer import send_company_email_with_attachments
from app.core.tracking_helpers import (
    new_tracking_id,
    open_pixel_tag,
    rewrite_links_for_tracking,
    unsubscribe_url,
)
from utils.db_client import get_collection
from utils.helpers import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/newsletters", tags=["newsletters"])


class CreateNewsletterBody(BaseModel):
    name: str
    description: Optional[str] = ""
    senderName: Optional[str] = "OrbitAvanya Tech"
    senderEmail: Optional[str] = "newsletter@orbitavanyatech.com"


class CreateSubscriberBody(BaseModel):
    email: str
    contactName: Optional[str] = ""
    companyName: Optional[str] = ""


class BulkCompanySubscriberBody(BaseModel):
    companyIds: Optional[List[str]] = []


class CreateEditionBody(BaseModel):
    subject: str
    body: str
    sendNow: Optional[bool] = True


def _format_newsletter(n: dict) -> dict:
    stats = n.get("stats", {}) or {}
    return {
        "id": str(n["_id"]),
        "name": n.get("name", ""),
        "description": n.get("description", ""),
        "senderName": n.get("senderName", "OrbitAvanya Tech"),
        "senderEmail": n.get("senderEmail", ""),
        "stats": {
            "totalSubscribers": stats.get("totalSubscribers", 0),
            "totalSent": stats.get("totalSent", 0),
            "totalOpened": stats.get("totalOpened", 0),
            "totalClicked": stats.get("totalClicked", 0),
            "totalUnsubscribed": stats.get("totalUnsubscribed", 0),
        },
        "createdAt": n.get("createdAt").isoformat() if n.get("createdAt") else None,
        "updatedAt": n.get("updatedAt").isoformat() if n.get("updatedAt") else None,
    }


def _format_subscriber(s: dict) -> dict:
    return {
        "id": str(s["_id"]),
        "newsletterId": str(s["newsletterId"]),
        "email": s.get("email", ""),
        "contactName": s.get("contactName", ""),
        "companyName": s.get("companyName", ""),
        "source": s.get("source", "manual"),
        "status": s.get("status", "subscribed"),
        "subscribedAt": s.get("subscribedAt").isoformat() if s.get("subscribedAt") else None,
        "createdAt": s.get("createdAt").isoformat() if s.get("createdAt") else None,
    }


def _format_edition(e: dict) -> dict:
    stats = e.get("stats", {}) or {}
    return {
        "id": str(e["_id"]),
        "newsletterId": str(e["newsletterId"]),
        "subject": e.get("subject", ""),
        "body": e.get("body", ""),
        "status": e.get("status", "draft"),
        "sentAt": e.get("sentAt").isoformat() if e.get("sentAt") else None,
        "stats": {
            "sent": stats.get("sent", 0),
            "opened": stats.get("opened", 0),
            "clicked": stats.get("clicked", 0),
            "unsubscribed": stats.get("unsubscribed", 0),
        },
        "createdAt": e.get("createdAt").isoformat() if e.get("createdAt") else None,
    }


@router.get("")
def list_newsletters(current_user: dict = Depends(get_current_user)):
    col = get_collection("newsletters")
    items = col.find().sort("createdAt", -1)
    return {"newsletters": [_format_newsletter(n) for n in items]}


@router.post("")
def create_newsletter(
    body: CreateNewsletterBody,
    current_user: dict = Depends(get_current_user),
):
    col = get_collection("newsletters")
    doc = {
        "name": body.name.strip(),
        "description": (body.description or "").strip(),
        "senderName": (body.senderName or "OrbitAvanya Tech").strip(),
        "senderEmail": (body.senderEmail or "newsletter@orbitavanyatech.com").strip(),
        "stats": {
            "totalSubscribers": 0,
            "totalSent": 0,
            "totalOpened": 0,
            "totalClicked": 0,
            "totalUnsubscribed": 0,
        },
        "createdBy": current_user["_id"],
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }
    res = col.insert_one(doc)
    created = col.find_one({"_id": res.inserted_id})
    return {"newsletter": _format_newsletter(created)}


@router.get("/{id}")
def get_newsletter(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    col = get_collection("newsletters")
    item = col.find_one({"_id": oid})
    if not item:
        raise HTTPException(status_code=404, detail="Newsletter not found")

    return {"newsletter": _format_newsletter(item)}


@router.delete("/{id}")
def delete_newsletter(id: str, current_user: dict = Depends(get_current_user)):
    try:
        n_oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    newsletters_col = get_collection("newsletters")
    newsletter = newsletters_col.find_one({"_id": n_oid})
    if not newsletter:
        raise HTTPException(status_code=404, detail="Newsletter not found")

    newsletters_col.delete_one({"_id": n_oid})
    get_collection("editions").delete_many({"newsletterId": n_oid})
    get_collection("newsletter_subscribers").delete_many({"newsletterId": n_oid})
    get_collection("newsletter_sends").delete_many({"newsletterId": n_oid})

    return {"ok": True, "message": "Newsletter deleted successfully"}


@router.get("/{id}/subscribers")
def list_subscribers(
    id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = "all",
    current_user: dict = Depends(get_current_user),
):
    try:
        n_oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    subs_col = get_collection("newsletter_subscribers")
    query: Dict[str, Any] = {"newsletterId": n_oid}
    if status and status != "all":
        query["status"] = status

    total = subs_col.count_documents(query)
    items = subs_col.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)

    return {
        "subscribers": [_format_subscriber(s) for s in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/{id}/subscribers")
def add_subscriber(
    id: str,
    body: CreateSubscriberBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        n_oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")

    subs_col = get_collection("newsletter_subscribers")
    suppressions_col = get_collection("suppressions")

    if suppressions_col.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email is globally unsubscribed")

    existing = subs_col.find_one({"newsletterId": n_oid, "email": email})
    if existing:
        if existing.get("status") == "unsubscribed":
            subs_col.update_one({"_id": existing["_id"]}, {"$set": {"status": "subscribed", "subscribedAt": datetime.now(timezone.utc)}})
            return {"status": "resubscribed"}
        raise HTTPException(status_code=409, detail="Already subscribed to this newsletter")

    doc = {
        "newsletterId": n_oid,
        "email": email,
        "contactName": body.contactName or "",
        "companyName": body.companyName or "",
        "source": "manual",
        "status": "subscribed",
        "subscribedAt": datetime.now(timezone.utc),
        "createdAt": datetime.now(timezone.utc),
    }
    subs_col.insert_one(doc)

    # Update subscriber count
    get_collection("newsletters").update_one(
        {"_id": n_oid},
        {"$inc": {"stats.totalSubscribers": 1}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
    )

    return {"status": "success"}


@router.post("/{id}/subscribers/companies")
def add_company_subscribers(
    id: str,
    body: BulkCompanySubscriberBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        n_oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    companies_col = get_collection("companies")
    subs_col = get_collection("newsletter_subscribers")
    suppressions_col = get_collection("suppressions")

    suppressed = set(s["email"] for s in suppressions_col.find({}, {"email": 1}))
    existing = set(s["email"] for s in subs_col.find({"newsletterId": n_oid}, {"email": 1}))

    query = {}
    if body.companyIds:
        c_oids = []
        c_ueis = []
        for cid in body.companyIds:
            c_str = str(cid)
            c_ueis.append(c_str)
            try:
                c_oids.append(ObjectId(c_str))
            except Exception:
                pass
        
        or_conds = [{"uei": {"$in": c_ueis}}]
        if c_oids:
            or_conds.append({"_id": {"$in": c_oids}})
        query["$or"] = or_conds

    companies = list(companies_col.find(query, {"name": 1, "contact": 1, "email": 1}))
    to_insert = []
    added_count = 0

    for c in companies:
        c_email = (c.get("email") or "").strip().lower()
        if not c_email or "@" not in c_email:
            continue
        if c_email in suppressed or c_email in existing:
            continue

        existing.add(c_email)
        to_insert.append({
            "newsletterId": n_oid,
            "email": c_email,
            "contactName": c.get("contact", ""),
            "companyName": c.get("name", ""),
            "source": "company_db",
            "status": "subscribed",
            "subscribedAt": datetime.now(timezone.utc),
            "createdAt": datetime.now(timezone.utc),
        })
        added_count += 1

    if to_insert:
        subs_col.insert_many(to_insert, ordered=False)
        get_collection("newsletters").update_one(
            {"_id": n_oid},
            {"$inc": {"stats.totalSubscribers": added_count}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
        )

    return {"added": added_count}


@router.post("/{id}/editions")
async def create_edition(
    id: str,
    body: CreateEditionBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        n_oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    newsletters_col = get_collection("newsletters")
    newsletter = newsletters_col.find_one({"_id": n_oid})
    if not newsletter:
        raise HTTPException(status_code=404, detail="Newsletter not found")

    editions_col = get_collection("editions")
    subs_col = get_collection("newsletter_subscribers")
    sends_col = get_collection("newsletter_sends")

    edition_doc = {
        "newsletterId": n_oid,
        "subject": body.subject.strip(),
        "body": body.body.strip(),
        "status": "sending" if body.sendNow else "draft",
        "sentAt": datetime.now(timezone.utc) if body.sendNow else None,
        "stats": {"sent": 0, "opened": 0, "clicked": 0, "unsubscribed": 0},
        "createdBy": current_user["_id"],
        "createdAt": datetime.now(timezone.utc),
    }
    e_res = editions_col.insert_one(edition_doc)
    e_id = e_res.inserted_id

    if body.sendNow:
        subscribers = list(subs_col.find({"newsletterId": n_oid, "status": "subscribed"}))
        sent_count = 0
        events_col = get_collection("tracking_events")

        for sub in subscribers:
            recipient_email = sub.get("email")
            if not recipient_email:
                continue

            tracking_id = new_tracking_id()
            unsub_link = unsubscribe_url(str(sub["_id"]), str(n_oid))

            # 1. Rewrite HTML links for click tracking
            html_body, click_links = rewrite_links_for_tracking(body.body)

            # 2. Append open tracking pixel & unsubscribe link
            pixel = open_pixel_tag(tracking_id)
            body_with_unsub = (
                f"{html_body}\n\n"
                f"{pixel}\n"
                f'<hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;" />'
                f'<p style="font-size:11px;color:#94a3b8;">To unsubscribe from this newsletter, <a href="{unsub_link}">click here</a>.</p>'
            )

            try:
                await send_company_email_with_attachments(
                    to_email=recipient_email,
                    subject=body.subject,
                    body_html=body_with_unsub,
                )
                success = True
                err = ""
            except Exception as mail_err:
                success = False
                err = str(mail_err)

            sends_col.insert_one({
                "editionId": e_id,
                "newsletterId": n_oid,
                "subscriberId": sub["_id"],
                "email": recipient_email,
                "trackingId": tracking_id,
                "status": "sent" if success else "failed",
                "error": err if not success else "",
                "sentAt": datetime.now(timezone.utc),
            })

            if success:
                sent_count += 1
                # Register open tracking event record
                events_col.insert_one({
                    "trackingId": tracking_id,
                    "editionId": e_id,
                    "newsletterId": n_oid,
                    "subscriberId": sub["_id"],
                    "type": "open",
                    "timestamp": None,  # Will be populated when pixel is fetched
                    "createdAt": datetime.now(timezone.utc),
                })

                # Register click tracking event records for links
                for link in click_links:
                    events_col.insert_one({
                        "trackingId": link["trackingId"],
                        "editionId": e_id,
                        "newsletterId": n_oid,
                        "subscriberId": sub["_id"],
                        "destinationUrl": link["destinationUrl"],
                        "type": "click",
                        "timestamp": None,  # Will be populated when link is clicked
                        "createdAt": datetime.now(timezone.utc),
                    })

        editions_col.update_one(
            {"_id": e_id},
            {"$set": {"status": "sent", "stats.sent": sent_count}}
        )

        newsletters_col.update_one(
            {"_id": n_oid},
            {"$inc": {"stats.totalSent": sent_count}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
        )

    created_e = editions_col.find_one({"_id": e_id})
    return {"edition": _format_edition(created_e)}


@router.get("/{id}/editions")
def list_editions(id: str, current_user: dict = Depends(get_current_user)):
    try:
        n_oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    editions_col = get_collection("editions")
    items = editions_col.find({"newsletterId": n_oid}).sort("createdAt", -1)
    return {"editions": [_format_edition(e) for e in items]}
