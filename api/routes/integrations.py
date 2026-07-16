"""
api/routes/integrations.py
---------------------------
Integration settings endpoints — mirrors Node.js server/routes/integrations.js.

Endpoints:
  GET  /api/integrations/google/status   — check if Google is connected
  GET  /api/integrations/google/auth-url — get Google OAuth consent URL
  GET  /api/integrations/google/callback — OAuth callback (Google redirects here)
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from api.utils.auth import get_current_user
from utils.db_client import get_collection

router = APIRouter(prefix="/integrations", tags=["integrations"])

_CLIENT_URL = os.getenv("CLIENT_URL", "http://localhost:5173")
_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
_GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/integrations/google/callback"
)

# ---------------------------------------------------------------------------
# Google OAuth helpers (thin wrappers — gracefully unavailable)
# ---------------------------------------------------------------------------

def _get_google_auth_url() -> str:
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(500, "Google OAuth is not configured (GOOGLE_CLIENT_ID missing).")
    from google_auth_oauthlib.flow import Flow  # type: ignore
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": _GOOGLE_CLIENT_ID,
                "client_secret": _GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [_GOOGLE_REDIRECT_URI],
            }
        },
        scopes=[
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
    )
    flow.redirect_uri = _GOOGLE_REDIRECT_URI
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return auth_url


async def _handle_google_callback(code: str) -> None:
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(500, "Google OAuth is not configured.")
    from google_auth_oauthlib.flow import Flow  # type: ignore

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": _GOOGLE_CLIENT_ID,
                "client_secret": _GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [_GOOGLE_REDIRECT_URI],
            }
        },
        scopes=[
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
    )
    flow.redirect_uri = _GOOGLE_REDIRECT_URI
    flow.fetch_token(code=code)
    creds = flow.credentials
    # Store refresh token in MongoDB
    get_collection("integrations").update_one(
        {"service": "google"},
        {"$set": {
            "service": "google",
            "connected": True,
            "refreshToken": creds.refresh_token,
            "accessToken": creds.token,
            "tokenExpiry": str(creds.expiry),
        }},
        upsert=True,
    )


def _get_google_connection_status() -> dict:
    doc = get_collection("integrations").find_one({"service": "google"})
    return {"connected": bool(doc and doc.get("connected"))}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/google/status")
async def google_status(current_user: dict = Depends(get_current_user)):
    try:
        return _get_google_connection_status()
    except Exception as exc:
        raise HTTPException(500, f"Could not check Google connection status: {exc}")


@router.get("/google/auth-url")
async def google_auth_url(current_user: dict = Depends(get_current_user)):
    try:
        return {"url": _get_google_auth_url()}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/google/callback")
async def google_callback(request: Request, code: Optional[str] = None, error: Optional[str] = None):
    if error:
        return RedirectResponse(f"{_CLIENT_URL}/settings/integrations?google=error")
    if not code:
        return RedirectResponse(f"{_CLIENT_URL}/settings/integrations?google=error")
    try:
        await _handle_google_callback(code)
        return RedirectResponse(f"{_CLIENT_URL}/settings/integrations?google=connected")
    except Exception:
        return RedirectResponse(f"{_CLIENT_URL}/settings/integrations?google=error")
