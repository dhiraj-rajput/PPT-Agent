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
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import get_async_collection, get_collection
from config.settings import settings

router = APIRouter(prefix="/integrations", tags=["integrations"])

_CLIENT_URL = settings.CLIENT_URL
_GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID
_GOOGLE_CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET
_GOOGLE_REDIRECT_URI = settings.GOOGLE_REDIRECT_URI

# ---------------------------------------------------------------------------
# Google OAuth helpers
# ---------------------------------------------------------------------------

async def _get_google_auth_url_async(user_id: str) -> str:
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "") or ""
    if not client_id or "sem90bnjfcss" in client_id or "your_" in client_id or len(client_id) < 15:
        raise HTTPException(
            status_code=400,
            detail="Google OAuth is not configured. Please set a valid GOOGLE_CLIENT_ID from Google Cloud Console in backend/.env file."
        )
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
    
    import secrets
    from datetime import datetime, timezone, timedelta
    state_token = secrets.token_urlsafe(32)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state_token)
    
    oauth_states_col = get_async_collection("oauth_states")
    await oauth_states_col.insert_one({
        "state": state_token,
        "userId": user_id,
        "codeVerifier": getattr(flow, "code_verifier", None),
        "expireAt": datetime.now(timezone.utc) + timedelta(minutes=10)
    })
    
    return auth_url


async def _handle_google_callback_async(code: str, state: Optional[str] = None) -> None:
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(505, "Google OAuth is not configured.")
        
    user_id_clean = "global"
    code_verifier = None
    if state:
        oauth_states_col = get_async_collection("oauth_states")
        state_doc = await oauth_states_col.find_one_and_delete({"state": state})
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

    integrations_col = get_async_collection("integrations")
    await integrations_col.update_one(
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


async def _get_google_connection_status_async(user_id: str) -> dict:
    integrations_col = get_async_collection("integrations")
    doc = await integrations_col.find_one({"service": "google", "userId": user_id})
    return {"connected": bool(doc and doc.get("connected"))}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/google/status")
async def google_status(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        return await _get_google_connection_status_async(user_id)
    except Exception as exc:
        raise HTTPException(500, f"Could not check Google connection status: {exc}")


@router.delete("/google")
async def disconnect_google(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        integrations_col = get_async_collection("integrations")
        await integrations_col.delete_one({"service": "google", "userId": user_id})
        return {"success": True, "message": "Google Meet integration disconnected."}
    except Exception as exc:
        raise HTTPException(500, f"Could not disconnect Google integration: {exc}")


@router.get("/google/auth-url")
async def google_auth_url(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        url = await _get_google_auth_url_async(user_id)
        return {"url": url}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/google/callback")
async def google_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error:
        logger.error(f"Google OAuth callback received error from Google: {error}")
        return RedirectResponse(f"{_CLIENT_URL}/integrations?google=error")
    if not code:
        logger.error("Google OAuth callback received no code parameter.")
        return RedirectResponse(f"{_CLIENT_URL}/integrations?google=error")
    try:
        await _handle_google_callback_async(code, state)
        return RedirectResponse(f"{_CLIENT_URL}/integrations?google=connected")
    except Exception as exc:
        logger.error(f"Google OAuth callback processing failed: {exc}", exc_info=True)
        return RedirectResponse(f"{_CLIENT_URL}/integrations?google=error")


# ---------------------------------------------------------------------------
# SAM.gov API Key Integration
# ---------------------------------------------------------------------------

class SamApiKeyPayload(BaseModel):
    api_key: str


@router.get("/sam/status")
async def sam_status(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        integrations_col = get_async_collection("integrations")
        doc = await integrations_col.find_one({"service": "sam", "userId": user_id})
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
async def sam_connect(payload: SamApiKeyPayload, current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        api_key = payload.api_key.strip()
        if not api_key:
            raise HTTPException(400, "API key cannot be empty.")
            
        integrations_col = get_async_collection("integrations")
        await integrations_col.update_one(
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
async def sam_disconnect(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        integrations_col = get_async_collection("integrations")
        await integrations_col.delete_one({"service": "sam", "userId": user_id})
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


_SECRET_KEY_SUFFIXES = ("_API_KEY", "_SECRET", "_PASS", "_KEY", "_TOKEN", "_LI_AT")


def _is_secret_key(key: str) -> bool:
    return key.endswith(_SECRET_KEY_SUFFIXES) or key == "LINKEDIN_LI_AT"


def obfuscate_key(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 6:
        return val
    return f"****{val[-4:]}"


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
async def linkedin_status(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        env_keys = read_env_file_keys()
        li_at = env_keys.get("LINKEDIN_LI_AT") or os.environ.get("LINKEDIN_LI_AT") or ""
        
        integrations_col = get_async_collection("integrations")
        doc = await integrations_col.find_one({"service": "linkedin", "userId": user_id})
        
        if not li_at or "EXPIRED" in li_at.upper() or (doc and doc.get("expired")):
            return {"connected": False, "expired": True, "status": "expired"}
            
        return {"connected": True, "expired": False, "status": "connected"}
    except Exception:
        return {"connected": False, "expired": True, "status": "expired"}


@router.post("/env-keys")
async def save_env_keys(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        updates = {}
        for k, new_val in payload.items():
            if new_val is None:
                continue
            new_val = str(new_val).strip()
            if "****" in new_val:
                continue
            updates[k] = new_val
            
        if updates:
            update_env_file(updates)
            
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
                    integrations_col = get_async_collection("integrations")
                    await integrations_col.update_one(
                        {"service": "linkedin", "userId": user_id},
                        {"$set": {"connected": True, "expired": False, "status": "connected", "li_at": v}},
                        upsert=True
                    )
                        
        return {"status": "success", "message": "API keys updated successfully."}
    except Exception as exc:
        raise HTTPException(500, f"Failed to save environment API keys: {exc}")
