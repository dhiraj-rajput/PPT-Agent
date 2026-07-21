"""
app/routes/auth.py
-------------------
Authentication routes for the OrbitAvanya FastAPI backend.

All routes mirror the Node.js server/routes/auth.js behaviour exactly
so the React frontend (which was written against that API) works unchanged.

Endpoints:
  POST /api/auth/register          — create pending user, send OTP
  POST /api/auth/login             — verify password, send OTP
  POST /api/auth/verify-otp        — verify OTP → JWT or action token
  POST /api/auth/forgot-password   — send reset OTP
  POST /api/auth/reset-password    — verify OTP + set new password
  PATCH /api/auth/change-password  — change password (authenticated)
  GET  /api/auth/me                — return current user from JWT
  POST /api/auth/logout            — stateless logout (client-side)
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Response, File, UploadFile
from fastapi.responses import FileResponse
import bcrypt
from pydantic import BaseModel

from app.core.auth import (
    create_access_token,
    create_action_token,
    get_current_user,
    verify_action_token,
)
from app.core.mailer import send_otp_email, send_invite_email
from utils.db_client import get_collection

from config.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_OTP_TTL_MINUTES = settings.OTP_TTL_MINUTES
_MAX_OTP_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _is_strong_password(pw: str) -> bool:
    return (
        len(pw) >= 8
        and bool(re.search(r"[A-Z]", pw))
        and bool(re.search(r"[a-z]", pw))
        and bool(re.search(r"\d", pw))
        and bool(re.search(r"[^A-Za-z0-9]", pw))
    )


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email))


def _is_valid_phone(phone: str) -> bool:
    digits = re.sub(r"[^\d]", "", phone)
    return bool(re.match(r"^[\d+\-\s()]+$", phone)) and 7 <= len(digits) <= 15


def _generate_otp() -> str:
    from config.settings import settings
    length = getattr(settings, "OTP_LENGTH", 6)
    if not isinstance(length, int) or length < 4 or length > 10:
        length = 6
    low = 10 ** (length - 1)
    high = 10 ** length - 1
    return str(secrets.randbelow(high - low + 1) + low)


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _otp_expiry() -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(minutes=_OTP_TTL_MINUTES)


def _to_public_user(u: Optional[dict]) -> dict:
    if not u:
        return {}
    return {
        "id": str(u["_id"]),
        "name": u.get("name", ""),
        "email": u.get("email", ""),
        "role": u.get("role", "Team Member"),
        "phone": u.get("phone", ""),
        "isVerified": u.get("isVerified", False),
        "mustChangePassword": u.get("mustChangePassword", False),
        "createdAt": u.get("createdAt", ""),
        "avatarUrl": u.get("avatarUrl", ""),
    }


async def _send_otp_for_user(user_id: str, email: str, purpose: str) -> None:
    """Generate, store, and email an OTP for the given purpose."""
    otps_col = get_collection("otps")
    otp = _generate_otp()
    otps_col.delete_many({"userId": str(user_id), "purpose": purpose})
    otps_col.insert_one({
        "userId": str(user_id),
        "purpose": purpose,
        "otpHash": _hash_otp(otp),
        "attempts": 0,
        "expiresAt": _otp_expiry(),
        "createdAt": datetime.now(tz=timezone.utc),
    })
    if settings.DEBUG_OTP:
        print(f"\n[DEVELOPMENT] Generated OTP for {email} ({purpose}): {otp}\n")
    import asyncio
    asyncio.create_task(send_otp_email(email, otp, purpose))


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RegisterBody(BaseModel):
    name: str
    email: str
    phone: str
    password: str
    confirmPassword: str


class LoginBody(BaseModel):
    email: str
    password: str


class VerifyOtpBody(BaseModel):
    email: str
    otp: str
    purpose: str  # "login" | "register" | "reset-password"


class ForgotPasswordBody(BaseModel):
    email: str


class ResetPasswordBody(BaseModel):
    actionToken: str
    newPassword: str
    confirmPassword: str


class ChangePasswordBody(BaseModel):
    currentPassword: str
    newPassword: str
    confirmPassword: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register(body: RegisterBody):
    if not all([body.name, body.email, body.phone, body.password, body.confirmPassword]):
        raise HTTPException(400, "Name, email, phone number, and password are required.")
    if not _is_valid_email(body.email):
        raise HTTPException(400, "Enter a valid email address.")
    if not _is_valid_phone(body.phone):
        raise HTTPException(400, "Enter a valid phone number.")
    if body.password != body.confirmPassword:
        raise HTTPException(400, "Passwords do not match.")
    if not _is_strong_password(body.password):
        raise HTTPException(
            400,
            "Password is too weak. Use at least 8 characters with uppercase, lowercase, a number, and a special character.",
        )

    users_col = get_collection("users")
    normalized = body.email.lower().strip()
    existing = users_col.find_one({"email": normalized})

    if existing and existing.get("isVerified"):
        raise HTTPException(409, "An account with this email already exists.")

    pw_hash = _hash_password(body.password)
    if existing:
        users_col.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "name": body.name.strip(),
                "phone": body.phone.strip(),
                "passwordHash": pw_hash,
                "isVerified": False,
                "updatedAt": datetime.now(tz=timezone.utc),
            }},
        )
        user_id = str(existing["_id"])
    else:
        result = users_col.insert_one({
            "name": body.name.strip(),
            "email": normalized,
            "phone": body.phone.strip(),
            "passwordHash": pw_hash,
            "isVerified": False,
            "role": "Team Member",
            "mustChangePassword": False,
            "createdAt": datetime.now(tz=timezone.utc),
        })
        user_id = str(result.inserted_id)

    await _send_otp_for_user(user_id, normalized, "register")
    return {"message": "OTP sent to your email. Please verify to complete registration."}


@router.post("/login")
async def login(body: LoginBody):
    if not body.email or not body.password:
        raise HTTPException(400, "Email and password are required.")

    normalized_email = body.email.lower().strip()
    login_failures_col = get_collection("login_failures")
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(minutes=15)

    failures_count = login_failures_col.count_documents({
        "email": normalized_email,
        "timestamp": {"$gte": cutoff}
    })
    if failures_count >= 5:
        raise HTTPException(429, "Too many failed login attempts. Please try again in 15 minutes.")

    users_col = get_collection("users")
    user = users_col.find_one({"email": normalized_email})
    if not user or not _verify_password(body.password, user.get("passwordHash", "")):
        login_failures_col.insert_one({
            "email": normalized_email,
            "timestamp": datetime.now(tz=timezone.utc),
            "createdAt": datetime.now(tz=timezone.utc)
        })
        raise HTTPException(401, "Incorrect email or password.")

    # Successful login — clear failure count
    login_failures_col.delete_many({"email": normalized_email})

    if not user.get("isVerified"):
        raise HTTPException(403, "Account not yet verified. Check your email for the verification OTP.")

    await _send_otp_for_user(str(user["_id"]), user["email"], "login")
    return {"requiresOtp": True, "message": "OTP sent to your email."}


@router.post("/verify-otp")
def verify_otp(body: VerifyOtpBody, response: Response):
    users_col = get_collection("users")
    otps_col = get_collection("otps")

    user = users_col.find_one({"email": body.email.lower().strip()})
    if not user:
        raise HTTPException(404, "No account found for this email.")

    user_id = str(user["_id"])
    otp_doc = otps_col.find_one({"userId": user_id, "purpose": body.purpose})

    if not otp_doc:
        raise HTTPException(400, "No OTP was requested. Please start over.")

    if otp_doc.get("attempts", 0) >= _MAX_OTP_ATTEMPTS:
        raise HTTPException(429, "Too many attempts. Please request a new code.")

    now = datetime.now(tz=timezone.utc)
    expires_at = otp_doc.get("expiresAt")
    if expires_at and (
        (expires_at.tzinfo and expires_at < now) or
        (not expires_at.tzinfo and expires_at < now.replace(tzinfo=None))
    ):
        raise HTTPException(400, "OTP has expired. Please request a new code.")

    otps_col.update_one({"_id": otp_doc["_id"]}, {"$inc": {"attempts": 1}})

    import hmac
    is_valid = hmac.compare_digest(otp_doc.get("otpHash", ""), _hash_otp(body.otp.strip()))
    if not is_valid:
        remaining = _MAX_OTP_ATTEMPTS - otp_doc.get("attempts", 0) - 1
        raise HTTPException(400, f"Incorrect OTP. {remaining} attempt(s) remaining.")

    # OTP is valid — clean it up
    otps_col.delete_one({"_id": otp_doc["_id"]})

    if body.purpose == "register":
        users_col.update_one({"_id": user["_id"]}, {"$set": {"isVerified": True}})
        token = create_access_token(user_id)
        updated_user = users_col.find_one({"_id": user["_id"]})
        response.set_cookie(
            key="orbitavanya_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
        )
        return {"token": token, "user": _to_public_user(updated_user)}

    if body.purpose == "login":
        if user.get("mustChangePassword"):
            action_token = create_action_token(user_id, "force-change-password")
            return {"mustChangePassword": True, "actionToken": action_token}
        token = create_access_token(user_id)
        response.set_cookie(
            key="orbitavanya_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
        )
        return {"token": token, "user": _to_public_user(user)}

    if body.purpose in ("reset-password", "change-password"):
        action_token = create_action_token(user_id, body.purpose)
        return {"actionToken": action_token}

    raise HTTPException(400, "Unknown OTP purpose.")


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordBody):
    if not body.email:
        raise HTTPException(400, "Email is required.")
    users_col = get_collection("users")
    user = users_col.find_one({"email": body.email.lower().strip()})
    # Always return success to avoid email enumeration
    if user and user.get("isVerified"):
        await _send_otp_for_user(str(user["_id"]), user["email"], "reset-password")
    return {"message": "If an account exists for this email, an OTP has been sent."}


@router.post("/reset-password")
def reset_password(body: ResetPasswordBody):
    if body.newPassword != body.confirmPassword:
        raise HTTPException(400, "Passwords do not match.")
    if not _is_strong_password(body.newPassword):
        raise HTTPException(
            400,
            "Password is too weak. Use at least 8 characters with uppercase, lowercase, a number, and a special character.",
        )
    user_id = verify_action_token(body.actionToken, "reset-password")
    if not user_id:
        raise HTTPException(400, "Invalid or expired action token. Please start over.")
    users_col = get_collection("users")
    users_col.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"passwordHash": _hash_password(body.newPassword), "mustChangePassword": False}},
    )
    return {"message": "Password reset successfully. You can now sign in."}


@router.patch("/change-password")
def change_password(
    body: ChangePasswordBody,
    current_user: dict = Depends(get_current_user),
):
    if not _verify_password(body.currentPassword, current_user.get("passwordHash", "")):
        raise HTTPException(400, "Current password is incorrect.")
    if body.newPassword != body.confirmPassword:
        raise HTTPException(400, "Passwords do not match.")
    if not _is_strong_password(body.newPassword):
        raise HTTPException(
            400,
            "Password is too weak. Use at least 8 characters with uppercase, lowercase, a number, and a special character.",
        )
    get_collection("users").update_one(
        {"_id": current_user["_id"]},
        {"$set": {"passwordHash": _hash_password(body.newPassword), "mustChangePassword": False}},
    )
    return {"message": "Password changed successfully."}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return {"user": _to_public_user(current_user)}


class UpdateProfileBody(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None


@router.patch("/me/profile")
def update_profile(
    body: UpdateProfileBody,
    current_user: dict = Depends(get_current_user),
):
    """Update the authenticated user's profile fields."""
    updates = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.phone is not None:
        updates["phone"] = body.phone.strip()
    if updates:
        get_collection("users").update_one({"_id": current_user["_id"]}, {"$set": updates})
    updated = get_collection("users").find_one({"_id": current_user["_id"]})
    return {"user": _to_public_user(updated)}


