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

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
import bcrypt
from pydantic import BaseModel
from typing import Optional, Any

from app.core.auth import get_current_user, require_admin
from app.core.mailer import send_invite_email
from utils.db_client import get_async_collection

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
    return {
        "id": str(u["_id"]),
        "name": u.get("name", ""),
        "email": u.get("email", ""),
        "role": u.get("role", "Team Member"),
        "status": "Active" if u.get("isVerified") else "Pending",
        "seed": u.get("email", ""),
        "createdAt": u.get("createdAt", ""),
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
    users_col = get_async_collection("users")
    users = await users_col.find().sort("createdAt", -1).to_list(length=1000)
    return {"users": [_to_public_user(u) for u in users]}


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

    users_col = get_async_collection("users")
    normalized = body.email.lower().strip()
    existing = await users_col.find_one({"email": normalized})
    if existing:
        raise HTTPException(409, "A user with that email already exists.")

    temp_password = secrets.token_urlsafe(9)
    pw_hash = await asyncio.to_thread(_hash_pw_sync, temp_password)
    invitee_name = (body.name or "").strip() or normalized.split("@")[0]
    raw_role = body.role.value if isinstance(body.role, ValidRoles) else str(body.role or "Team Member")
    assigned_role = "Admin" if raw_role.lower() in ("admin", "administrator") else raw_role

    result = await users_col.insert_one({
        "name": invitee_name,
        "email": normalized,
        "phone": "",
        "passwordHash": pw_hash,
        "isVerified": True,
        "role": assigned_role,
        "mustChangePassword": True,
        "invitedBy": current_user["_id"],
        "createdAt": datetime.now(tz=timezone.utc),
    })

    user = await users_col.find_one({"_id": result.inserted_id})
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

    response: dict[str, Any] = {"user": _to_public_user(user)}
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
        oid = ObjectId(user_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid user ID.")

    users_col = get_async_collection("users")
    raw_role = body.role.value if isinstance(body.role, ValidRoles) else str(body.role)
    assigned_role = "Admin" if raw_role.lower() in ("admin", "administrator") else raw_role
    
    await users_col.update_one(
        {"_id": oid},
        {"$set": {"role": assigned_role}},
    )
    user = await users_col.find_one({"_id": oid})
    if not user:
        raise HTTPException(404, "User not found.")
    return {"user": _to_public_user(user)}
