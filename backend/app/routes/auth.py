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

import asyncio
import hashlib
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
from utils.db_client import get_async_collection, get_db_session, _mysql_available
from models.sql_models import User as SQLUser, OTP as SQLOTP, LoginFailure as SQLLoginFailure
from sqlalchemy import select, insert, update, delete, func

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
    length = getattr(settings, "OTP_LENGTH", 6)
    if not isinstance(length, int) or length < 4 or length > 10:
        length = 6
    digits = [str(secrets.randbelow(10)) for _ in range(length)]
    return "".join(digits)


def _sql_user_to_dict(u: SQLUser) -> dict:
    if not u:
        return {}
    return {
        "id": str(u.id),
        "_id": str(u.id),
        "name": u.name or "",
        "email": u.email or "",
        "phone": u.phone or "",
        # passwordHash intentionally excluded — use get_current_user dependency
        # only for internal auth comparisons, never expose in API responses
        "isVerified": getattr(u, "is_verified", True),
        "role": u.role or "Team Member",
        "avatar": getattr(u, "avatar", "") or "",
        "bio": getattr(u, "bio", "") or "",
        "company": getattr(u, "company", "") or "",
        "location": getattr(u, "location", "") or "",
        "website": getattr(u, "website", "") or "",
        "github": getattr(u, "github", "") or "",
        "linkedin": getattr(u, "linkedin", "") or "",
        "twitter": getattr(u, "twitter", "") or "",
        "mustChangePassword": getattr(u, "must_change_password", False),
        "createdAt": u.created_at.isoformat() if getattr(u, "created_at", None) else "",
        "updatedAt": u.updated_at.isoformat() if getattr(u, "updated_at", None) else "",
    }

def _get_password_hash_for_auth(user_row: SQLUser) -> str:
    """Return the raw bcrypt hash for internal-only password verification.
    Never include this in any dict returned to the client."""
    return str(user_row.password_hash or "")



def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _otp_expiry() -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(minutes=_OTP_TTL_MINUTES)


def _to_public_user(u: Optional[dict]) -> dict:
    if not u:
        return {}
    uid = u.get("_id") or u.get("id")
    return {
        "id": str(uid) if uid is not None else "",
        "name": u.get("name", ""),
        "email": u.get("email", ""),
        "role": u.get("role", "Team Member"),
        "phone": u.get("phone", ""),
        "isVerified": u.get("isVerified", False) or u.get("is_verified", False),
        "mustChangePassword": u.get("mustChangePassword", False) or u.get("must_change_password", False),
        "createdAt": str(u.get("createdAt") or u.get("created_at") or ""),
        "avatarUrl": u.get("avatarUrl", "") or u.get("avatar_url", ""),
    }


