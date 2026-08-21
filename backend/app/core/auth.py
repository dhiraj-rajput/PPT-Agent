"""
app/core/auth.py
------------------
JWT authentication utilities for the OrbitAvanya FastAPI backend.

Provides:
  - create_access_token()     — sign a JWT
  - create_action_token()     — short-lived token for OTP-gated actions
  - verify_action_token()     — verify short-lived tokens
  - get_current_user()        — FastAPI dependency that decodes the Bearer token (async Motor)
  - require_admin()           — dependency that also checks the user is an admin
  - decode_and_get_user_async() — async helper for WebSockets / async contexts
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config.settings import settings
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from models.sql_models import User
from sqlalchemy import select
from utils.db_client import _mysql_available, get_db_session, get_sync_db_session

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
if not settings.JWT_SECRET or settings.JWT_SECRET == "changeme-use-a-strong-random-secret":
    raise RuntimeError("CRITICAL: JWT_SECRET environment variable is not configured or is set to a weak fallback value.")

SECRET_KEY: str = settings.JWT_SECRET
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS: int = settings.JWT_EXPIRES_DAYS
ACTION_TOKEN_EXPIRE_MINUTES: int = 10

_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def create_access_token(user_id: str) -> str:
    """Create a long-lived JWT for the authenticated session."""
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": datetime.now(tz=timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_action_token(user_id: str, purpose: str) -> str:
    """Create a short-lived JWT to bridge an OTP verification to the next step."""
    payload = {
        "sub": str(user_id),
        "type": "action",
        "purpose": purpose,
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=ACTION_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_action_token(token: str, expected_purpose: str) -> str | None:
    """Return user_id if the action token is valid for the expected purpose, else None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != expected_purpose or payload.get("type") != "action":
            return None
        return payload.get("sub")
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def _sql_user_to_dict(u) -> dict:
    if not u:
        return {}
    return {
        "id": str(u.id),
        "_id": str(u.id),
        "name": u.name or "",
        "email": u.email or "",
        "phone": u.phone or "",
        "role": u.role or "Team Member",
        "isVerified": bool(u.is_verified),
        "mustChangePassword": bool(u.must_change_password),
        "createdAt": u.created_at if u.created_at else datetime.now(timezone.utc),
        "avatarUrl": u.avatar_url or "",
    }



async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """FastAPI dependency — decode Bearer token or cookie and return the user document using MySQL."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated or token expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = None
    if credentials:
        token = credentials.credentials
    else:
        # Fallback to HttpOnly cookie only (security hardening: query param token removed)
        token = request.cookies.get("orbitavanya_token")

    if not token:
        raise exc

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub", "")
        # Prevent action tokens (e.g. OTP/reset) from authenticating as access tokens
        if not user_id or payload.get("type") == "action" or payload.get("purpose") is not None:
            raise exc
    except JWTError:
        raise exc

    if _mysql_available:
        try:
            async for db in get_db_session():
                try:
                    uid = int(user_id)
                    stmt = select(User).where(User.id == uid)
                    res = await db.execute(stmt)
                    user_row = res.scalar_one_or_none()
                    if user_row:
                        if hasattr(user_row, "is_active") and user_row.is_active is False:
                            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")
                        return _sql_user_to_dict(user_row)
                except ValueError:
                    pass
        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.getLogger("auth").error(f"MySQL get_current_user error: {e}")

    raise exc


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency — only allows admin users through."""
    if current_user.get("role", "").lower() not in ("admin", "owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


async def decode_and_get_user_async(token: str) -> dict | None:
    """Async helper to decode a JWT token and retrieve the user document. Useful for WebSockets/async contexts."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub", "")
        if not user_id:
            return None

        # MySQL only
        if _mysql_available:
            async for db in get_db_session():
                try:
                    uid = int(user_id)
                    stmt = select(User).where(User.id == uid)
                    res = await db.execute(stmt)
                    user_row = res.scalar_one_or_none()
                    if user_row:
                        return _sql_user_to_dict(user_row)
                except ValueError:
                    pass
                # Try email match if payload has it
                email = payload.get("email")
                if email:
                    stmt = select(User).where(User.email == email.lower().strip())
                    res = await db.execute(stmt)
                    user_row = res.scalar_one_or_none()
                    if user_row:
                        return _sql_user_to_dict(user_row)
        return None
    except Exception as e:
        import logging
        logging.getLogger("auth").error(f"WebSocket authentication decode failed: {e}")
        return None


def decode_and_get_user(token: str) -> dict | None:
    """Sync helper to decode a JWT token and retrieve the user document."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub", "")
        if not user_id:
            return None

        # MySQL only
        if _mysql_available:
            with get_sync_db_session() as db:
                try:
                    uid = int(user_id)
                    stmt = select(User).where(User.id == uid)
                    user_row = db.execute(stmt).scalar_one_or_none()
                    if user_row:
                        return _sql_user_to_dict(user_row)
                except ValueError:
                    pass
                email = payload.get("email")
                if email:
                    stmt = select(User).where(User.email == email.lower().strip())
                    user_row = db.execute(stmt).scalar_one_or_none()
                    if user_row:
                        return _sql_user_to_dict(user_row)
        return None
    except Exception as e:
        import logging
        logging.getLogger("auth").error(f"Sync authentication decode failed: {e}")
        return None


