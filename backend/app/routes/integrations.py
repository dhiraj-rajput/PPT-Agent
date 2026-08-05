"""
app/routes/integrations.py
---------------------------
Integration settings endpoints — using MySQL.
"""

from __future__ import annotations

import os
import logging
from typing import Optional
try:
    from filelock import FileLock as _FileLock
    _ENV_LOCK = _FileLock(".env.lock", timeout=10)
except ImportError:
    import contextlib
    _FileLock = None  # type: ignore
    _ENV_LOCK = contextlib.nullcontext()  # type: ignore

logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request

from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import get_db_session, _mysql_available
from utils.encryption import encrypt_data, decrypt_data
from config.settings import settings
from models.sql_models import (
    Integration as SQL_Integration,
    OAuthState as SQL_OAuthState,
)
from sqlalchemy import select, insert, update, delete

router = APIRouter(prefix="/integrations", tags=["integrations"])

_CLIENT_URL = settings.CLIENT_URL


def _google_config() -> tuple[str, str, str]:
    """Read the current Google OAuth client id/secret/redirect URI, preferring
    live env vars (updated by /env-keys) over whatever was loaded at boot."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID") or getattr(settings, "GOOGLE_CLIENT_ID", "") or ""
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or getattr(settings, "GOOGLE_CLIENT_SECRET", "") or ""
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI") or getattr(settings, "GOOGLE_REDIRECT_URI", "") or ""
    return client_id, client_secret, redirect_uri


def _is_google_client_id_configured(client_id: str) -> bool:
    """Check if GOOGLE_CLIENT_ID is configured and not an empty placeholder."""
    if not client_id or "your_" in client_id.lower() or "placeholder" in client_id.lower():
        return False
    if not client_id.endswith(".apps.googleusercontent.com"):
        return False
    return len(client_id) >= 20


async def _get_google_auth_url_async(user_id: str) -> str:
    _GOOGLE_CLIENT_ID, _GOOGLE_CLIENT_SECRET, _GOOGLE_REDIRECT_URI = _google_config()
    if not _is_google_client_id_configured(_GOOGLE_CLIENT_ID):
        raise HTTPException(
            status_code=400,
            detail="Google OAuth is not configured. Please set a valid GOOGLE_CLIENT_ID in settings."
        )
    from google_auth_oauthlib.flow import Flow
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
    
    if _mysql_available:
        try:
            async for db in get_db_session():
                db.add(SQL_OAuthState(
                    state=state_token,
                    service="google",
                    user_id=int(user_id),
                    code_verifier=getattr(flow, "code_verifier", ""),
                    expires_at=datetime.utcnow() + timedelta(minutes=10),
                    created_at=datetime.utcnow()
                ))
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to save Google OAuth state in MySQL: {e}")
            raise HTTPException(500, "Database error saving OAuth state.")
    
    return auth_url


async def _handle_google_callback_async(code: str, state: Optional[str] = None) -> None:
    _GOOGLE_CLIENT_ID, _GOOGLE_CLIENT_SECRET, _GOOGLE_REDIRECT_URI = _google_config()
    if not _is_google_client_id_configured(_GOOGLE_CLIENT_ID):
        raise HTTPException(400, "Google OAuth is not configured.")
        
    user_id_clean = "global"
    code_verifier = None
    if state and _mysql_available:
        async for db in get_db_session():
            stmt = select(SQL_OAuthState).where(SQL_OAuthState.state == state)
            state_doc = (await db.execute(stmt)).scalar_one_or_none()
            if not state_doc:
                raise HTTPException(400, "Invalid or expired OAuth state parameter.")
            user_id_clean = str(state_doc.user_id) if state_doc.user_id is not None else "global"
            code_verifier = state_doc.code_verifier

            # Delete the state token
            await db.execute(delete(SQL_OAuthState).where(SQL_OAuthState.state == state))
            await db.commit()
        
    from google_auth_oauthlib.flow import Flow

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

    if _mysql_available and user_id_clean != "global":
        uid = int(user_id_clean)
        async for db in get_db_session():
            stmt_int = select(SQL_Integration).where(SQL_Integration.service == "google", SQL_Integration.user_id == uid)
            existing = (await db.execute(stmt_int)).scalar_one_or_none()
            if existing:
                await db.execute(
                    update(SQL_Integration)
                    .where(SQL_Integration.id == existing.id)
                    .values(
                        connected=True,
                        refresh_token=creds.refresh_token or existing.refresh_token,
                        access_token=creds.token,
                        token_expiry=creds.expiry,
                        updated_at=datetime.utcnow()
                    )
                )
            else:
                db.add(SQL_Integration(
                    user_id=uid,
                    service="google",
                    connected=True,
                    refresh_token=creds.refresh_token or "",
                    access_token=creds.token or "",
                    token_expiry=creds.expiry,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                ))
            await db.commit()


async def _get_google_connection_status_async(user_id: str) -> dict:
    if _mysql_available:
        try:
            uid = int(user_id)
            async for db in get_db_session():
                stmt = select(SQL_Integration).where(SQL_Integration.service == "google", SQL_Integration.user_id == uid)
                doc = (await db.execute(stmt)).scalar_one_or_none()
                return {"connected": bool(doc and doc.connected)}
        except Exception:
            pass
    return {"connected": False}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/google/status")
async def google_status(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["id"])
        return await _get_google_connection_status_async(user_id)
    except Exception as exc:
        raise HTTPException(500, f"Could not check Google connection status: {exc}")


@router.delete("/google")
async def disconnect_google(current_user: dict = Depends(get_current_user)):
    try:
        user_id = int(current_user["id"])
        if _mysql_available:
            async for db in get_db_session():
                await db.execute(delete(SQL_Integration).where(SQL_Integration.service == "google", SQL_Integration.user_id == user_id))
                await db.commit()
        return {"success": True, "message": "Google Meet integration disconnected."}
    except Exception as exc:
        raise HTTPException(500, f"Could not disconnect Google integration: {exc}")


@router.get("/google/auth-url")
async def google_auth_url(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["id"])
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
        user_id = int(current_user["id"])
        raw_key = ""
        if _mysql_available:
            async for db in get_db_session():
                stmt = select(SQL_Integration).where(SQL_Integration.service == "sam", SQL_Integration.user_id == user_id)
                doc = (await db.execute(stmt)).scalar_one_or_none()
                if doc and getattr(doc, "connected", False):
                    token = str(doc.access_token or "")
                    try:
                        raw_key = decrypt_data(token)
                    except Exception:
                        raw_key = token

        if not raw_key:
            env_keys = read_env_file_keys()
            raw_key = env_keys.get("SAM_GOV_API_KEY") or os.environ.get("SAM_GOV_API_KEY") or getattr(settings, "SAM_GOV_API_KEY", "") or ""
            
        r_str = str(raw_key or "")
        if r_str and not r_str.startswith("your_") and len(r_str) > 5:
            obfuscated = f"****{r_str[-4:]}" if len(r_str) >= 4 else "****"
            return {"connected": True, "apiKey": obfuscated}

        return {"connected": False, "apiKey": ""}
    except Exception as exc:
        raise HTTPException(500, f"Could not check SAM.gov connection status: {exc}")


@router.post("/sam/connect")
async def sam_connect(payload: SamApiKeyPayload, current_user: dict = Depends(get_current_user)):
    try:
        user_id = int(current_user["id"])
        api_key = payload.api_key.strip()
        if not api_key:
            raise HTTPException(400, "API key cannot be empty.")
            
        encrypted_key = encrypt_data(api_key)

        if _mysql_available:
            async for db in get_db_session():
                stmt = select(SQL_Integration).where(SQL_Integration.service == "sam", SQL_Integration.user_id == user_id)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if existing:
                    await db.execute(
                        update(SQL_Integration)
                        .where(SQL_Integration.id == existing.id)
                        .values(connected=True, access_token=encrypted_key, updated_at=datetime.utcnow())
                    )
                else:
                    db.add(SQL_Integration(
                        user_id=user_id,
                        service="sam",
                        connected=True,
                        access_token=encrypted_key,
                        refresh_token="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    ))
                await db.commit()
        
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
        user_id = int(current_user["id"])
        if _mysql_available:
            async for db in get_db_session():
                await db.execute(delete(SQL_Integration).where(SQL_Integration.service == "sam", SQL_Integration.user_id == user_id))
                await db.commit()
        return {"success": True, "message": "SAM.gov API Key disconnected."}
    except Exception as exc:
        raise HTTPException(500, f"Could not disconnect SAM.gov: {exc}")


# ---------------------------------------------------------------------------
# Companies House (UK) API Key Integration
# ---------------------------------------------------------------------------

class CompaniesHouseApiKeyPayload(BaseModel):
    api_key: str


@router.get("/companies-house/status")
async def companies_house_status(current_user: dict = Depends(get_current_user)):
    try:
        user_id = int(current_user["id"])
        raw_key = ""
        if _mysql_available:
            async for db in get_db_session():
                stmt = select(SQL_Integration).where(SQL_Integration.service == "companies_house", SQL_Integration.user_id == user_id)
                doc = (await db.execute(stmt)).scalar_one_or_none()
                if doc and getattr(doc, "connected", False):
                    token = str(doc.access_token or "")
                    try:
                        raw_key = decrypt_data(token)
                    except Exception:
                        raw_key = token

        if not raw_key:
            env_keys = read_env_file_keys()
            raw_key = env_keys.get("COMPANIES_HOUSE_KEY") or os.environ.get("COMPANIES_HOUSE_KEY") or getattr(settings, "COMPANIES_HOUSE_KEY", "") or ""

        r_str = str(raw_key or "")
        if r_str and len(r_str) > 5:
            obfuscated = f"****{r_str[-4:]}" if len(r_str) >= 4 else "****"
            return {"connected": True, "apiKey": obfuscated}

        return {"connected": False, "apiKey": ""}
    except Exception as exc:
        raise HTTPException(500, f"Could not check Companies House connection status: {exc}")


@router.post("/companies-house/connect")
async def companies_house_connect(payload: CompaniesHouseApiKeyPayload, current_user: dict = Depends(get_current_user)):
    try:
        user_id = int(current_user["id"])
        api_key = payload.api_key.strip()
        if not api_key:
            raise HTTPException(400, "API key cannot be empty.")

        encrypted_key = encrypt_data(api_key)

        if _mysql_available:
            async for db in get_db_session():
                stmt = select(SQL_Integration).where(SQL_Integration.service == "companies_house", SQL_Integration.user_id == user_id)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if existing:
                    await db.execute(
                        update(SQL_Integration)
                        .where(SQL_Integration.id == existing.id)
                        .values(connected=True, access_token=encrypted_key, updated_at=datetime.utcnow())
                    )
                else:
                    db.add(SQL_Integration(
                        user_id=user_id,
                        service="companies_house",
                        connected=True,
                        access_token=encrypted_key,
                        refresh_token="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    ))
                await db.commit()

        update_env_file({"COMPANIES_HOUSE_KEY": api_key})
        os.environ["COMPANIES_HOUSE_KEY"] = api_key

        return {"success": True, "message": "Companies House API Key saved successfully."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Could not save Companies House API Key: {exc}")


@router.delete("/companies-house")
async def companies_house_disconnect(current_user: dict = Depends(get_current_user)):
    try:
        user_id = int(current_user["id"])
        if _mysql_available:
            async for db in get_db_session():
                await db.execute(delete(SQL_Integration).where(SQL_Integration.service == "companies_house", SQL_Integration.user_id == user_id))
                await db.commit()
        return {"success": True, "message": "Companies House API Key disconnected."}
    except Exception as exc:
        raise HTTPException(500, f"Could not disconnect Companies House: {exc}")



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
    """Write updates to .env file. Protected by a cross-process file lock to
    prevent concurrent writes from corrupting the file."""
    env_path = ".env"
    with _ENV_LOCK:
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
    return key.endswith(_SECRET_KEY_SUFFIXES) or key in ("LINKEDIN_LI_AT", "BROWSERLESS_CDP_URL")


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
    "BROWSERLESS_CDP_URL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASS",
    "SMTP_FROM",
]


@router.get("/env-keys")
def get_env_keys(current_user: dict = Depends(get_current_user)):
    # Only Admins and Owners may view API keys
    user_role = (current_user.get("role") or "").strip().lower()
    if user_role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Only Admin or Owner users can view API keys.")
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
        user_id = int(current_user["id"])
        env_keys = read_env_file_keys()
        li_at = env_keys.get("LINKEDIN_LI_AT") or os.environ.get("LINKEDIN_LI_AT") or ""
        
        expired = True
        connected = False
        if _mysql_available:
            async for db in get_db_session():
                stmt = select(SQL_Integration).where(SQL_Integration.service == "linkedin", SQL_Integration.user_id == user_id)
                doc = (await db.execute(stmt)).scalar_one_or_none()
                if doc:
                    expired = bool(doc.extra_data.get("expired", True))
                    connected = bool(doc.connected)
        
        if not li_at or "EXPIRED" in li_at.upper() or expired:
            return {"connected": False, "expired": True, "status": "expired"}
            
        return {"connected": connected, "expired": False, "status": "connected"}
    except Exception:
        return {"connected": False, "expired": True, "status": "expired"}


@router.post("/env-keys")
async def save_env_keys(payload: dict, current_user: dict = Depends(get_current_user)):
    # Only Admins and Owners may modify API keys / environment variables
    user_role = (current_user.get("role") or "").strip().lower()
    if user_role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Only Admin or Owner users can update API keys.")
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
                
                if k == "LINKEDIN_LI_AT" and v and _mysql_available:
                    user_id = int(current_user["id"])
                    async for db in get_db_session():
                        stmt = select(SQL_Integration).where(SQL_Integration.service == "linkedin", SQL_Integration.user_id == user_id)
                        existing = (await db.execute(stmt)).scalar_one_or_none()
                        if existing:
                            await db.execute(
                                update(SQL_Integration)
                                .where(SQL_Integration.id == existing.id)
                                .values(connected=True, extra_data={"expired": False, "status": "connected", "li_at": v}, updated_at=datetime.utcnow())
                            )
                        else:
                            db.add(SQL_Integration(
                                user_id=user_id,
                                service="linkedin",
                                connected=True,
                                access_token=v,
                                refresh_token="",
                                extra_data={"expired": False, "status": "connected", "li_at": v},
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            ))
                        await db.commit()
                        
        return {"status": "success", "message": "API keys updated successfully."}
    except Exception as exc:
        raise HTTPException(500, f"Failed to save environment API keys: {exc}")
