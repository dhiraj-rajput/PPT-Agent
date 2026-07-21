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
            "openid",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
    )
    flow.redirect_uri = _GOOGLE_REDIRECT_URI
    
    # Generate and store a secure OAuth state token to prevent CSRF
    import secrets
    from datetime import datetime, timezone, timedelta
    state_token = secrets.token_urlsafe(32)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state_token)
    
    get_collection("oauth_states").insert_one({
        "state": state_token,
        "userId": user_id,
        "codeVerifier": getattr(flow, "code_verifier", None),
        "expireAt": datetime.now(timezone.utc) + timedelta(minutes=10)
    })
    
    return auth_url


def _handle_google_callback(code: str, state: Optional[str] = None) -> None:
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(505, "Google OAuth is not configured.")
        
    user_id_clean = "global"
    code_verifier = None
    if state:
        # Validate OAuth state and resolve to userId
        state_doc = get_collection("oauth_states").find_one_and_delete({"state": state})
        if not state_doc:
            raise HTTPException(400, "Invalid or expired OAuth state parameter.")
        user_id_clean = state_doc.get("userId") or "global"
        code_verifier = state_doc.get("codeVerifier")
        
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
            "openid",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
    )
    flow.redirect_uri = _GOOGLE_REDIRECT_URI
    flow.fetch_token(code=code, code_verifier=code_verifier)
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


