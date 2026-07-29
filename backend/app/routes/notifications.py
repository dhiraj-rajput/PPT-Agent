"""
app/routes/notifications.py
----------------------------
In-app notification endpoints — using MySQL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import get_db_session, _mysql_available
from models.sql_models import (
    Notification as SQL_Notification,
    User as SQLUser,
)
from sqlalchemy import select, insert, update, delete, func

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _iso(dt: Any) -> Optional[str]:
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


def _to_public_notification(n: SQL_Notification) -> dict:
    if not n:
        return {}
    return {
        "id": str(n.id),
        "type": n.notification_type or "",
        "title": n.title or "",
        "message": n.message or "",
        "link": n.link or "",
        "relatedId": n.related_id or "",
        "read": bool(n.is_read),
        "createdAt": _iso(n.created_at),
    }


@router.get("")
async def list_notifications(current_user: dict = Depends(get_current_user)):
    uid = int(current_user["id"])
    notifications = []
    unread_count = 0

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Notification).where(SQL_Notification.user_id == uid).order_by(SQL_Notification.created_at.desc()).limit(50)
                res = await db.execute(stmt)
                notifications = [_to_public_notification(n) for n in res.scalars().all()]

                stmt_count = select(func.count()).select_from(SQL_Notification).where(SQL_Notification.user_id == uid, SQL_Notification.is_read == False)
                unread_count = (await db.execute(stmt_count)).scalar() or 0
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")

    return {
        "notifications": notifications,
        "unreadCount": unread_count,
    }


class CreateNotifBody(BaseModel):
    title: str
    message: Optional[str] = ""
    link: Optional[str] = ""
    userId: Optional[str] = None


@router.post("", status_code=201)
async def create_notification(
    body: CreateNotifBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.title:
        raise HTTPException(400, "Title is required.")

    target_id = int(current_user["id"])

    if _mysql_available:
        try:
            async for db in get_db_session():
                if body.userId:
                    try:
                        target_oid = int(body.userId)
                    except ValueError:
                        raise HTTPException(400, "Invalid userId.")
                    
                    stmt_u = select(SQLUser).where(SQLUser.id == target_oid)
                    u = (await db.execute(stmt_u)).scalar_one_or_none()
                    if not u:
                        raise HTTPException(400, "Target user not found.")
                    target_id = target_oid

                new_notif = SQL_Notification(
                    user_id=target_id,
                    notification_type="custom",
                    title=body.title,
                    message=body.message or "",
                    link=body.link or "",
                    related_id="",
                    is_read=False,
                    created_at=datetime.utcnow()
                )
                db.add(new_notif)
                await db.commit()
                await db.refresh(new_notif)

                return {"notification": _to_public_notification(new_notif)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error creating notification: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.patch("/read-all")
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    uid = int(current_user["id"])
    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(
                    update(SQL_Notification)
                    .where(SQL_Notification.user_id == uid, SQL_Notification.is_read == False)
                    .values(is_read=True)
                )
                await db.commit()
                return {"ok": True}
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.patch("/{notif_id}/read")
async def mark_read(
    notif_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        nid = int(notif_id)
    except ValueError:
        raise HTTPException(400, "Invalid notification ID.")

    uid = int(current_user["id"])

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Notification).where(SQL_Notification.id == nid, SQL_Notification.user_id == uid)
                notif = (await db.execute(stmt)).scalar_one_or_none()
                if not notif:
                    raise HTTPException(404, "Notification not found.")

                await db.execute(
                    update(SQL_Notification)
                    .where(SQL_Notification.id == nid, SQL_Notification.user_id == uid)
                    .values(is_read=True)
                )
                await db.commit()

                # refetch
                stmt_new = select(SQL_Notification).where(SQL_Notification.id == nid, SQL_Notification.user_id == uid)
                notif = (await db.execute(stmt_new)).scalar_one()
                return {"notification": _to_public_notification(notif)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.delete("")
async def clear_all_notifications(current_user: dict = Depends(get_current_user)):
    uid = int(current_user["id"])
    if _mysql_available:
        try:
            async for db in get_db_session():
                res = await db.execute(delete(SQL_Notification).where(SQL_Notification.user_id == uid))
                await db.commit()
                return {"ok": True, "deleted": getattr(res, "rowcount", 0)}

        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")


@router.delete("/{notif_id}")
async def delete_notification(
    notif_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        nid = int(notif_id)
    except ValueError:
        raise HTTPException(400, "Invalid notification ID.")

    uid = int(current_user["id"])

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Notification).where(SQL_Notification.id == nid, SQL_Notification.user_id == uid)
                notif = (await db.execute(stmt)).scalar_one_or_none()
                if not notif:
                    raise HTTPException(404, "Notification not found.")

                await db.execute(delete(SQL_Notification).where(SQL_Notification.id == nid, SQL_Notification.user_id == uid))
                await db.commit()
                return {"ok": True}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")
    raise HTTPException(500, "Database is unavailable.")
