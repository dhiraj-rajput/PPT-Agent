"""
app/core/video_rooms.py
--------------------------
Video meeting room creation — mirrors Node.js server/utils/googleMeet.js
and server/utils/zoom.js but running inside FastAPI.

Priority: user's chosen provider → Jitsi fallback (always works, no API key).
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.db_client import get_async_collection, get_collection
from config.settings import settings

logger = logging.getLogger(__name__)

import os


def _zoom_config() -> tuple[str, str, str]:
    """Read Zoom credentials fresh so a saved change via /env-keys applies without a restart."""
    return (
        os.environ.get("ZOOM_ACCOUNT_ID") or getattr(settings, "ZOOM_ACCOUNT_ID", "") or "",
        os.environ.get("ZOOM_CLIENT_ID") or getattr(settings, "ZOOM_CLIENT_ID", "") or "",
        os.environ.get("ZOOM_CLIENT_SECRET") or getattr(settings, "ZOOM_CLIENT_SECRET", "") or "",
    )


def _google_config() -> tuple[str, str]:
    """Read Google credentials fresh so a saved change via /env-keys applies without a restart."""
    return (
        os.environ.get("GOOGLE_CLIENT_ID") or getattr(settings, "GOOGLE_CLIENT_ID", "") or "",
        os.environ.get("GOOGLE_CLIENT_SECRET") or getattr(settings, "GOOGLE_CLIENT_SECRET", "") or "",
    )


# ---------------------------------------------------------------------------
# Jitsi (always available, no API key required)
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    return (
        text.lower()
        .replace(" ", "-")
        .replace("_", "-")
    )[:40]


def generate_jitsi_link(title: str) -> str:
    """Generate a unique Jitsi room URL. No account required."""
    token = secrets.token_hex(4)
    room = f"OrbitAvanya-{_slugify(title)}-{token}"
    return f"https://meet.jit.si/{room}"


# ---------------------------------------------------------------------------
# Zoom
# ---------------------------------------------------------------------------

async def _create_zoom_meeting(title: str, date: str, time: str) -> str:
    """
    Creates a Zoom meeting via Zoom Server-to-Server OAuth and returns the join URL.
    Raises on failure so the caller can fall back to Jitsi.
    """
    import httpx

    zoom_account_id, zoom_client_id, zoom_client_secret = _zoom_config()

    # Step 1 — get OAuth token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://zoom.us/oauth/token",
            params={"grant_type": "account_credentials", "account_id": zoom_account_id},
            auth=(zoom_client_id, zoom_client_secret),
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        # Step 2 — create meeting
        start_time = f"{date}T{time}:00"
        meeting_resp = await client.post(
            "https://api.zoom.us/v2/users/me/meetings",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "topic": title,
                "type": 2,
                "start_time": start_time,
                "duration": 60,
                "settings": {"join_before_host": True},
            },
        )
        meeting_resp.raise_for_status()
        return meeting_resp.json()["join_url"]


# ---------------------------------------------------------------------------
# Google Meet
# ---------------------------------------------------------------------------

async def _create_google_meet(
    user_id: Optional[str],
    title: str,
    date: str,
    time: str,
    attendee_emails: list[str],
) -> str:
    """
    Creates a Google Calendar event with a Meet link.
    Requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET + a stored refresh token.
    Uses Motor for DB and asyncio.to_thread for blocking Google API calls.
    """
    google_client_id, google_client_secret = _google_config()
    if not google_client_id:
        raise ValueError("Google OAuth client ID is not configured.")

    user_oid_or_str = user_id or "global"
    integrations_col = get_async_collection("integrations")
    doc = await integrations_col.find_one({"service": "google", "userId": user_oid_or_str})
    if not doc and user_oid_or_str != "global":
        doc = await integrations_col.find_one({"service": "google", "userId": "global"})

    if not doc or not doc.get("connected") or not doc.get("refreshToken"):
        raise ValueError("Google Meet integration is not connected. Connect in Settings > Integrations.")

    def _sync_google_event_create():
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=doc.get("accessToken"),
            refresh_token=doc.get("refreshToken"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=google_client_id,
            client_secret=google_client_secret,
        )

        service = build("calendar", "v3", credentials=creds)

        try:
            dt_str = f"{date}T{time}:00"
            start_dt = datetime.fromisoformat(dt_str)
            end_dt = start_dt + timedelta(minutes=30)
            start_iso = start_dt.isoformat()
            end_iso = end_dt.isoformat()
        except Exception:
            start_iso = datetime.now(timezone.utc).isoformat()
            end_iso = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()

        event = {
            "summary": title,
            "description": "Video meeting created via OrbitAvanya",
            "start": {
                "dateTime": start_iso,
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end_iso,
                "timeZone": "UTC",
            },
            "attendees": [{"email": email} for email in (attendee_emails or [])],
            "conferenceData": {
                "createRequest": {
                    "requestId": str(uuid.uuid4()),
                    "conferenceSolutionKey": {
                        "type": "hangoutsMeet"
                    }
                }
            }
        }

        event_result = service.events().insert(
            calendarId="primary",
            body=event,
            conferenceDataVersion=1
        ).execute()

        meet_link = None
        conf_data = event_result.get("conferenceData", {})
        entry_points = conf_data.get("entryPoints", [])
        for ep in entry_points:
            if ep.get("entryPointType") == "video":
                meet_link = ep.get("uri")
                break

        if not meet_link:
            meet_link = event_result.get("htmlLink")

        if not meet_link:
            raise ValueError("Google Meet link could not be generated by calendar event creation.")

        return meet_link

    return await asyncio.to_thread(_sync_google_event_create)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def create_video_room(
    provider: str,
    title: str,
    date: str,
    time: str,
    attendee_emails: Optional[list[str]] = None,
    user_id: Optional[str] = None,
) -> dict:
    """
    Returns {provider, meeting_link, warning?}.
    Always succeeds — falls back to Jitsi if the requested provider fails.
    """
    zoom_account_id, zoom_client_id, zoom_client_secret = _zoom_config()
    if provider == "zoom" and zoom_account_id and zoom_client_id and zoom_client_secret:
        try:
            join_url = await _create_zoom_meeting(title, date, time)
            return {"provider": "zoom", "meeting_link": join_url}
        except Exception as exc:
            logger.warning(f"[VideoRooms] Zoom failed ({exc}), falling back to Jitsi")
            return {
                "provider": "jitsi",
                "meeting_link": generate_jitsi_link(title),
                "warning": f"Zoom meeting couldn't be created ({exc}) — used a Jitsi link instead.",
            }

    if provider == "google_meet":
        try:
            join_url = await _create_google_meet(
                user_id, title, date, time, attendee_emails or []
            )
            return {"provider": "google_meet", "meeting_link": join_url}
        except Exception as exc:
            logger.warning(f"[VideoRooms] Google Meet failed ({exc}), falling back to Jitsi")
            return {
                "provider": "jitsi",
                "meeting_link": generate_jitsi_link(title),
                "warning": f"Google Meet link couldn't be created ({exc}) — used a Jitsi link instead.",
            }

    # Default: Jitsi
    return {"provider": "jitsi", "meeting_link": generate_jitsi_link(title)}
