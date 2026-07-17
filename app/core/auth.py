"""
app/core/auth.py
------------------
JWT authentication utilities for the OrbitAvanya FastAPI backend.

Provides:
  - create_access_token()  — sign a JWT
  - create_action_token()  — short-lived token for OTP-gated actions
  - verify_action_token()  — verify short-lived tokens
  - get_current_user()     — FastAPI dependency that decodes the Bearer token
  - require_admin()        — dependency that also checks the user is an admin
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from utils.db_client import get_collection
from config.settings import settings

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
        "exp": datetime.now(tz=timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_action_token(user_id: str, purpose: str) -> str:
    """Create a short-lived JWT to bridge an OTP verification to the next step."""
    payload = {
        "sub": str(user_id),
        "purpose": purpose,
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=ACTION_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_action_token(token: str, expected_purpose: str) -> Optional[str]:
    """Return user_id if the action token is valid for the expected purpose, else None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != expected_purpose:
            return None
        return payload.get("sub")
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """FastAPI dependency — decode Bearer token and return the user document."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated or token expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = None
    if credentials:
        token = credentials.credentials
    else:
        # Fallback to cookies
        token = request.cookies.get("orbitavanya_token")
        if not token:
            # Fallback to query param
            token = request.query_params.get("token")

    if not token:
        raise exc

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise exc
    except JWTError:
        raise exc

    users_col = get_collection("users")
    from bson import ObjectId
    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
    except Exception:
        raise exc

    if not user:
        raise exc
    return user


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency — only allows admin users through."""
    if current_user.get("role", "").lower() not in ("admin", "owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


def decode_and_get_user(token: str) -> Optional[dict]:
    """Helper to decode a JWT token and retrieve the user document. Useful for WebSockets."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub", "")
        if not user_id:
            return None
        from bson import ObjectId
        user = get_collection("users").find_one({"_id": ObjectId(user_id)})
        return user
    except Exception:
        return None
