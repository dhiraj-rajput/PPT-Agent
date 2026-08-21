"""
app/routes/tasks.py
--------------------
Tasks CRUD — using MySQL.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from models.sql_models import (
    Notification as SQL_Notification,
)
from models.sql_models import (
    Task as SQL_Task,
)
from models.sql_models import (
    User as SQLUser,
)
from pydantic import BaseModel
from sqlalchemy import select, update
from utils.db_client import _mysql_available, get_db_session

from app.core.auth import get_current_user
from app.core.mailer import send_task_assigned_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


def _iso(dt: Any) -> str | None:
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


def _format_task_with_user_map(task: SQL_Task, users_map: dict) -> dict:
    if not task:
        return {}
    assignee_id = str(task.assignee) if task.assignee is not None else None
    assignee = users_map.get(assignee_id) if assignee_id else None
    return {
        "id": str(task.id),
        "title": task.title or "",
        "due": task.due or "",
        "priority": (task.priority or "medium").title(),
        "done": bool(task.done),
        "assigneeId": assignee_id,
        "assignee": assignee,
        "createdAt": _iso(task.created_at),
    }


async def _notify_assignee(task: SQL_Task, assigner_id: int) -> None:
    if not task or task.assignee is None:
        return
    try:
        assignee = None
        assigner = None
        async for db in get_db_session():
            assignee = (await db.execute(select(SQLUser).where(SQLUser.id == task.assignee))).scalar_one_or_none()
            assigner = (await db.execute(select(SQLUser).where(SQLUser.id == assigner_id))).scalar_one_or_none()

        if not assignee:
            return
        
        await send_task_assigned_email(
            to_email=str(assignee.email),
            assignee_name=str(assignee.name or ""),
            task_title=str(task.title or ""),
            due=str(task.due) if getattr(task, "due", None) else None,
            priority=str(task.priority or "medium").title(),
            assigner_name=str(assigner.name) if (assigner and getattr(assigner, "name", None)) else None,
        )



        # In-app notification
        await _push_notification_async(
            user_id=str(assignee.id),
            notif_type="task_assigned",
            title="New task assigned to you",
            message=(
                f"{assigner.name if assigner else 'Someone'} "
                f"assigned you \"{task.title or ''}\"."
            ),
            link="/tasks",
            related_id=str(task.id),
        )
    except Exception as exc:
        logger.warning(f"[Tasks] Notify assignee failed: {exc}")


async def _push_notification_async(
    user_id: str, notif_type: str, title: str, message: str,
    link: str = "", related_id: str = "",
) -> None:
    if not _mysql_available:
        return
    try:
        async for db in get_db_session():
            db.add(SQL_Notification(
                user_id=int(user_id),
                notification_type=notif_type,
                title=title,
                message=message,
                link=link,
                related_id=related_id,
                is_read=False,
                created_at=datetime.utcnow()
            ))
            await db.commit()
    except Exception as e:
        logger.warning(f"[Tasks] Push notification error: {e}")


class CreateTaskBody(BaseModel):
    title: str
    due: str | None = ""
    priority: str | None = "Medium"
    assigneeId: str | None = None


class ReassignBody(BaseModel):
    assigneeId: str


@router.get("")
async def list_tasks(current_user: dict = Depends(get_current_user)):
    tasks = []
    users_map = {}
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Task).order_by(SQL_Task.created_at.desc())
                res = await db.execute(stmt)
                tasks = res.scalars().all()

                assignee_ids = list({t.assignee for t in tasks if t.assignee is not None})
                if assignee_ids:
                    stmt_users = select(SQLUser).where(SQLUser.id.in_(assignee_ids))
                    res_users = await db.execute(stmt_users)
                    for u in res_users.scalars().all():
                        users_map[str(u.id)] = {
                            "id": str(u.id),
                            "name": u.name or "",
                            "email": u.email or "",
                            "seed": u.email or "",
                        }
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")

    return {"tasks": [_format_task_with_user_map(t, users_map) for t in tasks]}


@router.post("", status_code=201)
async def create_task(
    body: CreateTaskBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.title:
        raise HTTPException(400, "Title is required.")

    assignee_id = None
    if body.assigneeId:
        try:
            assignee_id = int(body.assigneeId)
        except ValueError:
            raise HTTPException(400, "Invalid assignee ID.")

    task: SQL_Task | None = None
    if _mysql_available:
        try:
            async for db in get_db_session():
                if assignee_id is not None:
                    stmt = select(SQLUser).where(SQLUser.id == assignee_id)
                    u = (await db.execute(stmt)).scalar_one_or_none()
                    if not u:
                        raise HTTPException(400, "Assignee not found.")

                new_task = SQL_Task(
                    title=body.title,
                    due=body.due or "",
                    priority=(body.priority or "Medium").lower(),
                    done=False,
                    assignee=assignee_id,
                    created_by=int(current_user["id"]),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(new_task)
                await db.commit()
                await db.refresh(new_task)

                task = new_task
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error creating task: {e}")

    if task is not None:
        await _notify_assignee(task, int(current_user["id"]))
    
    users_map = {}
    if assignee_id is not None:
        async for db in get_db_session():
            u = (await db.execute(select(SQLUser).where(SQLUser.id == assignee_id))).scalar_one_or_none()
            if u:
                users_map[str(u.id)] = {"id": str(u.id), "name": u.name or "", "email": u.email or "", "seed": u.email or ""}

    return {"task": _format_task_with_user_map(task, users_map)}


@router.patch("/{task_id}/toggle")
async def toggle_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        tid = int(task_id)
    except ValueError:
        raise HTTPException(400, "Invalid task ID.")

    updated_task: SQL_Task | None = None
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Task).where(SQL_Task.id == tid)
                res = await db.execute(stmt)
                task = res.scalar_one_or_none()
                if not task:
                    raise HTTPException(404, "Task not found.")

                new_done = not bool(task.done)
                await db.execute(
                    update(SQL_Task)
                    .where(SQL_Task.id == tid)
                    .values(done=new_done, updated_at=datetime.utcnow())
                )
                await db.commit()

                # refetch
                updated_task = (await db.execute(select(SQL_Task).where(SQL_Task.id == tid))).scalar_one()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")

    users_map = {}
    if updated_task and updated_task.assignee is not None:
        async for db in get_db_session():
            u = (await db.execute(select(SQLUser).where(SQLUser.id == updated_task.assignee))).scalar_one_or_none()
            if u:
                users_map[str(u.id)] = {"id": str(u.id), "name": u.name or "", "email": u.email or "", "seed": u.email or ""}

    return {"task": _format_task_with_user_map(updated_task, users_map)}


@router.patch("/{task_id}/assignee")
async def reassign_task(
    task_id: str,
    body: ReassignBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.assigneeId:
        raise HTTPException(400, "assigneeId is required.")
    try:
        tid = int(task_id)
        assignee_id = int(body.assigneeId)
    except ValueError:
        raise HTTPException(400, "Invalid ID.")

    updated_task: SQL_Task | None = None
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQLUser).where(SQLUser.id == assignee_id)
                u = (await db.execute(stmt)).scalar_one_or_none()
                if not u:
                    raise HTTPException(400, "Assignee not found.")

                await db.execute(
                    update(SQL_Task)
                    .where(SQL_Task.id == tid)
                    .values(assignee=assignee_id, updated_at=datetime.utcnow())
                )
                await db.commit()

                # refetch
                updated_task = (await db.execute(select(SQL_Task).where(SQL_Task.id == tid))).scalar_one_or_none()
                if not updated_task:
                    raise HTTPException(404, "Task not found.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Database error: {e}")

    if updated_task is not None:
        await _notify_assignee(updated_task, int(current_user["id"]))
    
    users_map = {}
    async for db in get_db_session():
        u = (await db.execute(select(SQLUser).where(SQLUser.id == assignee_id))).scalar_one_or_none()
        if u:
            users_map[str(u.id)] = {"id": str(u.id), "name": u.name or "", "email": u.email or "", "seed": u.email or ""}

    return {"task": _format_task_with_user_map(updated_task, users_map)}
