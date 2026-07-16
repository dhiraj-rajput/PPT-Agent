"""
api/routes/meetings.py
-----------------------
Meetings CRUD — mirrors Node.js server/routes/meetings.js.

Endpoints:
  GET  /api/meetings            — list meetings
  POST /api/meetings            — create meeting + auto video room + invite emails
  POST /api/meetings/:id/cancel — cancel + email attendees
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.utils.auth import get_current_user
from api.utils.mailer import send_meeting_invite_email, send_meeting_cancelled_email
from api.utils.video_rooms import create_video_room
from utils.db_client import get_collection

router = APIRouter(prefix="/meetings", tags=["meetings"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_public_meeting(m: dict) -> dict:
    attendees = []
    for a in m.get("attendees", []):
        attendees.append({
            "name": a.get("name", ""),
            "email": a.get("email", ""),
            "userId": str(a["userId"]) if a.get("userId") else None,
            "inviteSent": a.get("inviteSent", False),
        })
    return {
        "id": str(m["_id"]),
        "title": m.get("title", ""),
        "with": m.get("with", ""),
        "date": m.get("date", ""),
        "time": m.get("time", ""),
        "type": m.get("type", "Video Call"),
        "provider": m.get("provider", "jitsi"),
        "location": m.get("location", ""),
        "meetingLink": m.get("meetingLink", ""),
        "attendees": attendees,
        "status": m.get("status", "scheduled"),
        "cancelledAt": m.get("cancelledAt"),
        "createdAt": m.get("createdAt", ""),
    }


async def _resolve_attendees(raw_attendees: List[dict], users_col) -> List[dict]:
    """Normalize the mixed user-id / email attendees list."""
    if not raw_attendees:
        return []

    user_ids = [a["userId"] for a in raw_attendees if a.get("userId")]
    users = {}
    for uid in user_ids:
        try:
            u = users_col.find_one({"_id": ObjectId(str(uid))})
            if u:
                users[str(u["_id"])] = u
        except Exception:
            pass

    by_email: dict[str, dict] = {}
    for raw in raw_attendees:
        if raw.get("userId") and str(raw["userId"]) in users:
            u = users[str(raw["userId"])]
            by_email[u["email"]] = {
                "name": u.get("name", ""),
                "email": u["email"],
                "userId": u["_id"],
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


def _push_notifications(user_ids: List[str], notif_type: str, title: str, message: str, link: str, related_id: str) -> None:
    try:
        notifs_col = get_collection("notifications")
        docs = [
            {
                "user": ObjectId(uid),
                "type": notif_type,
                "title": title,
                "message": message,
                "link": link,
                "relatedId": related_id,
                "read": False,
                "createdAt": datetime.now(tz=timezone.utc),
            }
            for uid in user_ids
            if uid
        ]
        if docs:
            notifs_col.insert_many(docs)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AttendeeInput(BaseModel):
    userId: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = ""


class CreateMeetingBody(BaseModel):
    title: str
    with_: Optional[str] = None
    date: str
    time: str
    type: Optional[str] = "Video Call"
    location: Optional[str] = ""
    provider: Optional[str] = "jitsi"
    attendees: Optional[List[AttendeeInput]] = []

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def list_meetings(current_user: dict = Depends(get_current_user)):
    meetings_col = get_collection("meetings")
    meetings = list(meetings_col.find().sort("date", 1))
    return {"meetings": [_to_public_meeting(m) for m in meetings]}


@router.post("", status_code=201)
async def create_meeting(
    body: CreateMeetingBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.title or not body.date or not body.time:
        raise HTTPException(400, "Title, date, and time are required.")

    users_col = get_collection("users")
    raw_attendees = [a.dict() for a in (body.attendees or [])]
    resolved = await _resolve_attendees(raw_attendees, users_col)

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
        )
        meeting_link = room["meeting_link"]
        used_provider = room["provider"]
        provider_warning = room.get("warning", "")

    with_name = getattr(body, "with_", None) or ""

    meetings_col = get_collection("meetings")
    result = meetings_col.insert_one({
        "title": body.title,
        "with": with_name,
        "date": body.date,
        "time": body.time,
        "type": meeting_type,
        "provider": used_provider,
        "location": body.location or "",
        "meetingLink": meeting_link,
        "attendees": resolved,
        "status": "scheduled",
        "createdBy": current_user["_id"],
        "createdAt": datetime.now(tz=timezone.utc),
    })

    meeting = meetings_col.find_one({"_id": result.inserted_id})
    meeting_id = str(result.inserted_id)

    # Send invite emails asynchronously (best-effort)
    if resolved:
        organizer_name = current_user.get("name")

        async def send_invites():
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
            meetings_col.update_one({"_id": result.inserted_id}, {"$set": {"attendees": resolved}})

        asyncio.create_task(send_invites())

    # In-app notifications for all attendee users
    attendee_user_ids = [str(a["userId"]) for a in resolved if a.get("userId")]
    _push_notifications(
        [str(current_user["_id"])] + attendee_user_ids,
        notif_type="meeting_scheduled",
        title="Meeting scheduled",
        message=f"\"{body.title}\" is set for {body.date} at {body.time}.",
        link="/meetings",
        related_id=meeting_id,
    )

    response = {"meeting": _to_public_meeting(meeting)}
    if provider_warning:
        response["providerWarning"] = provider_warning
    return response


@router.post("/{meeting_id}/cancel")
async def cancel_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(meeting_id)
    except Exception:
        raise HTTPException(400, "Invalid meeting ID.")

    meetings_col = get_collection("meetings")
    meeting = meetings_col.find_one({"_id": oid})
    if not meeting:
        raise HTTPException(404, "Meeting not found.")
    if meeting.get("status") == "cancelled":
        raise HTTPException(400, "This meeting is already cancelled.")

    meetings_col.update_one(
        {"_id": oid},
        {"$set": {"status": "cancelled", "cancelledAt": datetime.now(tz=timezone.utc)}},
    )
    meeting = meetings_col.find_one({"_id": oid})

    # Send cancellation emails (best-effort)
    attendees = meeting.get("attendees", [])
    if attendees:
        organizer_name = current_user.get("name")
        asyncio.create_task(
            asyncio.gather(
                *[
                    send_meeting_cancelled_email(
                        to_email=a["email"],
                        title=meeting["title"],
                        date=meeting["date"],
                        time=meeting["time"],
                        organizer_name=organizer_name,
                    )
                    for a in attendees
                ],
                return_exceptions=True,
            )
        )

    # In-app notifications
    attendee_user_ids = [str(a["userId"]) for a in attendees if a.get("userId")]
    _push_notifications(
        [str(current_user["_id"])] + attendee_user_ids,
        notif_type="meeting_cancelled",
        title="Meeting cancelled",
        message=f"\"{meeting['title']}\" originally set for {meeting['date']} at {meeting['time']} has been cancelled.",
        link="/meetings",
        related_id=meeting_id,
    )

    return {"meeting": _to_public_meeting(meeting)}
