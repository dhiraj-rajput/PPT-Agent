"""
api/routes/notifications.py
----------------------------
In-app notification endpoints — mirrors Node.js server/routes/notifications.js.

Endpoints:
  GET    /api/notifications           — list user's notifications (+ unreadCount)
  POST   /api/notifications           — create a custom alert
  PATCH  /api/notifications/read-all  — mark all as read
  PATCH  /api/notifications/:id/read  — mark one as read
  DELETE /api/notifications/:id       — delete one
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import get_collection

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _to_public_notification(n: dict) -> dict:
    return {
        "id": str(n["_id"]),
        "type": n.get("type", ""),
        "title": n.get("title", ""),
        "message": n.get("message", ""),
        "link": n.get("link", ""),
        "relatedId": n.get("relatedId", ""),
        "read": n.get("read", False),
        "createdAt": n.get("createdAt", ""),
    }


@router.get("")
def list_notifications(current_user: dict = Depends(get_current_user)):
    notifs_col = get_collection("notifications")
    uid = current_user["_id"]
    notifications = list(
        notifs_col.find({"user": uid}).sort("createdAt", -1).limit(50)
    )
    unread_count = notifs_col.count_documents({"user": uid, "read": False})
    return {
        "notifications": [_to_public_notification(n) for n in notifications],
        "unreadCount": unread_count,
    }


class CreateNotifBody(BaseModel):
    title: str
    message: Optional[str] = ""
    link: Optional[str] = ""
    userId: Optional[str] = None


@router.post("", status_code=201)
def create_notification(
    body: CreateNotifBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.title:
        raise HTTPException(400, "Title is required.")

    notifs_col = get_collection("notifications")
    users_col = get_collection("users")

    target_id = current_user["_id"]
    if body.userId:
        try:
            target_oid = ObjectId(body.userId)
        except Exception:
            raise HTTPException(400, "Invalid userId.")
        if not users_col.find_one({"_id": target_oid}):
            raise HTTPException(400, "Target user not found.")
        target_id = target_oid

    result = notifs_col.insert_one({
        "user": target_id,
        "type": "custom",
        "title": body.title,
        "message": body.message or "",
        "link": body.link or "",
        "relatedId": "",
        "read": False,
        "createdAt": datetime.now(tz=timezone.utc),
    })
    notification = notifs_col.find_one({"_id": result.inserted_id})
    if not notification:
        raise HTTPException(500, "Could not create alert.")
    return {"notification": _to_public_notification(notification)}


@router.patch("/read-all")
def mark_all_read(current_user: dict = Depends(get_current_user)):
    get_collection("notifications").update_many(
        {"user": current_user["_id"], "read": False},
        {"$set": {"read": True}},
    )
    return {"ok": True}


@router.patch("/{notif_id}/read")
def mark_read(
    notif_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(notif_id)
    except Exception:
        raise HTTPException(400, "Invalid notification ID.")

    notification = get_collection("notifications").find_one_and_update(
        {"_id": oid, "user": current_user["_id"]},
        {"$set": {"read": True}},
        return_document=True,
    )
    if not notification:
        raise HTTPException(404, "Alert not found.")
    return {"notification": _to_public_notification(notification)}


@router.delete("/{notif_id}")
def delete_notification(
    notif_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(notif_id)
    except Exception:
        raise HTTPException(400, "Invalid notification ID.")

    result = get_collection("notifications").find_one_and_delete(
        {"_id": oid, "user": current_user["_id"]}
    )
    if not result:
        raise HTTPException(404, "Alert not found.")
    return {"ok": True}