@router.delete("/google")
def disconnect_google(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        get_collection("integrations").delete_one({"service": "google", "userId": user_id})
        return {"success": True, "message": "Google Meet integration disconnected."}
    except Exception as exc:
        raise HTTPException(500, f"Could not disconnect Google integration: {exc}")


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
        return RedirectResponse(f"{_CLIENT_URL}/integrations?google=error")
    if not code:
        logger.error("Google OAuth callback received no code parameter.")
        return RedirectResponse(f"{_CLIENT_URL}/integrations?google=error")
    try:
        _handle_google_callback(code, state)
        return RedirectResponse(f"{_CLIENT_URL}/integrations?google=connected")
    except Exception as exc:
        import traceback
        print("\n=== GOOGLE OAUTH CALLBACK EXCEPTION TRACEBACK ===")
        traceback.print_exc()
        print("=================================================\n")
        logger.error(f"Google OAuth callback processing failed: {exc}")
        return RedirectResponse(f"{_CLIENT_URL}/integrations?google=error")


# ---------------------------------------------------------------------------
# SAM.gov API Key Integration
# ---------------------------------------------------------------------------

from pydantic import BaseModel

class SamApiKeyPayload(BaseModel):
    api_key: str


@router.get("/sam/status")
def sam_status(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        doc = get_collection("integrations").find_one({"service": "sam", "userId": user_id})
        raw_key = ""
        if doc and doc.get("connected"):
            raw_key = doc.get("apiKey", "")
        if not raw_key:
            env_keys = read_env_file_keys()
            raw_key = env_keys.get("SAM_GOV_API_KEY") or os.environ.get("SAM_GOV_API_KEY") or getattr(settings, "SAM_GOV_API_KEY", "") or ""
            
        if raw_key and not raw_key.startswith("your_") and len(raw_key) > 5:
            obfuscated = f"****{raw_key[-4:]}" if len(raw_key) >= 4 else "****"
            return {"connected": True, "apiKey": obfuscated}
        return {"connected": False, "apiKey": ""}
    except Exception as exc:
        raise HTTPException(500, f"Could not check SAM.gov connection status: {exc}")


@router.post("/sam/connect")
def sam_connect(payload: SamApiKeyPayload, current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        api_key = payload.api_key.strip()
        if not api_key:
            raise HTTPException(400, "API key cannot be empty.")
            
        get_collection("integrations").update_one(
            {"service": "sam", "userId": user_id},
            {"$set": {
                "service": "sam",
                "userId": user_id,
                "apiKey": api_key,
                "connected": True
            }},
            upsert=True
        )
        
        update_env_file({"SAM_GOV_API_KEY": api_key})
        os.environ["SAM_GOV_API_KEY"] = api_key
        
        return {"success": True, "message": "SAM.gov API Key saved successfully."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Could not save SAM.gov API Key: {exc}")


@router.delete("/sam")
def sam_disconnect(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        get_collection("integrations").delete_one({"service": "sam", "userId": user_id})
        return {"success": True, "message": "SAM.gov API Key disconnected."}
    except Exception as exc:
        raise HTTPException(500, f"Could not disconnect SAM.gov: {exc}")


# ---------------------------------------------------------------------------
# General Environment Key Editor
# ---------------------------------------------------------------------------

def read_env_file_keys() -> dict:
    env_path = ".env"
    if not os.path.exists(env_path):
        return {}
    
    keys = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in line:
                parts = line.split("=", 1)
                k = parts[0].strip()
                v = parts[1].strip()
                # strip potential quotes around value
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                keys[k] = v
    return keys


def update_env_file(updates: dict) -> None:
    env_path = ".env"
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            pass
            
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    updated_keys = set()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            parts = line.split("=", 1)
            key = parts[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)
        
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")
            
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


# Keys that hold real secrets and must always be masked before leaving the server.
# Everything else in TARGET_KEYS (hosts, model names, ports, usernames, account ids)
# is not sensitive and is returned in full so the UI can actually show/prefill it.
_SECRET_KEY_SUFFIXES = ("_API_KEY", "_SECRET", "_PASS", "_KEY", "_TOKEN", "_LI_AT")


def _is_secret_key(key: str) -> bool:
    return key.endswith(_SECRET_KEY_SUFFIXES) or key == "LINKEDIN_LI_AT"


def obfuscate_key(val: str) -> str:
    if not val:
        return ""
    # Don't obfuscate short values if they are placeholders/ports/hosts
    if len(val) <= 6:
        return val
    return f"****{val[-4:]}"


# Every field any integration card on the frontend can submit. Kept in sync with
# Frontend/orbitavanya/src/pages/Integrations.jsx — a key missing here can be saved
# but will never be reported back as "connected" or shown for editing.
TARGET_KEYS = [
    "TAVILY_API_KEY",
    "SAM_GOV_API_KEY",
    "SERPAPI_API_KEY",
    "FIRECRAWL_API_KEY",
    "OLLAMA_API_KEY",
    "OLLAMA_HOST",
    "OLLAMA_MODEL",
    "OLLAMA_TIMEOUT",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
    "LINKEDIN_LI_AT",
    "COMPANIES_HOUSE_KEY",
    "ZOOM_ACCOUNT_ID",
    "ZOOM_CLIENT_ID",
    "ZOOM_CLIENT_SECRET",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASS",
    "SMTP_FROM",
]


@router.get("/env-keys")
def get_env_keys(current_user: dict = Depends(get_current_user)):
    try:
        env_keys = read_env_file_keys()

        response = {}
        for k in TARGET_KEYS:
            val = env_keys.get(k) or os.environ.get(k) or str(getattr(settings, k, "")) or ""
            response[k] = obfuscate_key(val) if _is_secret_key(k) else val

        return response
    except Exception as exc:
        raise HTTPException(500, f"Failed to retrieve environment API keys: {exc}")


@router.get("/linkedin/status")
def linkedin_status(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        env_keys = read_env_file_keys()
        li_at = env_keys.get("LINKEDIN_LI_AT") or os.environ.get("LINKEDIN_LI_AT") or ""
        
        doc = get_collection("integrations").find_one({"service": "linkedin", "userId": user_id})
        
        if not li_at or "EXPIRED" in li_at.upper() or (doc and doc.get("expired")):
            return {"connected": False, "expired": True, "status": "expired"}
            
        return {"connected": True, "expired": False, "status": "connected"}
    except Exception as exc:
        return {"connected": False, "expired": True, "status": "expired"}



@router.post("/env-keys")
def save_env_keys(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        current_keys = read_env_file_keys()
        
        updates = {}
        for k, new_val in payload.items():
            if new_val is None:
                continue
            new_val = str(new_val).strip()
            # If new_val contains ****, it is obfuscated and unchanged.
            if "****" in new_val:
                continue
            updates[k] = new_val
            
        if updates:
            update_env_file(updates)
            
            # Load and update in-memory settings & os.environ
            from config.settings import settings
            for k, v in updates.items():
                os.environ[k] = v
                if hasattr(settings, k):
                    current_type = type(getattr(settings, k))
                    try:
                        if current_type is int:
                            setattr(settings, k, int(v))
                        elif current_type is float:
                            setattr(settings, k, float(v))
                        elif current_type is bool:
                            setattr(settings, k, v.lower() in ("true", "1", "yes"))
                        else:
                            setattr(settings, k, v)
                    except Exception as e:
                        logger.error(f"Failed to cast env variable {k} to type {current_type}: {e}")
                        setattr(settings, k, v)
                
                if k == "LINKEDIN_LI_AT" and v:
                    user_id = str(current_user["_id"])
                    get_collection("integrations").update_one(
                        {"service": "linkedin", "userId": user_id},
                        {"$set": {"connected": True, "expired": False, "status": "connected", "li_at": v}},
                        upsert=True
                    )
                        
        return {"status": "success", "message": "API keys updated successfully."}
    except Exception as exc:
        raise HTTPException(500, f"Failed to save environment API keys: {exc}")
