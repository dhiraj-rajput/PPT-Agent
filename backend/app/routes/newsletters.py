"""
app/routes/newsletters.py
--------------------------
Newsletter creation, subscriber management, edition dispatch, and tracking endpoints.
Uses MySQL.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path
import uuid

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
from utils.db_client import get_db_session, _mysql_available
from models.sql_models import (
    Newsletter as SQL_Newsletter,
    NewsletterSubscriber as SQL_NewsletterSubscriber,
    Edition as SQL_Edition,
    NewsletterSend as SQL_NewsletterSend,
    TrackingEvent as SQL_TrackingEvent,
    Company as SQL_Company,
    Person as SQL_Person,
)
from sqlalchemy import select, insert, update, delete, func, or_, and_

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


def _format_newsletter(n: SQL_Newsletter) -> dict:
    if not n:
        return {}
    stats = n.stats or {}
    return {
        "id": str(n.id),
        "name": n.name or "",
        "description": n.description or "",
        "category": n.category or "General",
        "stats": {
            "totalSubscribers": stats.get("totalSubscribers", 0),
            "totalSent": stats.get("totalSent", 0),
            "totalOpened": stats.get("totalOpened", 0),
            "totalClicked": stats.get("totalClicked", 0),
            "totalUnsubscribed": stats.get("totalUnsubscribed", 0),
        },
        "createdAt": _iso(n.created_at),
        "updatedAt": _iso(n.updated_at),
    }


def _format_edition(e: SQL_Edition) -> dict:
    if not e:
        return {}
    stats = e.stats or {}
    return {
        "id": str(e.id),
        "newsletterId": str(e.newsletter_id),
        "subject": e.subject or "",
        "body": e.body or "",
        "imageUrl": e.image_url,
        "status": e.status or "draft",
        "sentAt": _iso(e.sent_at),
        "scheduledAt": _iso(e.scheduled_at),
        "stats": {
            "sent": stats.get("sent", 0),
            "opened": stats.get("opened", 0),
            "clicked": stats.get("clicked", 0),
            "unsubscribed": stats.get("unsubscribed", 0),
        },
        "createdAt": _iso(e.created_at),
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
    newsletters = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Newsletter).order_by(SQL_Newsletter.created_at.desc())
                res = await db.execute(stmt)
                newsletters = [_format_newsletter(n) for n in res.scalars().all()]
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    return {"newsletters": newsletters}


@router.post("", status_code=201)
async def create_newsletter(
    body: CreateNewsletterBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.name:
        raise HTTPException(status_code=400, detail="Name is required.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                new_n = SQL_Newsletter(
                    name=body.name.strip(),
                    description=(body.description or "").strip(),
                    category=(body.category or "General").strip(),
                    status="active",
                    user_id=int(current_user["id"]),
                    stats={
                        "totalSubscribers": 0,
                        "totalSent": 0,
                        "totalOpened": 0,
                        "totalClicked": 0,
                        "totalUnsubscribed": 0,
                    },
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(new_n)
                await db.commit()
                await db.refresh(new_n)
                return {"newsletter": _format_newsletter(new_n)}
        except Exception as e:
            raise HTTPException(500, f"Database error creating newsletter: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.post("/{id}/subscribers", status_code=201)
async def add_subscribers_to_newsletter(
    id: str,
    body: BulkSubscriberBody,
    current_user: dict = Depends(get_current_user),
):
    """Add subscribers in bulk to MySQL."""
    try:
        n_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    if _mysql_available:
        try:
            async for db in get_db_session():
                newsletter = (await db.execute(select(SQL_Newsletter).where(SQL_Newsletter.id == n_id))).scalar_one_or_none()
                if not newsletter:
                    raise HTTPException(status_code=404, detail="Newsletter not found")

                emails = [s.email.lower().strip() for s in body.subscribers if s.email and "@" in s.email]
                if not emails:
                    return {"added": 0}

                stmt_existing = select(SQL_NewsletterSubscriber.email).where(
                    SQL_NewsletterSubscriber.newsletter_id == n_id,
                    SQL_NewsletterSubscriber.email.in_(emails)
                )
                existing_emails = set((await db.execute(stmt_existing)).scalars().all())

                to_insert = []
                seen = set()
                for s in body.subscribers:
                    e = s.email.lower().strip()
                    if e and "@" in e and e not in existing_emails and e not in seen:
                        seen.add(e)
                        to_insert.append({
                            "newsletter_id": n_id,
                            "email": e,
                            "name": (s.name or "").strip(),
                            "status": "subscribed",
                            "subscribed_at": datetime.utcnow()
                        })

                if to_insert:
                    await db.execute(insert(SQL_NewsletterSubscriber).values(to_insert))
                    
                    # Update newsletter stats
                    raw_stats = getattr(newsletter, "stats", {})
                    stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                    stats["totalSubscribers"] = int(str(stats.get("totalSubscribers", 0) or 0)) + len(to_insert)


                    await db.execute(
                        update(SQL_Newsletter)
                        .where(SQL_Newsletter.id == n_id)
                        .values(stats=stats, updated_at=datetime.utcnow())
                    )
                    await db.commit()
                    return {"added": len(to_insert)}
                return {"added": 0}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error adding subscribers: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.get("/{id}/subscribers")
async def list_newsletter_subscribers(
    id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """Retrieve subscriber list for a specific newsletter from MySQL."""
    try:
        n_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    subscribers = []
    total = 0

    if _mysql_available:
        try:
            async for db in get_db_session():
                count_stmt = select(func.count()).select_from(SQL_NewsletterSubscriber).where(SQL_NewsletterSubscriber.newsletter_id == n_id)
                total = (await db.execute(count_stmt)).scalar() or 0

                skip = (page - 1) * limit
                stmt = select(SQL_NewsletterSubscriber).where(SQL_NewsletterSubscriber.newsletter_id == n_id).order_by(SQL_NewsletterSubscriber.subscribed_at.desc()).offset(skip).limit(limit)
                res = await db.execute(stmt)
                for d in res.scalars().all():
                    subscribers.append({
                        "id": str(d.id),
                        "email": d.email or "",
                        "name": d.name or "",
                        "status": d.status or "subscribed",
                        "subscribedAt": _iso(d.subscribed_at),
                        "createdAt": _iso(d.subscribed_at),
                    })
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")

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
        n_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    if _mysql_available:
        try:
            async for db in get_db_session():
                newsletter = (await db.execute(select(SQL_Newsletter).where(SQL_Newsletter.id == n_id))).scalar_one_or_none()
                if not newsletter:
                    raise HTTPException(status_code=404, detail="Newsletter not found")

                emails_to_add = set()
                if body.manualEmail and "@" in body.manualEmail:
                    emails_to_add.add(body.manualEmail.lower().strip())

                if body.companyIds:
                    c_ids = []
                    for cid in body.companyIds:
                        try:
                            c_ids.append(int(cid))
                        except ValueError:
                            pass
                    if c_ids:
                        stmt_comp = select(SQL_Company.email).where(SQL_Company.id.in_(c_ids))
                        res_comp = await db.execute(stmt_comp)
                        for em in res_comp.scalars().all():
                            if em and "@" in em:
                                emails_to_add.add(em.lower().strip())

                if not emails_to_add:
                    return {"added": 0}

                stmt_existing = select(SQL_NewsletterSubscriber.email).where(
                    SQL_NewsletterSubscriber.newsletter_id == n_id,
                    SQL_NewsletterSubscriber.email.in_(list(emails_to_add))
                )
                existing_emails = set((await db.execute(stmt_existing)).scalars().all())

                to_insert = []
                for em in emails_to_add:
                    if em not in existing_emails:
                        to_insert.append({
                            "newsletter_id": n_id,
                            "email": em,
                            "name": "",
                            "status": "subscribed",
                            "subscribed_at": datetime.utcnow()
                        })

                if to_insert:
                    await db.execute(insert(SQL_NewsletterSubscriber).values(to_insert))
                    
                    raw_stats = getattr(newsletter, "stats", {})
                    stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                    stats["totalSubscribers"] = int(str(stats.get("totalSubscribers", 0) or 0)) + len(to_insert)


                    await db.execute(
                        update(SQL_Newsletter)
                        .where(SQL_Newsletter.id == n_id)
                        .values(stats=stats, updated_at=datetime.utcnow())
                    )
                    await db.commit()
                    return {"added": len(to_insert)}
                return {"added": 0}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


class AddPeopleSubscribersBody(BaseModel):
    peopleIds: List[str] = []
    manualEmail: Optional[str] = None


@router.post("/{id}/subscribers/people", status_code=201)
async def add_people_subscribers_to_newsletter(
    id: str,
    body: AddPeopleSubscribersBody,
    current_user: dict = Depends(get_current_user),
):
    """Add subscribers from people records or manual email entry to a newsletter."""
    try:
        n_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    if _mysql_available:
        try:
            async for db in get_db_session():
                newsletter = (await db.execute(select(SQL_Newsletter).where(SQL_Newsletter.id == n_id))).scalar_one_or_none()
                if not newsletter:
                    raise HTTPException(status_code=404, detail="Newsletter not found")

                emails_to_add = set()
                if body.manualEmail and "@" in body.manualEmail:
                    emails_to_add.add(body.manualEmail.lower().strip())

                if body.peopleIds:
                    p_ids = []
                    for pid in body.peopleIds:
                        try:
                            p_ids.append(int(pid))
                        except ValueError:
                            pass
                    if p_ids:
                        stmt_people = select(SQL_Person.email).where(SQL_Person.id.in_(p_ids))
                        res_people = await db.execute(stmt_people)
                        for em in res_people.scalars().all():
                            if em and "@" in em:
                                emails_to_add.add(em.lower().strip())

                if not emails_to_add:
                    return {"added": 0}

                stmt_existing = select(SQL_NewsletterSubscriber.email).where(
                    SQL_NewsletterSubscriber.newsletter_id == n_id,
                    SQL_NewsletterSubscriber.email.in_(list(emails_to_add))
                )
                existing_emails = set((await db.execute(stmt_existing)).scalars().all())

                to_insert = []
                for em in emails_to_add:
                    if em not in existing_emails:
                        to_insert.append({
                            "newsletter_id": n_id,
                            "email": em,
                            "name": "",
                            "status": "subscribed",
                            "subscribed_at": datetime.utcnow()
                        })

                if to_insert:
                    await db.execute(insert(SQL_NewsletterSubscriber).values(to_insert))
                    
                    raw_stats = getattr(newsletter, "stats", {})
                    stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                    stats["totalSubscribers"] = int(str(stats.get("totalSubscribers", 0) or 0)) + len(to_insert)

                    await db.execute(
                        update(SQL_Newsletter)
                        .where(SQL_Newsletter.id == n_id)
                        .values(stats=stats, updated_at=datetime.utcnow())
                    )
                    await db.commit()
                    return {"added": len(to_insert)}
                return {"added": 0}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


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
    e_id: int,
    n_id: int,
    subject: str,
    body_text: str,
    base_url: str,
    image_url: Optional[str] = None
):
    logger.info(f"Starting background newsletter dispatch for edition {e_id}...")

    subscribers = []
    newsletter_name = "OrbitAvanya Tech"

    if _mysql_available:
        try:
            async for db in get_db_session():
                # Get newsletter info
                stmt_n = select(SQL_Newsletter).where(SQL_Newsletter.id == n_id)
                n_row = (await db.execute(stmt_n)).scalar_one_or_none()
                if n_row:
                    newsletter_name = n_row.name or "OrbitAvanya Tech"
        except Exception as e:
            logger.error(f"MySQL background fetch failed: {e}")
            return

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

    semaphore = asyncio.Semaphore(10)

    async def send_single_newsletter(sub: dict):
        recipient_email = sub.get("email")
        if not recipient_email:
            return 0

        async with semaphore:
            tracking_id = new_tracking_id()
            unsub_link = unsubscribe_url(str(sub["id"]), str(n_id))
            html_body, click_links = rewrite_links_for_tracking(body_text)

            pixel = open_pixel_tag(tracking_id)
            body_with_unsub = (
                f'<div style="background:#f1f5f9;padding:28px 12px;font-family:sans-serif;">'
                f'  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:16px;'
                f'overflow:hidden;box-shadow:0 4px 18px rgba(28,21,30,0.08);">'
                f'    <div style="padding:20px 24px 4px;">{header_img_html}</div>'
                f'    <div style="padding:4px 28px 24px;color:#334155;line-height:1.65;font-size:14px;">{html_body}</div>'
                f'    <div style="background:#f8fafc;padding:14px 24px;">'
                f'      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
                f'        <td style="font-size:11px;color:#94a3b8;text-align:left;">'
                f'You are receiving this because you subscribed to {newsletter_name}.'
                f'        </td>'
                f'        <td style="font-size:11px;text-align:right;white-space:nowrap;padding-left:12px;">'
                f'<a href="{unsub_link}" style="color:#236576;text-decoration:underline;font-weight:600;">Unsubscribe</a>'
                f'        </td>'
                f'      </tr></table>'
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

            # Write to newsletter_sends in MySQL
            async for db in get_db_session():
                db.add(SQL_NewsletterSend(
                    edition_id=e_id,
                    subscriber_id=sub["id"],
                    status="sent" if success else "failed",
                    sent_at=datetime.utcnow()
                ))

                if success:
                    # Insert tracking event
                    db.add(SQL_TrackingEvent(
                        tracking_id=tracking_id,
                        edition_id=e_id,
                        newsletter_id=n_id,
                        subscriber_id=sub["id"],
                        event_type="open",
                        timestamp=None,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    ))
                    for link in click_links:
                        db.add(SQL_TrackingEvent(
                            tracking_id=link["trackingId"],
                            edition_id=e_id,
                            newsletter_id=n_id,
                            subscriber_id=sub["id"],
                            destination_url=link["destinationUrl"],
                            event_type="click",
                            timestamp=None,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        ))
                await db.commit()
            return 1 if success else 0

    total_sent_count = 0
    BATCH_SIZE = 50
    offset = 0

    if not _mysql_available:
        return

    while True:
        batch_subscribers = []
        try:
            async for db in get_db_session():
                stmt_sub = select(SQL_NewsletterSubscriber).where(
                    SQL_NewsletterSubscriber.newsletter_id == n_id,
                    SQL_NewsletterSubscriber.status != "unsubscribed"
                ).order_by(SQL_NewsletterSubscriber.id.asc()).offset(offset).limit(BATCH_SIZE)
                res_sub = await db.execute(stmt_sub)
                batch_subscribers = [{"id": s.id, "email": s.email} for s in res_sub.scalars().all()]
        except Exception as e:
            logger.error(f"MySQL background fetch failed: {e}")
            break

        if not batch_subscribers:
            break

        # Process the batch concurrently
        results = await asyncio.gather(*[send_single_newsletter(sub) for sub in batch_subscribers])
        total_sent_count += sum(int(r or 0) for r in results)
        offset += BATCH_SIZE

    async for db in get_db_session():
        # Update edition stats
        edition_row = (await db.execute(select(SQL_Edition).where(SQL_Edition.id == e_id))).scalar_one()
        raw_stats = getattr(edition_row, "stats", {})
        stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
        stats["sent"] = int(total_sent_count)
        await db.execute(
            update(SQL_Edition)
            .where(SQL_Edition.id == e_id)
            .values(status="sent", stats=stats, updated_at=datetime.utcnow())
        )

        # Update newsletter stats
        newsletter_row = (await db.execute(select(SQL_Newsletter).where(SQL_Newsletter.id == n_id))).scalar_one()
        raw_stats_news = getattr(newsletter_row, "stats", {})
        stats_news = {str(k): v for k, v in dict(raw_stats_news).items()} if isinstance(raw_stats_news, dict) else {}
        stats_news["totalSent"] = int(str(stats_news.get("totalSent", 0) or 0)) + int(total_sent_count)
        await db.execute(
            update(SQL_Newsletter)
            .where(SQL_Newsletter.id == n_id)
            .values(stats=stats_news, updated_at=datetime.utcnow())
        )

        await db.commit()

    logger.info(f"Background newsletter dispatch completed. Sent: {total_sent_count} emails.")


@router.post("/{id}/editions")
async def create_edition(
    id: str,
    body: CreateEditionBody,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    try:
        n_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    now = datetime.utcnow()
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

    if _mysql_available:
        try:
            async for db in get_db_session():
                newsletter = (await db.execute(select(SQL_Newsletter).where(SQL_Newsletter.id == n_id))).scalar_one_or_none()
                if not newsletter:
                    raise HTTPException(status_code=404, detail="Newsletter not found")

                new_ed = SQL_Edition(
                    newsletter_id=n_id,
                    subject=body.subject.strip(),
                    body=body.body.strip(),
                    image_url=body.imageUrl.strip() if body.imageUrl else None,
                    status=status,
                    sent_at=now if status == "sending" else None,
                    scheduled_at=scheduled_dt if is_scheduled else None,
                    stats={"sent": 0, "opened": 0, "clicked": 0, "unsubscribed": 0},
                    created_at=now,
                    updated_at=now
                )
                db.add(new_ed)
                await db.commit()
                await db.refresh(new_ed)

                e_id = new_ed.id
                created_e = new_ed

            if status == "sending":
                base_url = str(request.base_url)
                background_tasks.add_task(
                    _send_newsletter_background,
                    int(str(e_id)),
                    n_id,
                    body.subject.strip(),
                    body.body.strip(),
                    base_url,
                    body.imageUrl.strip() if body.imageUrl else None
                )

            return {"edition": _format_edition(created_e)}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.get("/{id}/editions")
async def list_editions(id: str, current_user: dict = Depends(get_current_user)):
    try:
        n_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid newsletter ID")

    editions = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Edition).where(SQL_Edition.newsletter_id == n_id).order_by(SQL_Edition.created_at.desc())
                res = await db.execute(stmt)
                editions = [_format_edition(e) for e in res.scalars().all()]
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    return {"editions": editions}


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
        e_id = int(edition_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid edition ID")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Edition).where(SQL_Edition.id == e_id)
                edition = (await db.execute(stmt)).scalar_one_or_none()
                if not edition:
                    raise HTTPException(status_code=404, detail="Edition not found")

                # created_by? Wait, editions does not have a user_id or created_by field in SQL schema,
                # let's skip the createdBy check or keep it logic if it's there. The SQL schema does not
                # have created_by for Edition. So we don't need user_id matching since all admins/writers can manage it.

                updates: Dict[str, Any] = {
                    "subject": body.subject.strip(),
                    "body": body.body.strip(),
                    "image_url": body.imageUrl.strip() if body.imageUrl else None,
                    "updated_at": datetime.utcnow(),
                }

                if getattr(body, "clearSchedule", False):
                    updates["scheduled_at"] = None
                    if getattr(edition, "status", "") == "scheduled":
                        updates["status"] = "draft"

                elif getattr(body, "scheduledAt", None):
                    try:
                        sch_str = str(body.scheduledAt)
                        scheduled_dt = datetime.fromisoformat(sch_str.replace("Z", "+00:00"))
                        if scheduled_dt.tzinfo is None:
                            scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        raise HTTPException(status_code=400, detail="Invalid scheduledAt timestamp format.")

                    if scheduled_dt <= datetime.now(timezone.utc):
                        raise HTTPException(status_code=400, detail="scheduledAt must be in the future.")

                    updates["scheduled_at"] = scheduled_dt
                    if edition.status in ("draft", "scheduled"):
                        updates["status"] = "scheduled"

                await db.execute(
                    update(SQL_Edition)
                    .where(SQL_Edition.id == e_id)
                    .values(**updates)
                )
                await db.commit()
                return {"status": "success"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.delete("/editions/{edition_id}")
async def delete_edition(
    edition_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        e_id = int(edition_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid edition ID")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Edition).where(SQL_Edition.id == e_id)
                edition = (await db.execute(stmt)).scalar_one_or_none()
                if not edition:
                    raise HTTPException(status_code=404, detail="Edition not found")

                await db.execute(delete(SQL_Edition).where(SQL_Edition.id == e_id))
                await db.execute(delete(SQL_NewsletterSend).where(SQL_NewsletterSend.edition_id == e_id))
                await db.execute(delete(SQL_TrackingEvent).where(SQL_TrackingEvent.edition_id == e_id))
                await db.commit()
                return {"status": "success"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")
