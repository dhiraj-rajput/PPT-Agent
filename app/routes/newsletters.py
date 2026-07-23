"""
app/routes/newsletters.py
--------------------------
Newsletter creation, subscriber management, edition dispatch, and tracking endpoints.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional
from pathlib import Path
import uuid

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, File, UploadFile, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.mailer import send_company_email_with_attachments
from app.core.tracking_helpers import (
    rewrite_links_for_tracking,
    open_pixel_tag,
    unsubscribe_url,
    new_tracking_id,
)
from utils.db_client import get_async_collection, get_collection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/newsletters", tags=["newsletters"])


def _iso(dt: Any) -> Optional[str]:
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


class CreateSubscriberBody(BaseModel):
    email: str
    contactName: Optional[str] = ""
    companyName: Optional[str] = ""


class BulkCompanySubscriberBody(BaseModel):
    companyIds: Optional[List[str]] = []
    manualEmail: Optional[str] = ""


class CreateEditionBody(BaseModel):
    subject: str
    body: str
    imageUrl: Optional[str] = None
    sendNow: Optional[bool] = True
    scheduledAt: Optional[str] = None


def _format_newsletter(n: Optional[dict]) -> dict:
    if not n:
        return {}
    stats = n.get("stats", {}) or {}
    return {
        "id": str(n["_id"]),
        "name": n.get("name", ""),
        "description": n.get("description", ""),
        "category": n.get("category", "General"),
        "stats": {
            "totalSubscribers": stats.get("totalSubscribers", 0),
            "totalSent": stats.get("totalSent", 0),
            "totalOpened": stats.get("totalOpened", 0),
            "totalClicked": stats.get("totalClicked", 0),
            "totalUnsubscribed": stats.get("totalUnsubscribed", 0),
        },
        "createdAt": _iso(n.get("createdAt")),
        "updatedAt": _iso(n.get("updatedAt")),
    }


def _format_edition(e: Optional[dict]) -> dict:
    if not e:
        return {}
    stats = e.get("stats", {}) or {}
    return {
        "id": str(e["_id"]),
        "newsletterId": str(e["newsletterId"]),
        "subject": e.get("subject", ""),
        "body": e.get("body", ""),
        "imageUrl": e.get("imageUrl"),
        "status": e.get("status", "draft"),
        "sentAt": _iso(e.get("sentAt")),
        "scheduledAt": _iso(e.get("scheduledAt")),
        "stats": {
            "sent": stats.get("sent", 0),
            "opened": stats.get("opened", 0),
            "clicked": stats.get("clicked", 0),
            "unsubscribed": stats.get("unsubscribed", 0),
        },
        "createdAt": _iso(e.get("createdAt")),
    }


class CreateNewsletterBody(BaseModel):
    name: str
    description: Optional[str] = ""
    category: Optional[str] = "General"


class SubscriberInput(BaseModel):
    email: str
    name: Optional[str] = ""


class BulkSubscriberBody(BaseModel):
    subscribers: List[SubscriberInput]


@router.get("")
async def list_newsletters(current_user: dict = Depends(get_current_user)):
    col = get_async_collection("newsletters")
    items = await col.find().sort("createdAt", -1).to_list(length=1000)
    return {"newsletters": [_format_newsletter(n) for n in items]}


@router.post("", status_code=201)
async def create_newsletter(
    body: CreateNewsletterBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.name:
        raise HTTPException(status_code=400, detail="Name is required.")

    col = get_async_collection("newsletters")
    doc = {
        "name": body.name.strip(),
        "description": (body.description or "").strip(),
        "category": (body.category or "General").strip(),
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

    res = await col.insert_one(doc)
    created = await col.find_one({"_id": res.inserted_id})
    return {"newsletter": _format_newsletter(created)}


@router.post("/{id}/subscribers", status_code=201)
async def add_subscribers_to_newsletter(
    id: str,
    body: BulkSubscriberBody,
    current_user: dict = Depends(get_current_user),
):
    """Add subscribers in bulk using insert_many (Eliminates N+1 query loop)."""
    try:
        n_oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    newsletters_col = get_async_collection("newsletters")
    newsletter = await newsletters_col.find_one({"_id": n_oid})
    if not newsletter:
        raise HTTPException(status_code=404, detail="Newsletter not found")

    subs_col = get_async_collection("newsletter_subscribers")
    
    emails = [s.email.lower().strip() for s in body.subscribers if s.email and "@" in s.email]
    existing = await subs_col.find({"newsletterId": n_oid, "email": {"$in": emails}}, {"email": 1}).to_list(length=len(emails))
    existing_emails = set(e["email"] for e in existing)

    to_insert = []
    seen = set()
    for s in body.subscribers:
        e = s.email.lower().strip()
        if e and "@" in e and e not in existing_emails and e not in seen:
            seen.add(e)
            to_insert.append({
                "newsletterId": n_oid,
                "email": e,
                "name": (s.name or "").strip(),
                "status": "subscribed",
                "subscribedAt": datetime.now(timezone.utc),
                "createdAt": datetime.now(timezone.utc),
            })

    if to_insert:
        await subs_col.insert_many(to_insert, ordered=False)
        added_count = len(to_insert)
        await newsletters_col.update_one(
            {"_id": n_oid},
            {"$inc": {"stats.totalSubscribers": added_count}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
        )
    else:
        added_count = 0

    return {"added": added_count}


@router.get("/{id}/subscribers")
async def list_newsletter_subscribers(
    id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """Retrieve subscriber list for a specific newsletter."""
    try:
        n_oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    subs_col = get_async_collection("newsletter_subscribers")
    skip = (page - 1) * limit
    total = await subs_col.count_documents({"newsletterId": n_oid})
    docs = await subs_col.find({"newsletterId": n_oid}).sort("createdAt", -1).skip(skip).limit(limit).to_list(length=limit)

    subscribers = []
    for d in docs:
        subscribers.append({
            "id": str(d["_id"]),
            "email": d.get("email", ""),
            "name": d.get("name", ""),
            "status": d.get("status", "subscribed"),
            "subscribedAt": _iso(d.get("subscribedAt")),
            "createdAt": _iso(d.get("createdAt")),
        })

    return {
        "subscribers": subscribers,
        "total": total,
        "page": page,
        "limit": limit,
    }


class AddCompanySubscribersBody(BaseModel):
    companyIds: List[str] = []
    manualEmail: Optional[str] = None


@router.post("/{id}/subscribers/companies", status_code=201)
async def add_company_subscribers_to_newsletter(
    id: str,
    body: AddCompanySubscribersBody,
    current_user: dict = Depends(get_current_user),
):
    """Add subscribers from company records or manual email entry to a newsletter."""
    try:
        n_oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    newsletters_col = get_async_collection("newsletters")
    newsletter = await newsletters_col.find_one({"_id": n_oid})
    if not newsletter:
        raise HTTPException(status_code=404, detail="Newsletter not found")

    subs_col = get_async_collection("newsletter_subscribers")
    emails_to_add = set()

    if body.manualEmail and "@" in body.manualEmail:
        emails_to_add.add(body.manualEmail.lower().strip())

    if body.companyIds:
        companies_col = get_async_collection("companies")
        c_oids = []
        for cid in body.companyIds:
            try:
                c_oids.append(ObjectId(cid))
            except InvalidId:
                pass
        if c_oids:
            comp_docs = await companies_col.find({"_id": {"$in": c_oids}}, {"email": 1, "name": 1}).to_list(length=len(c_oids))
            for cd in comp_docs:
                em = cd.get("email")
                if em and "@" in em:
                    emails_to_add.add(em.lower().strip())

    if not emails_to_add:
        return {"added": 0}

    existing = await subs_col.find({"newsletterId": n_oid, "email": {"$in": list(emails_to_add)}}, {"email": 1}).to_list(length=len(emails_to_add))
    existing_emails = set(e["email"] for e in existing)

    to_insert = []
    for em in emails_to_add:
        if em not in existing_emails:
            to_insert.append({
                "newsletterId": n_oid,
                "email": em,
                "name": "",
                "status": "subscribed",
                "subscribedAt": datetime.now(timezone.utc),
                "createdAt": datetime.now(timezone.utc),
            })

    if to_insert:
        await subs_col.insert_many(to_insert, ordered=False)
        added_count = len(to_insert)
        await newsletters_col.update_one(
            {"_id": n_oid},
            {"$inc": {"stats.totalSubscribers": added_count}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
        )
    else:
        added_count = 0

    return {"added": added_count}


@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        UPLOAD_DIR = Path("private/newsletter_images")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        file_ext = Path(file.filename).suffix if file.filename else ".jpg"
        unique_name = f"{uuid.uuid4().hex}{file_ext}"
        dest_path = UPLOAD_DIR / unique_name
        
        content = await file.read()
        def write_img():
            with open(dest_path, "wb") as f:
                f.write(content)

        await asyncio.to_thread(write_img)
            
        return {"imageUrl": unique_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {e}")


@router.get("/images/{filename}")
def serve_image(filename: str):
    safe_filename = Path(filename).name
    image_path = Path("private/newsletter_images") / safe_filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
        
    content_type = "image/jpeg"
    lower_name = filename.lower()
    if lower_name.endswith(".png"):
        content_type = "image/png"
    elif lower_name.endswith(".gif"):
        content_type = "image/gif"
    elif lower_name.endswith(".webp"):
        content_type = "image/webp"
    elif lower_name.endswith(".svg"):
        content_type = "image/svg+xml"
        
    return FileResponse(image_path, media_type=content_type)


async def _send_newsletter_background(
    e_id: ObjectId,
    n_oid: ObjectId,
    subject: str,
    body_text: str,
    base_url: str,
    image_url: Optional[str] = None
):
    logger.info(f"Starting background newsletter dispatch for edition {e_id}...")

    subs_col = get_async_collection("newsletter_subscribers")
    sends_col = get_async_collection("newsletter_sends")
    editions_col = get_async_collection("editions")
    newsletters_col = get_async_collection("newsletters")
    events_col = get_async_collection("tracking_events")

    subscribers = await subs_col.find({"newsletterId": n_oid, "status": {"$ne": "unsubscribed"}}).to_list(length=10000)

    newsletter_doc = await newsletters_col.find_one({"_id": n_oid}, {"name": 1})
    newsletter_name = (newsletter_doc or {}).get("name") or "OrbitAvanya Tech"
    if image_url:
        img_url = f"{base_url}api/newsletters/images/{image_url}"
        header_img_html = (
            f'<div style="background:linear-gradient(135deg,#1c151e 0%,#382a3c 45%,#236576 100%);'
            f'border-radius:14px;padding:6px;margin-bottom:24px;box-shadow:0 8px 24px rgba(28,21,30,0.25);">'
            f'  <img src="{img_url}" alt="Newsletter Header Banner" '
            f'style="max-width:100%;height:auto;border-radius:10px;display:block;margin:0 auto;" />'
            f'</div>'
        )
    else:
        header_img_html = (
            f'<div style="background:linear-gradient(135deg,#1c151e 0%,#533f5a 45%,#236576 100%);'
            f'border-radius:14px;padding:32px 28px;margin-bottom:24px;text-align:center;'
            f'box-shadow:0 8px 24px rgba(28,21,30,0.25);">'
            f'  <div style="display:inline-block;width:40px;height:4px;background:#f7b708;border-radius:2px;margin-bottom:14px;"></div>'
            f'  <p style="margin:0;color:#f9c639;font-size:11px;font-weight:700;letter-spacing:2px;'
            f'text-transform:uppercase;font-family:sans-serif;">{newsletter_name}</p>'
            f'  <h1 style="margin:10px 0 0;color:#ffffff;font-size:22px;font-weight:800;'
            f'font-family:sans-serif;line-height:1.3;">{subject}</h1>'
            f'</div>'
        )

    semaphore = asyncio.Semaphore(5)

    async def send_single_newsletter(sub: dict):
        recipient_email = sub.get("email")
        if not recipient_email:
            return 0

        async with semaphore:
            tracking_id = new_tracking_id()
            unsub_link = unsubscribe_url(str(sub["_id"]), str(n_oid))

            html_body, click_links = rewrite_links_for_tracking(body_text)

        pixel = open_pixel_tag(tracking_id)
        body_with_unsub = (
            f'<div style="background:#f1f5f9;padding:28px 12px;font-family:sans-serif;">'
            f'  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:16px;'
            f'overflow:hidden;box-shadow:0 4px 18px rgba(28,21,30,0.08);">'
            f'    <div style="padding:20px 24px 4px;">{header_img_html}</div>'
            f'    <div style="padding:4px 28px 24px;color:#334155;line-height:1.65;font-size:14px;">{html_body}</div>'
            f'    <div style="background:#f8fafc;padding:18px 24px;border-top:1px solid #e2e8f0;">'
            f'      <p style="margin:0;font-size:11px;color:#94a3b8;text-align:center;">'
            f'You are receiving this because you subscribed to {newsletter_name}. '
            f'<a href="{unsub_link}" style="color:#236576;text-decoration:underline;font-weight:600;">Unsubscribe</a>'
            f'      </p>'
            f'    </div>'
            f'  </div>'
            f"</div>"
            f"{pixel}"
        )

        try:
            await send_company_email_with_attachments(
                to_email=recipient_email,
                subject=subject,
                body_html=body_with_unsub,
            )
            success = True
            err = ""
        except Exception as mail_err:
            success = False
            err = str(mail_err)

            await sends_col.insert_one({
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
                event_docs = [{
                    "trackingId": tracking_id,
                    "editionId": e_id,
                    "newsletterId": n_oid,
                    "subscriberId": sub["_id"],
                    "type": "open",
                    "timestamp": None,
                    "createdAt": datetime.now(timezone.utc),
                }]
                for link in click_links:
                    event_docs.append({
                        "trackingId": link["trackingId"],
                        "editionId": e_id,
                        "newsletterId": n_oid,
                        "subscriberId": sub["_id"],
                        "destinationUrl": link["destinationUrl"],
                        "type": "click",
                        "timestamp": None,
                        "createdAt": datetime.now(timezone.utc),
                    })
                await events_col.insert_many(event_docs, ordered=False)
                return 1
            return 0

    results = await asyncio.gather(*[send_single_newsletter(sub) for sub in subscribers])
    sent_count = sum(results)

    await editions_col.update_one(
        {"_id": e_id},
        {"$set": {"status": "sent", "stats.sent": sent_count}}
    )

    await newsletters_col.update_one(
        {"_id": n_oid},
        {"$inc": {"stats.totalSent": sent_count}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
    )
    logger.info(f"Background newsletter dispatch completed. Sent: {sent_count} emails.")


@router.post("/{id}/editions")
async def create_edition(
    id: str,
    body: CreateEditionBody,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    try:
        n_oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    newsletters_col = get_async_collection("newsletters")
    newsletter = await newsletters_col.find_one({"_id": n_oid})
    if not newsletter:
        raise HTTPException(status_code=404, detail="Newsletter not found")

    editions_col = get_async_collection("editions")

    now = datetime.now(timezone.utc)
    scheduled_dt: Optional[datetime] = None
    if body.scheduledAt:
        try:
            scheduled_dt = datetime.fromisoformat(body.scheduledAt.replace("Z", "+00:00"))
            if scheduled_dt.tzinfo is None:
                scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid scheduledAt timestamp format.")

    is_scheduled = bool(scheduled_dt and scheduled_dt > now)

    if is_scheduled:
        status = "scheduled"
    elif body.sendNow:
        status = "sending"
    else:
        status = "draft"

    edition_doc = {
        "newsletterId": n_oid,
        "subject": body.subject.strip(),
        "body": body.body.strip(),
        "imageUrl": body.imageUrl.strip() if body.imageUrl else None,
        "status": status,
        "sentAt": now if status == "sending" else None,
        "scheduledAt": scheduled_dt if is_scheduled else None,
        "stats": {"sent": 0, "opened": 0, "clicked": 0, "unsubscribed": 0},
        "createdBy": current_user["_id"],
        "createdAt": now,
    }
    e_res = await editions_col.insert_one(edition_doc)
    e_id = e_res.inserted_id

    if status == "sending":
        base_url = str(request.base_url)
        background_tasks.add_task(
            _send_newsletter_background,
            e_id,
            n_oid,
            body.subject.strip(),
            body.body.strip(),
            base_url,
            body.imageUrl.strip() if body.imageUrl else None
        )

    created_e = await editions_col.find_one({"_id": e_id})
    return {"edition": _format_edition(created_e)}


@router.get("/{id}/editions")
async def list_editions(id: str, current_user: dict = Depends(get_current_user)):
    try:
        n_oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    editions_col = get_async_collection("editions")
    items = await editions_col.find({"newsletterId": n_oid}).sort("createdAt", -1).to_list(length=1000)
    return {"editions": [_format_edition(e) for e in items]}


class UpdateEditionBody(BaseModel):
    subject: str
    body: str
    imageUrl: Optional[str] = None
    scheduledAt: Optional[str] = None
    clearSchedule: Optional[bool] = False


@router.put("/editions/{edition_id}")
async def update_edition(
    edition_id: str,
    body: UpdateEditionBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        e_oid = ObjectId(edition_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid edition ID")

    editions_col = get_async_collection("editions")
    edition = await editions_col.find_one({"_id": e_oid})
    if not edition:
        raise HTTPException(status_code=404, detail="Edition not found")

    if edition.get("createdBy") != current_user["_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    updates: Dict[str, Any] = {
        "subject": body.subject.strip(),
        "body": body.body.strip(),
        "imageUrl": body.imageUrl.strip() if body.imageUrl else None,
        "updatedAt": datetime.now(timezone.utc),
    }

    if getattr(body, "clearSchedule", False):
        updates["scheduledAt"] = None
        if edition.get("status") == "scheduled":
            updates["status"] = "draft"
    elif getattr(body, "scheduledAt", None):
        try:
            scheduled_dt = datetime.fromisoformat(body.scheduledAt.replace("Z", "+00:00"))
            if scheduled_dt.tzinfo is None:
                scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid scheduledAt timestamp format.")

        if scheduled_dt <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="scheduledAt must be in the future.")

        updates["scheduledAt"] = scheduled_dt
        if edition.get("status") in ("draft", "scheduled"):
            updates["status"] = "scheduled"

    await editions_col.update_one({"_id": e_oid}, {"$set": updates})
    return {"status": "success"}


@router.delete("/editions/{edition_id}")
async def delete_edition(
    edition_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        e_oid = ObjectId(edition_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid edition ID")

    editions_col = get_async_collection("editions")
    edition = await editions_col.find_one({"_id": e_oid})
    if not edition:
        raise HTTPException(status_code=404, detail="Edition not found")

    if edition.get("createdBy") != current_user["_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    await editions_col.delete_one({"_id": e_oid})
    await get_async_collection("newsletter_sends").delete_many({"editionId": e_oid})
    await get_async_collection("tracking_events").delete_many({"editionId": e_oid})
    
    return {"status": "success"}