async def _send_otp_for_user(user_id: str, email: str, purpose: str) -> None:
    """Generate, store, and email an OTP for the given purpose using MySQL primary or Mongo fallback."""
    otp = _generate_otp()
    if _mysql_available:
        try:
            async for db in get_db_session():
                # Core delete
                await db.execute(delete(SQLOTP).where(SQLOTP.user_id == str(user_id), SQLOTP.purpose == purpose))
                # Core insert
                await db.execute(insert(SQLOTP).values(
                    user_id=str(user_id),
                    purpose=purpose,
                    otp_hash=_hash_otp(otp),
                    attempts=0,
                    expires_at=_otp_expiry(),
                    created_at=datetime.now(timezone.utc)
                ))
                await db.commit()
            import logging as _logging
            _logging.getLogger("auth").info("🔑 [DEV OTP] Generated OTP for %s (%s): %s", email, purpose, otp)
            print(f"\n🔑 [DEV OTP CODE] {email} ({purpose}): {otp}\n", flush=True)
            asyncio.create_task(send_otp_email(email, otp, purpose))
            return
        except Exception as e:
            import logging
            logging.getLogger("auth").warning(f"MySQL OTP save failed, trying Mongo fallback: {e}")

    # Fallback to MongoDB
    otps_col = get_async_collection("otps")
    await otps_col.delete_many({"userId": str(user_id), "purpose": purpose})
    await otps_col.insert_one({
        "userId": str(user_id),
        "purpose": purpose,
        "otpHash": _hash_otp(otp),
        "attempts": 0,
        "expiresAt": _otp_expiry(),
        "createdAt": datetime.now(tz=timezone.utc),
    })
    import logging as _logging
    _logging.getLogger("auth").info("🔑 [DEV OTP] Generated OTP for %s (%s): %s", email, purpose, otp)
    print(f"\n🔑 [DEV OTP CODE] {email} ({purpose}): {otp}\n", flush=True)
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

    normalized = body.email.lower().strip()
    existing_sql = None
    existing_mongo = None

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQLUser).where(SQLUser.email == normalized)
                res = await db.execute(stmt)
                existing_sql = res.scalar_one_or_none()
        except Exception as e:
            import logging
            logging.getLogger("auth").warning(f"MySQL check in register failed: {e}")

    # Check MongoDB
    users_col = get_async_collection("users")
    existing_mongo = await users_col.find_one({"email": normalized})

    is_v = getattr(existing_sql, "is_verified", False) if existing_sql else False
    if is_v or (existing_mongo and existing_mongo.get("isVerified")):
        raise HTTPException(409, "An account with this email already exists.")


    pw_hash = await asyncio.to_thread(_hash_password, body.password)
    user_id = None

    if existing_sql:
        # Update MySQL
        async for db in get_db_session():
            await db.execute(
                update(SQLUser)
                .where(SQLUser.id == existing_sql.id)
                .values(
                    name=body.name.strip(),
                    phone=body.phone.strip(),
                    password_hash=pw_hash,
                    is_verified=False,
                    updated_at=datetime.now(timezone.utc)
                )
            )
            await db.commit()
        user_id = str(existing_sql.id)
    elif existing_mongo:
        # Update MongoDB
        await users_col.update_one(
            {"_id": existing_mongo["_id"]},
            {"$set": {
                "name": body.name.strip(),
                "phone": body.phone.strip(),
                "passwordHash": pw_hash,
                "isVerified": False,
                "updatedAt": datetime.now(tz=timezone.utc),
            }},
        )
        user_id = str(existing_mongo["_id"])
    else:
        # Insert new
        if _mysql_available:
            try:
                async for db in get_db_session():
                    stmt = insert(SQLUser).values(
                        name=body.name.strip(),
                        email=normalized,
                        phone=body.phone.strip(),
                        password_hash=pw_hash,
                        is_verified=False,
                        role="Team Member",
                        must_change_password=False,
                        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                        updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
                    )
                    await db.execute(stmt)
                    await db.commit()

                    new_u = (await db.execute(select(SQLUser).where(SQLUser.email == normalized))).scalar_one()
                    user_id = str(new_u.id)

            except Exception as e:
                import logging
                logging.getLogger("auth").warning(f"MySQL insert in register failed, falling back to Mongo: {e}")

        if not user_id:
            # Fallback to MongoDB
            result = await users_col.insert_one({
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
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(minutes=15)

    max_attempts = getattr(settings, "LOGIN_MAX_ATTEMPTS", 10)
    user = None

    if _mysql_available:
        try:
            async for db in get_db_session():
                # Count login failures
                stmt_count = select(func.count()).select_from(SQLLoginFailure).where(
                    SQLLoginFailure.email == normalized_email,
                    SQLLoginFailure.timestamp >= cutoff
                )
                failures_count = (await db.execute(stmt_count)).scalar() or 0
                if failures_count >= max_attempts:
                    raise HTTPException(429, "Too many failed login attempts. Please try again in 15 minutes.")

                # Find user
                stmt_user = select(SQLUser).where(SQLUser.email == normalized_email)
                res = await db.execute(stmt_user)
                user_row = res.scalar_one_or_none()
                if user_row:
                    user = _sql_user_to_dict(user_row)
        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.getLogger("auth").error(f"MySQL error during login checks: {e}")
            raise HTTPException(500, "Database error during login.")

    if not user:
        # Constant-time response to prevent email enumeration via timing
        import bcrypt
        await asyncio.to_thread(
            bcrypt.checkpw,
            body.password.encode('utf-8'),
            b'$2b$12$notavalidhashXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'
        )
        # Record failure and raise unauthorized
        if _mysql_available:
            try:
                async for db in get_db_session():
                    await db.execute(insert(SQLLoginFailure).values(
                        email=normalized_email,
                        timestamp=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc)
                    ))
                    await db.commit()
            except Exception:
                pass
        raise HTTPException(401, "Incorrect email or password.")

    # Re-fetch the hash directly from the DB row rather than storing it in the
    # user dict, which is returned to the client and must not contain the hash.
    _pw_hash_for_check = ""
    if _mysql_available:
        try:
            async for db in get_db_session():
                _row = (await db.execute(select(SQLUser).where(SQLUser.email == normalized_email))).scalar_one_or_none()
                if _row:
                    _pw_hash_for_check = _get_password_hash_for_auth(_row)
        except Exception:
            pass
    is_valid_pw = await asyncio.to_thread(_verify_password, body.password, _pw_hash_for_check)
    if not is_valid_pw:
        if _mysql_available:
            try:
                async for db in get_db_session():
                    await db.execute(insert(SQLLoginFailure).values(
                        email=normalized_email,
                        timestamp=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc)
                    ))
                    await db.commit()
            except Exception:
                pass
        raise HTTPException(401, "Incorrect email or password.")

    # Successful login — clear failure count
    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(delete(SQLLoginFailure).where(SQLLoginFailure.email == normalized_email))
                await db.commit()
        except Exception:
            pass

    if not user.get("isVerified"):
        raise HTTPException(403, "Account not yet verified. Check your email for the verification OTP.")

    await _send_otp_for_user(user["id"], user["email"], "login")
    return {"requiresOtp": True, "message": "OTP sent to your email."}



