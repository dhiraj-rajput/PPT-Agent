"""
api/utils/video_rooms.py
--------------------------
Video meeting room creation — mirrors Node.js server/utils/googleMeet.js
and server/utils/zoom.js but running inside FastAPI.

Priority: user's chosen provider → Jitsi fallback (always works, no API key).
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from typing import Optional

logger = logging.getLogger(__name__)

_CLIENT_URL = os.getenv("CLIENT_URL", "http://localhost:5173")
_ZOOM_ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID", "")
_ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID", "")
_ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET", "")
_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")


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

    # Step 1 — get OAuth token
    token_resp = await httpx.AsyncClient().post(
        "https://zoom.us/oauth/token",
        params={"grant_type": "account_credentials", "account_id": _ZOOM_ACCOUNT_ID},
        auth=(_ZOOM_CLIENT_ID, _ZOOM_CLIENT_SECRET),
    )
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    # Step 2 — create meeting
    start_time = f"{date}T{time}:00"
    meeting_resp = await httpx.AsyncClient().post(
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
    title: str, date: str, time: str, attendee_emails: list[str]
) -> str:
    """
    Creates a Google Calendar event with a Meet link.
    Requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET + a stored refresh token.
    Raises on failure so the caller can fall back to Jitsi.
    """
    raise NotImplementedError(
        "Google Meet integration requires a persisted OAuth2 refresh token "
        "configured in Settings > Integrations. Falling back to Jitsi."
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def create_video_room(
    provider: str,
    title: str,
    date: str,
    time: str,
    attendee_emails: Optional[list[str]] = None,
) -> dict:
    """
    Returns {provider, meeting_link, warning?}.
    Always succeeds — falls back to Jitsi if the requested provider fails.
    """
    if provider == "zoom" and _ZOOM_ACCOUNT_ID and _ZOOM_CLIENT_ID and _ZOOM_CLIENT_SECRET:
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
                title, date, time, attendee_emails or []
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
