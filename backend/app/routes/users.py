"""
app/routes/users.py
--------------------
User management endpoints for OrbitAvanya — mirrors Node.js server/routes/users.js.

Endpoints:
  GET  /api/users           — list all users (requires auth)
  POST /api/users/invite    — invite a new team member (sends email)
  PATCH /api/users/:id/role — change a user's role
"""

from __future__ import annotations

import asyncio
import re
import secrets
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException
import bcrypt
from pydantic import BaseModel
from typing import Optional, Any

from app.core.auth import get_current_user, require_admin
from app.core.mailer import send_invite_email
from utils.db_client import get_db_session, _mysql_available
from models.sql_models import User as SQLUser
from sqlalchemy import select, insert, update, delete

router = APIRouter(prefix="/users", tags=["users"])



class ValidRoles(str, Enum):
    OWNER = "Owner"
    ADMIN = "Admin"
    ADMINISTRATOR = "Administrator"
    PROPOSAL_WRITER = "Proposal Writer"
    CONTRACT_SPECIALIST = "Contract Specialist"
    BUSINESS_DEVELOPMENT = "Business Development"
    TEAM_MEMBER = "Team Member"
    VIEWER = "Viewer"


def _to_public_user(u: Optional[dict]) -> dict:
    if not u:
        return {}
    uid = u.get("_id") or u.get("id")
    return {
        "id": str(uid) if uid is not None else "",
        "name": u.get("name", ""),
        "email": u.get("email", ""),
        "role": u.get("role", "Team Member"),
        "status": "Active" if (u.get("isVerified") or u.get("is_verified")) else "Pending",
        "seed": u.get("email", ""),
        "createdAt": str(u.get("createdAt") or u.get("created_at") or ""),
    }


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email))


def _hash_pw_sync(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def list_users(current_user: dict = Depends(get_current_user)):
    users = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQLUser).order_by(SQLUser.created_at.desc())
                res = await db.execute(stmt)
                for u in res.scalars().all():
                    users.append({
                        "id": str(u.id),
                        "name": u.name or "",
                        "email": u.email or "",
                        "role": u.role or "Team Member",
                        "status": "Active" if getattr(u, "is_verified", True) else "Pending",
                        "seed": u.email or "",
                        "createdAt": str(u.created_at or "")
                    })
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    return {"users": users}


class InviteBody(BaseModel):
    name: Optional[str] = None
    email: str
    role: Optional[ValidRoles] = ValidRoles.TEAM_MEMBER


@router.post("/invite", status_code=201)
async def invite_user(
    body: InviteBody,
    current_user: dict = Depends(require_admin),
):
    if not body.email or not _is_valid_email(body.email):
        raise HTTPException(400, "A valid email address is required.")

    normalized = body.email.lower().strip()
    existing = None
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQLUser).where(SQLUser.email == normalized)
                res = await db.execute(stmt)
                existing = res.scalar_one_or_none()
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")

    if existing:
        raise HTTPException(409, "A user with that email already exists.")

    temp_password = secrets.token_urlsafe(9)
    pw_hash = await asyncio.to_thread(_hash_pw_sync, temp_password)
    invitee_name = (body.name or "").strip() or normalized.split("@")[0]
    raw_role = body.role.value if isinstance(body.role, ValidRoles) else str(body.role or "Team Member")
    assigned_role = "Admin" if raw_role.lower() in ("admin", "administrator") else raw_role

    user_dict: dict[str, Any] = {}
    if _mysql_available:
        try:
            from datetime import timezone
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            async for db in get_db_session():
                stmt = insert(SQLUser).values(
                    name=invitee_name,
                    email=normalized,
                    phone="",
                    password_hash=pw_hash,
                    is_verified=True,
                    role=assigned_role,
                    must_change_password=True,
                    invited_by=int(current_user["id"]),
                    created_at=now_utc,
                    updated_at=now_utc
                )
                await db.execute(stmt)
                await db.commit()
                
                stmt_new = select(SQLUser).where(SQLUser.email == normalized)
                new_row = (await db.execute(stmt_new)).scalar_one()
                user_dict = {
                    "id": str(new_row.id),
                    "name": new_row.name or "",
                    "email": new_row.email or "",
                    "role": new_row.role or "Team Member",
                    "status": "Active" if getattr(new_row, "is_verified", True) else "Pending",
                    "seed": new_row.email or "",
                    "createdAt": str(new_row.created_at or "")
                }

        except Exception as e:
            raise HTTPException(500, f"Database error during invite: {e}")

    warning = None
    try:
        await send_invite_email(
            to_email=normalized,
            invitee_name=invitee_name,
            role=assigned_role,
            inviter_name=current_user.get("name"),
            temp_password=temp_password,
        )
    except Exception:
        warning = "User created, but the invite email could not be sent. Check SMTP settings."

    response: dict[str, Any] = {"user": user_dict}
    if warning:
        response["warning"] = warning
    return response