@router.post("/verify-otp")
async def verify_otp(body: VerifyOtpBody, response: Response):
    user = None
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQLUser).where(SQLUser.email == body.email.lower().strip())
                res = await db.execute(stmt)
                user_row = res.scalar_one_or_none()
                if user_row:
                    user = _sql_user_to_dict(user_row)
        except Exception as e:
            import logging
            logging.getLogger("auth").error(f"MySQL error during verify-otp: {e}")

    if not user:
        raise HTTPException(404, "No account found for this email.")

    user_id = user["id"]
    otp_doc = None

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQLOTP).where(SQLOTP.user_id == user_id, SQLOTP.purpose == body.purpose)
                res = await db.execute(stmt)
                otp_row = res.scalar_one_or_none()
                if otp_row:
                    otp_doc = {
                        "id": otp_row.id,
                        "userId": otp_row.user_id,
                        "purpose": otp_row.purpose,
                        "otpHash": otp_row.otp_hash,
                        "attempts": otp_row.attempts,
                        "expiresAt": otp_row.expires_at,
                        "createdAt": otp_row.created_at
                    }
        except Exception:
            pass

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

    # Validate OTP FIRST, only increment counter on failure
    import hmac
    is_valid = hmac.compare_digest(otp_doc.get("otpHash", ""), _hash_otp(body.otp.strip()))
    if not is_valid:
        # Only increment attempts counter when the OTP was wrong
        attempts = otp_doc.get("attempts", 0) + 1
        if _mysql_available:
            try:
                async for db in get_db_session():
                    await db.execute(
                        update(SQLOTP)
                        .where(SQLOTP.id == otp_doc["id"])
                        .values(attempts=attempts)
                    )
                    await db.commit()
            except Exception:
                pass
        remaining = _MAX_OTP_ATTEMPTS - attempts
        raise HTTPException(400, f"Incorrect OTP. {remaining} attempt(s) remaining.")

    # OTP is valid — clean it up
    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(delete(SQLOTP).where(SQLOTP.id == otp_doc["id"]))
                await db.commit()
        except Exception:
            pass

    if body.purpose == "register":
        updated_user = user
        if _mysql_available:
            try:
                async for db in get_db_session():
                    await db.execute(
                        update(SQLUser)
                        .where(SQLUser.id == int(user_id))
                        .values(is_verified=True)
                    )
                    await db.commit()
                    stmt = select(SQLUser).where(SQLUser.id == int(user_id))
                    res = await db.execute(stmt)
                    updated_user = _sql_user_to_dict(res.scalar_one())
            except Exception as e:
                raise HTTPException(500, f"Verification failed: {e}")

        token = create_access_token(user_id)
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
        token = create_access_token(user_id)
        response.set_cookie(
            key="orbitavanya_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
        )
        return {
            "token": token,
            "user": _to_public_user(user),
            "mustChangePassword": bool(user.get("mustChangePassword")),
        }

    if body.purpose in ("reset-password", "change-password"):
        action_token = create_action_token(user_id, body.purpose)
        return {"actionToken": action_token}

    raise HTTPException(400, "Unknown OTP purpose.")



class ForceChangePasswordBody(BaseModel):
    newPassword: str
    confirmPassword: str


