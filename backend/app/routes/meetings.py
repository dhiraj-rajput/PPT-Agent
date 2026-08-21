"""
app/routes/meetings.py
-----------------------
Meetings CRUD — using MySQL.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from models.sql_models import (
    Meeting as SQL_Meeting,
)
from models.sql_models import (
    Notification as SQL_Notification,
)
from models.sql_models import (
    User as SQLUser,
)
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from utils.db_client import _mysql_available, get_db_session

from app.core.auth import get_current_user
from app.core.mailer import send_meeting_cancelled_email, send_meeting_invite_email
from app.core.video_rooms import create_video_room

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings", tags=["meetings"])


def _iso(dt: Any) -> str | None:
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


def _to_public_meeting(m: SQL_Meeting) -> dict:
    if not m:
        return {}
    attendees = []
    raw_att = m.attendees
    if isinstance(raw_att, dict):
        raw_att = raw_att.get("list") or raw_att.get("attendees") or []
    if isinstance(raw_att, list):
        for a in raw_att:
            if isinstance(a, dict):
                attendees.append({
                    "name": a.get("name", ""),
                    "email": a.get("email", ""),
                    "userId": str(a["userId"]) if a.get("userId") else None,
                    "inviteSent": a.get("inviteSent", False),
                })
    return {
        "id": str(m.id),
        "title": m.title or "",
        "with": m.with_someone or "",
        "date": m.date or "",
        "time": m.time or "",
        "type": "In Person" if getattr(m, "provider", "") == "in-person" else "Video Call",
        "provider": getattr(m, "provider", "manual") or "manual",
        "location": m.description or "",
        "meetingLink": m.meeting_url or "",
        "attendees": attendees,
        "status": getattr(m, "status", "scheduled") or "scheduled",
        "cancelledAt": _iso(getattr(m, "updated_at", None)) if getattr(m, "status", "") == "cancelled" else None,
        "createdAt": _iso(getattr(m, "created_at", None)),
    }


async def _resolve_attendees(raw_attendees: list[dict]) -> list[dict]:
    """Normalize the mixed user-id / email attendees list (batch query) from MySQL."""
    if not raw_attendees:
        return []

    user_ids = []
    for a in raw_attendees:
        if a.get("userId"):
            try:
                user_ids.append(int(a["userId"]))
            except ValueError:
                pass

    users = {}
    if _mysql_available and user_ids:
        async for db in get_db_session():
            stmt = select(SQLUser).where(SQLUser.id.in_(user_ids))
            res = await db.execute(stmt)
            for u in res.scalars().all():
                users[str(u.id)] = u

    by_email: dict[str, dict] = {}
    for raw in raw_attendees:
        if raw.get("userId") and str(raw["userId"]) in users:
            u = users[str(raw["userId"])]
            by_email[u.email] = {
                "name": u.name or "",
                "email": u.email,
                "userId": str(u.id),
                "inviteSent": False,
            }
        elif raw.get("email"):
            email = raw["email"].lower().strip()
            if email:
                by_email[email] = {
                    "name": raw.get("name", ""),
                    "email": email,
                    "userId": None,
                    "inviteSent": False,
                }
    return list(by_email.values())


async def _push_notifications_async(user_ids: list[str], notif_type: str, title: str, message: str, link: str, related_id: str) -> None:
    if not _mysql_available:
        return
    try:
        async for db in get_db_session():
            for uid in user_ids:
                if uid:
                    try:
                        db.add(SQL_Notification(
                            user_id=int(uid),
                            notification_type=notif_type,
                            title=title,
                            message=message,
                            link=link,
                            related_id=related_id,
                            is_read=False,
                            created_at=datetime.utcnow()
                        ))
                    except ValueError:
                        pass
            await db.commit()
    except Exception as e:
        logger.warning(f"[Meetings] Push notification error: {e}")


class AttendeeInput(BaseModel):
    userId: str | None = None
    email: str | None = None
    name: str | None = ""


class CreateMeetingBody(BaseModel):
    title: str
    with_: str | None = None
    date: str
    time: str
    type: str | None = "Video Call"
    location: str | None = ""
    provider: str | None = "jitsi"
    attendees: list[AttendeeInput] | None = Field(default_factory=list)

    class Config:
        populate_by_name = True


@router.get("")
async def list_meetings(current_user: dict = Depends(get_current_user)):
    meetings = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Meeting).order_by(SQL_Meeting.date.asc())
                res = await db.execute(stmt)
                meetings = [_to_public_meeting(m) for m in res.scalars().all()]
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    return {"meetings": meetings}


@router.post("", status_code=201)
async def create_meeting(
    body: CreateMeetingBody,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    if not body.title or not body.date or not body.time:
        raise HTTPException(400, "Title, date, and time are required.")

    raw_attendees = [a.dict() for a in (body.attendees or [])]
    resolved = await _resolve_attendees(raw_attendees)

    meeting_type = "In Person" if body.type == "In Person" else "Video Call"
    meeting_link = ""
    used_provider = "in-person"
    provider_warning = ""

    if meeting_type == "Video Call":
        safe_provider = body.provider if body.provider in ("jitsi", "zoom", "google_meet") else "jitsi"
        room = await create_video_room(
            provider=safe_provider,
            title=body.title,
            date=body.date,
            time=body.time,
            attendee_emails=[a["email"] for a in resolved],
            user_id=str(current_user["id"]),
        )
        meeting_link = room["meeting_link"]
        used_provider = room["provider"]
        provider_warning = room.get("warning", "")

    with_name = getattr(body, "with_", None) or ""

    if _mysql_available:
        try:
            async for db in get_db_session():
                new_meet = SQL_Meeting(
                    user_id=int(current_user["id"]),
                    title=body.title,
                    description=body.location or "",
                    date=body.date,
                    time=body.time,
                    provider=used_provider,
                    meeting_url=meeting_link,
                    with_someone=with_name,
                    attendees=resolved,
                    status="scheduled",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(new_meet)
                await db.commit()
                await db.refresh(new_meet)
                meeting_id = str(new_meet.id)
                meeting_obj = new_meet
        except Exception as e:
            raise HTTPException(500, f"Database error creating meeting: {e}")

    # Send invite emails asynchronously (best-effort)
    if resolved:
        organizer_name = current_user.get("name")

        async def send_invites(m_id):
            results = await asyncio.gather(
                *[
                    send_meeting_invite_email(
                        to_email=a["email"],
                        title=body.title,
                        date=body.date,
                        time=body.time,
                        meeting_type=meeting_type,
                        meeting_link=meeting_link,
                        location=body.location,
                        organizer_name=organizer_name,
                    )
                    for a in resolved
                ],
                return_exceptions=True,
            )
            # Update inviteSent flags
            for i, r in enumerate(results):
                resolved[i]["inviteSent"] = not isinstance(r, Exception)
            
            async for db in get_db_session():
                await db.execute(
                    update(SQL_Meeting)
                    .where(SQL_Meeting.id == int(m_id))
                    .values(attendees=resolved)
                )
                await db.commit()

        background_tasks.add_task(send_invites, meeting_id)

    # In-app notifications for all attendee users
    attendee_user_ids = [str(a["userId"]) for a in resolved if a.get("userId")]
    await _push_notifications_async(
        [str(current_user["id"])] + attendee_user_ids,
        notif_type="meeting_scheduled",
        title="Meeting scheduled",
        message=f"\"{body.title}\" is set for {body.date} at {body.time}.",
        link="/meetings",
        related_id=meeting_id,
    )

    response = {"meeting": _to_public_meeting(meeting_obj)}
    if provider_warning:
        response["providerWarning"] = provider_warning
    return response


@router.post("/{meeting_id}/cancel")
async def cancel_meeting(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    try:
        mid = int(meeting_id)
    except ValueError:
        raise HTTPException(400, "Invalid meeting ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Meeting).where(SQL_Meeting.id == mid)
                res = await db.execute(stmt)
                meeting = res.scalar_one_or_none()
                if not meeting:
                    raise HTTPException(404, "Meeting not found.")
                if getattr(meeting, "status", "") == "cancelled":
                    raise HTTPException(400, "This meeting is already cancelled.")

                await db.execute(
                    update(SQL_Meeting)
                    .where(SQL_Meeting.id == mid)
                    .values(status="cancelled", updated_at=datetime.utcnow())
                )
                await db.commit()

                # refetch
                stmt_new = select(SQL_Meeting).where(SQL_Meeting.id == mid)
                meeting = (await db.execute(stmt_new)).scalar_one()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error cancelling meeting: {e}")

    # Send cancellation emails (best-effort)
    raw_att = getattr(meeting, "attendees", [])
    attendees = raw_att if isinstance(raw_att, list) else []
    if attendees:
        organizer_name = current_user.get("name")
        meeting_title = meeting.title or ""
        meeting_date = meeting.date or ""
        meeting_time = meeting.time or ""
        
        async def send_cancellations():
            await asyncio.gather(
                *[
                    send_meeting_cancelled_email(
                        to_email=str(a.get("email", "") or ""),
                        title=str(meeting_title or ""),
                        date=str(meeting_date or ""),
                        time=str(meeting_time or ""),
                        organizer_name=str(organizer_name) if organizer_name else None,
                    )
                    for a in attendees
                ],
                return_exceptions=True,
            )

        background_tasks.add_task(send_cancellations)

    # In-app notifications
    attendee_user_ids = [str(a["userId"]) for a in attendees if a.get("userId")]
    await _push_notifications_async(
        [str(current_user["id"])] + attendee_user_ids,
        notif_type="meeting_cancelled",
        title="Meeting cancelled",
        message=f"\"{meeting.title}\" originally set for {meeting.date} at {meeting.time} has been cancelled.",
        link="/meetings",
        related_id=meeting_id,
    )

    return {"meeting": _to_public_meeting(meeting)}