class UpdateRoleBody(BaseModel):
    role: ValidRoles


@router.patch("/{user_id}/role")
async def update_role(
    user_id: str,
    body: UpdateRoleBody,
    current_user: dict = Depends(require_admin),
):
    try:
        uid = int(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID.")

    raw_role = body.role.value if isinstance(body.role, ValidRoles) else str(body.role)
    assigned_role = "Admin" if raw_role.lower() in ("admin", "administrator") else raw_role
    
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQLUser).where(SQLUser.id == uid)
                res = await db.execute(stmt)
                user_row = res.scalar_one_or_none()
                if not user_row:
                    raise HTTPException(404, "User not found.")

                await db.execute(
                    update(SQLUser)
                    .where(SQLUser.id == uid)
                    .values(role=assigned_role, updated_at=datetime.now(timezone.utc))
                )
                await db.commit()

                res2 = await db.execute(select(SQLUser).where(SQLUser.id == uid))
                u = res2.scalar_one()
                return {"user": {
                    "id": str(u.id),
                    "name": u.name or "",
                    "email": u.email or "",
                    "role": u.role or "Team Member",
                    "status": "Active" if getattr(u, "is_verified", False) else "Pending",
                    "seed": u.email or "",
                    "createdAt": str(u.created_at or "")
                }}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "MySQL unavailable")


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
):
    try:
        uid = int(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID.")

    if str(current_user["id"]) == str(user_id):
        raise HTTPException(400, "You cannot delete your own account.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQLUser).where(SQLUser.id == uid)
                res = await db.execute(stmt)
                user = res.scalar_one_or_none()
                if not user:
                    raise HTTPException(404, "User not found.")

                await db.execute(delete(SQLUser).where(SQLUser.id == uid))
                await db.commit()
                return {"ok": True, "message": f"User {user.email} has been deleted."}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "MySQL unavailable")


@router.post("/{user_id}/resend-invite")
async def resend_invite(
    user_id: str,
    current_user: dict = Depends(require_admin),
):
    try:
        uid = int(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID.")

    user_dict = {}
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQLUser).where(SQLUser.id == uid)
                res = await db.execute(stmt)
                user = res.scalar_one_or_none()
                if not user:
                    raise HTTPException(404, "User not found.")

                temp_password = secrets.token_urlsafe(9)
                pw_hash = await asyncio.to_thread(_hash_pw_sync, temp_password)

                await db.execute(
                    update(SQLUser)
                    .where(SQLUser.id == uid)
                    .values(password_hash=pw_hash, must_change_password=True, updated_at=datetime.now(timezone.utc))
                )
                await db.commit()

                res2 = await db.execute(select(SQLUser).where(SQLUser.id == uid))
                u = res2.scalar_one()
                user_dict = {
                    "id": str(u.id),
                    "name": u.name or "",
                    "email": u.email or "",
                    "role": u.role or "Team Member",
                    "status": "Active" if getattr(u, "is_verified", False) else "Pending",

                    "seed": u.email or "",
                    "createdAt": str(u.created_at or "")
                }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")

    warning = None
    try:
        await send_invite_email(
            to_email=user_dict["email"],
            invitee_name=user_dict.get("name", user_dict["email"].split("@")[0]),
            role=user_dict.get("role", "Team Member"),
            inviter_name=current_user.get("name"),
            temp_password=temp_password,
        )
    except Exception:
        warning = "Temp password updated, but the invite email could not be sent. Check SMTP settings."

    response: dict[str, Any] = {"ok": True, "user": user_dict, "tempPassword": temp_password}
    if warning:
        response["warning"] = warning
    return response

