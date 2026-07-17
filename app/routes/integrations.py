"""
app/routes/integrations.py
---------------------------
Integration settings endpoints — mirrors Node.js server/routes/integrations.js.

Endpoints:
  GET  /api/integrations/google/status   — check if Google is connected
  GET  /api/integrations/google/auth-url — get Google OAuth consent URL
  GET  /api/integrations/google/callback — OAuth callback (Google redirects here)
"""

from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.auth import get_current_user
from utils.db_client import get_collection

router = APIRouter(prefix="/integrations", tags=["integrations"])

from config.settings import settings

_CLIENT_URL = settings.CLIENT_URL
_GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID
_GOOGLE_CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET
_GOOGLE_REDIRECT_URI = settings.GOOGLE_REDIRECT_URI

# ---------------------------------------------------------------------------
# Google OAuth helpers (thin wrappers — gracefully unavailable)
# ---------------------------------------------------------------------------

def _get_google_auth_url(user_id: str) -> str:
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(505, "Google OAuth is not configured (GOOGLE_CLIENT_ID missing).")
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
    
    # Generate and store a secure OAuth state token to prevent CSRF
    import secrets
    from datetime import datetime, timezone, timedelta
    state_token = secrets.token_urlsafe(32)
    get_collection("oauth_states").insert_one({
        "state": state_token,
        "userId": user_id,
        "expireAt": datetime.now(timezone.utc) + timedelta(minutes=10)
    })
    
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state_token)
    return auth_url


def _handle_google_callback(code: str, state: Optional[str] = None) -> None:
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(505, "Google OAuth is not configured.")
        
    user_id_clean = "global"
    if state:
        # Validate OAuth state and resolve to userId
        state_doc = get_collection("oauth_states").find_one_and_delete({"state": state})
        if not state_doc:
            raise HTTPException(400, "Invalid or expired OAuth state parameter.")
        user_id_clean = state_doc.get("userId") or "global"
        
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
    # Store refresh token in MongoDB scoped to userId
    get_collection("integrations").update_one(
        {"service": "google", "userId": user_id_clean},
        {"$set": {
            "service": "google",
            "userId": user_id_clean,
            "connected": True,
            "refreshToken": creds.refresh_token,
            "accessToken": creds.token,
            "tokenExpiry": str(creds.expiry),
        }},
        upsert=True,
    )


def _get_google_connection_status(user_id: str) -> dict:
    doc = get_collection("integrations").find_one({"service": "google", "userId": user_id})
    return {"connected": bool(doc and doc.get("connected"))}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/google/status")
def google_status(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        return _get_google_connection_status(user_id)
    except Exception as exc:
        raise HTTPException(500, f"Could not check Google connection status: {exc}")


@router.get("/google/auth-url")
def google_auth_url(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        return {"url": _get_google_auth_url(user_id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/google/callback")
def google_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error:
        logger.error(f"Google OAuth callback received error from Google: {error}")
        return RedirectResponse(f"{_CLIENT_URL}/settings/integrations?google=error")
    if not code:
        logger.error("Google OAuth callback received no code parameter.")
        return RedirectResponse(f"{_CLIENT_URL}/settings/integrations?google=error")
    try:
        _handle_google_callback(code, state)
        return RedirectResponse(f"{_CLIENT_URL}/settings/integrations?google=connected")
    except Exception as exc:
        import traceback
        print("\n=== GOOGLE OAUTH CALLBACK EXCEPTION TRACEBACK ===")
        traceback.print_exc()
        print("=================================================\n")
        logger.error(f"Google OAuth callback processing failed: {exc}")
        return RedirectResponse(f"{_CLIENT_URL}/settings/integrations?google=error")