_AVATAR_DIR = "private/avatars"
_ALLOWED_AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
_MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload/replace the authenticated user's profile photo and assign it to their account."""
    from pathlib import Path
    import uuid

    content_type = (file.content_type or "").lower()
    ext = _ALLOWED_AVATAR_TYPES.get(content_type)
    if not ext:
        # Fall back to checking the filename extension if the content-type header is unreliable.
        suffix = Path(file.filename).suffix.lower() if file.filename else ""
        if suffix in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            ext = ".jpg" if suffix == ".jpeg" else suffix
        else:
            raise HTTPException(400, "Unsupported image type. Use JPG, PNG, GIF, or WEBP.")

    content = await file.read()
    if len(content) > _MAX_AVATAR_BYTES:
        raise HTTPException(400, "Image is too large. Max size is 5MB.")
    if not content:
        raise HTTPException(400, "Uploaded file is empty.")

    upload_dir = Path(_AVATAR_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Remove any previous avatar file(s) for this user before saving the new one.
    user_id = str(current_user["_id"])
    for old_file in upload_dir.glob(f"{user_id}_*"):
        try:
            old_file.unlink()
        except OSError:
            pass

    unique_name = f"{user_id}_{uuid.uuid4().hex}{ext}"
    dest_path = upload_dir / unique_name
    with open(dest_path, "wb") as f:
        f.write(content)

    get_collection("users").update_one(
        {"_id": current_user["_id"]},
        {"$set": {"avatarUrl": unique_name, "updatedAt": datetime.now(tz=timezone.utc)}},
    )
    updated = get_collection("users").find_one({"_id": current_user["_id"]})
    return {"user": _to_public_user(updated)}


@router.get("/avatar/{filename}")
def serve_avatar(filename: str):
    """Serve an uploaded profile photo by filename."""
    from pathlib import Path

    safe_filename = Path(filename).name  # strip any path components to prevent traversal
    avatar_path = Path(_AVATAR_DIR) / safe_filename
    if not avatar_path.exists():
        raise HTTPException(status_code=404, detail="Avatar not found")

    content_type = "image/jpeg"
    lower_name = safe_filename.lower()
    if lower_name.endswith(".png"):
        content_type = "image/png"
    elif lower_name.endswith(".gif"):
        content_type = "image/gif"
    elif lower_name.endswith(".webp"):
        content_type = "image/webp"

    return FileResponse(avatar_path, media_type=content_type)


@router.post("/logout")
def logout():
    # JWT is stateless; client clears the token
    return {"ok": True}