@router.post("/force-change-password")
async def force_change_password(
    body: ForceChangePasswordBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.newPassword or not body.confirmPassword:
        raise HTTPException(400, "New password and confirm password are required.")
    if body.newPassword != body.confirmPassword:
        raise HTTPException(400, "Passwords do not match.")
    if not _is_strong_password(body.newPassword):
        raise HTTPException(
            400,
            "Password is too weak. Use at least 8 characters with uppercase, lowercase, a number, and a special character.",
        )
    pw_hash = await asyncio.to_thread(_hash_password, body.newPassword)
    uid = int(current_user["id"])
    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(
                    update(SQLUser)
                    .where(SQLUser.id == uid)
                    .values(password_hash=pw_hash, must_change_password=False, updated_at=datetime.now(timezone.utc))
                )
                await db.commit()
                stmt = select(SQLUser).where(SQLUser.id == uid)
                res = await db.execute(stmt)
                updated = _sql_user_to_dict(res.scalar_one())
                return {"message": "Password updated successfully.", "user": _to_public_user(updated)}
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "MySQL unavailable")


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordBody):
    if not body.email:
        raise HTTPException(400, "Email is required.")
    
    normalized_email = body.email.lower().strip()
    user = None
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQLUser).where(SQLUser.email == normalized_email)
                res = await db.execute(stmt)
                user_row = res.scalar_one_or_none()
                if user_row:
                    user = _sql_user_to_dict(user_row)
        except Exception:
            pass

    # Always return success to avoid email enumeration
    if user and user.get("isVerified"):
        await _send_otp_for_user(user["id"], user["email"], "reset-password")
    return {"message": "If an account exists for this email, an OTP has been sent."}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordBody):
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
    
    pw_hash = await asyncio.to_thread(_hash_password, body.newPassword)
    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(
                    update(SQLUser)
                    .where(SQLUser.id == int(user_id))
                    .values(password_hash=pw_hash, must_change_password=False, updated_at=datetime.now(timezone.utc))
                )
                await db.commit()
            return {"message": "Password reset successfully. You can now sign in."}
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "MySQL unavailable")


@router.patch("/change-password")
async def change_password(
    body: ChangePasswordBody,
    current_user: dict = Depends(get_current_user),
):
    # Fetch the current hash from DB directly — it is not in current_user dict (intentionally)
    _current_hash = ""
    if _mysql_available:
        try:
            _uid = int(current_user["id"])
            async for db in get_db_session():
                _row = (await db.execute(select(SQLUser).where(SQLUser.id == _uid))).scalar_one_or_none()
                if _row:
                    _current_hash = _get_password_hash_for_auth(_row)
        except Exception:
            pass
    is_valid_pw = await asyncio.to_thread(_verify_password, body.currentPassword, _current_hash)
    if not is_valid_pw:
        raise HTTPException(400, "Current password is incorrect.")
    if body.newPassword != body.confirmPassword:
        raise HTTPException(400, "Passwords do not match.")
    if not _is_strong_password(body.newPassword):
        raise HTTPException(
            400,
            "Password is too weak. Use at least 8 characters with uppercase, lowercase, a number, and a special character.",
        )
    pw_hash = await asyncio.to_thread(_hash_password, body.newPassword)
    uid = int(current_user["id"])
    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(
                    update(SQLUser)
                    .where(SQLUser.id == uid)
                    .values(password_hash=pw_hash, must_change_password=False, updated_at=datetime.now(timezone.utc))
                )
                await db.commit()
            return {"message": "Password changed successfully."}
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "MySQL unavailable")


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return {"user": _to_public_user(current_user)}


class UpdateProfileBody(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None


@router.patch("/me/profile")
async def update_profile(
    body: UpdateProfileBody,
    current_user: dict = Depends(get_current_user),
):
    """Update the authenticated user's profile fields."""
    updates = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.phone is not None:
        updates["phone"] = body.phone.strip()
    
    uid = int(current_user["id"])
    if _mysql_available:
        try:
            async for db in get_db_session():
                if updates:
                    await db.execute(
                        update(SQLUser)
                        .where(SQLUser.id == uid)
                        .values(**updates, updated_at=datetime.now(timezone.utc))
                    )
                    await db.commit()
                stmt = select(SQLUser).where(SQLUser.id == uid)
                res = await db.execute(stmt)
                updated = _sql_user_to_dict(res.scalar_one())
                return {"user": _to_public_user(updated)}
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "MySQL unavailable")


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

    user_id = str(current_user["id"])
    for old_file in upload_dir.glob(f"{user_id}_*"):
        try:
            old_file.unlink()
        except OSError:
            pass

    unique_name = f"{user_id}_{uuid.uuid4().hex}{ext}"
    dest_path = upload_dir / unique_name
    
    def write_avatar_file():
        with open(dest_path, "wb") as f:
            f.write(content)

    await asyncio.to_thread(write_avatar_file)

    uid = int(current_user["id"])
    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(
                    update(SQLUser)
                    .where(SQLUser.id == uid)
                    .values(avatar_url=unique_name, updated_at=datetime.now(timezone.utc))
                )
                await db.commit()
                stmt = select(SQLUser).where(SQLUser.id == uid)
                res = await db.execute(stmt)
                updated = _sql_user_to_dict(res.scalar_one())
                return {"user": _to_public_user(updated)}
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "MySQL unavailable")



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
