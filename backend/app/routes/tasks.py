"""
app/routes/tasks.py
--------------------
Tasks CRUD — mirrors Node.js server/routes/tasks.js exactly.

Endpoints:
  GET  /api/tasks              — list all tasks (with assignee populated)
  POST /api/tasks              — create task, email + notify assignee
  PATCH /api/tasks/:id/toggle  — flip done status
  PATCH /api/tasks/:id/assignee — reassign + notify
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.mailer import send_task_assigned_email
from utils.db_client import get_async_collection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_task_with_user_map(task: Optional[dict], users_map: dict) -> dict:
    """Format a task dict with embedded assignee details using a pre-fetched user map."""
    if not task:
        return {}
    assignee_id = str(task["assignee"]) if task.get("assignee") else None
    assignee = users_map.get(assignee_id) if assignee_id else None
    return {
        "id": str(task["_id"]),
        "title": task.get("title", ""),
        "due": task.get("due", ""),
        "priority": task.get("priority", "Medium"),
        "done": task.get("done", False),
        "assigneeId": assignee_id,
        "assignee": assignee,
        "createdAt": task.get("createdAt", ""),
    }


async def _notify_assignee(task: Optional[dict], assigner_id: str) -> None:
    """Email the assignee (best-effort) when a task is assigned or re-assigned."""
    if not task or not task.get("assignee"):
        return
    try:
        users_col = get_async_collection("users")
        assignee = await users_col.find_one({"_id": ObjectId(str(task["assignee"]))})
        assigner = await users_col.find_one({"_id": ObjectId(assigner_id)})
        if not assignee:
            return
        await send_task_assigned_email(
            to_email=assignee["email"],
            assignee_name=assignee.get("name", ""),
            task_title=task.get("title", ""),
            due=task.get("due"),
            priority=task.get("priority", "Medium"),
            assigner_name=assigner.get("name") if assigner else None,
        )
        # In-app notification
        await _push_notification_async(
            user_id=str(assignee["_id"]),
            notif_type="task_assigned",
            title="New task assigned to you",
            message=(
                f"{assigner.get('name', 'Someone') if assigner else 'Someone'} "
                f"assigned you \"{task.get('title', '')}\"."
            ),
            link="/tasks",
            related_id=str(task["_id"]),
        )
    except Exception as exc:
        logger.warning(f"[Tasks] Notify assignee failed: {exc}")


async def _push_notification_async(
    user_id: str, notif_type: str, title: str, message: str,
    link: str = "", related_id: str = "",
) -> None:
    try:
        notifs_col = get_async_collection("notifications")
        await notifs_col.insert_one({
            "user": ObjectId(user_id),
            "type": notif_type,
            "title": title,
            "message": message,
            "link": link,
            "relatedId": related_id,
            "read": False,
            "createdAt": datetime.now(tz=timezone.utc),
        })
    except Exception as e:
        logger.warning(f"[Tasks] Push notification error: {e}")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateTaskBody(BaseModel):
    title: str
    due: Optional[str] = ""
    priority: Optional[str] = "Medium"
    assigneeId: Optional[str] = None


class ReassignBody(BaseModel):
    assigneeId: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def list_tasks(current_user: dict = Depends(get_current_user)):
    tasks_col = get_async_collection("tasks")
    users_col = get_async_collection("users")
    
    tasks = await tasks_col.find().sort("createdAt", -1).to_list(length=1000)
    
    # Batch load all assignees in a single $in query (Fixes N+1 query)
    assignee_oids = list({t["assignee"] for t in tasks if t.get("assignee")})
    users_map = {}
    if assignee_oids:
        users = await users_col.find({"_id": {"$in": assignee_oids}}).to_list(length=len(assignee_oids))
        for u in users:
            users_map[str(u["_id"])] = {
                "id": str(u["_id"]),
                "name": u.get("name", ""),
                "email": u.get("email", ""),
                "seed": u.get("email", ""),
            }

    return {"tasks": [_format_task_with_user_map(t, users_map) for t in tasks]}


@router.post("", status_code=201)
async def create_task(
    body: CreateTaskBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.title:
        raise HTTPException(400, "Title is required.")

    users_col = get_async_collection("users")
    assignee_oid = None
    if body.assigneeId:
        try:
            assignee_oid = ObjectId(body.assigneeId)
        except InvalidId:
            raise HTTPException(400, "Invalid assignee ID.")
        if not await users_col.find_one({"_id": assignee_oid}):
            raise HTTPException(400, "Assignee not found.")

    tasks_col = get_async_collection("tasks")
    result = await tasks_col.insert_one({
        "title": body.title,
        "due": body.due or "",
        "priority": body.priority or "Medium",
        "done": False,
        "assignee": assignee_oid,
        "createdBy": current_user["_id"],
        "createdAt": datetime.now(tz=timezone.utc),
    })

    task = await tasks_col.find_one({"_id": result.inserted_id})
    await _notify_assignee(task, str(current_user["_id"]))
    
    users_map = {}
    if assignee_oid:
        u = await users_col.find_one({"_id": assignee_oid})
        if u:
            users_map[str(u["_id"])] = {"id": str(u["_id"]), "name": u.get("name", ""), "email": u.get("email", ""), "seed": u.get("email", "")}

    return {"task": _format_task_with_user_map(task, users_map)}


@router.patch("/{task_id}/toggle")
async def toggle_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(task_id)
    except InvalidId:
        raise HTTPException(400, "Invalid task ID.")

    tasks_col = get_async_collection("tasks")
    users_col = get_async_collection("users")
    task = await tasks_col.find_one({"_id": oid})
    if not task:
        raise HTTPException(404, "Task not found.")

    new_done = not task.get("done", False)
    await tasks_col.update_one(
        {"_id": oid},
        {"$set": {"done": new_done}},
    )
    updated_task = await tasks_col.find_one({"_id": oid})

    users_map = {}
    if updated_task and updated_task.get("assignee"):
        u = await users_col.find_one({"_id": updated_task["assignee"]})
        if u:
            users_map[str(u["_id"])] = {"id": str(u["_id"]), "name": u.get("name", ""), "email": u.get("email", ""), "seed": u.get("email", "")}

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
        task_oid = ObjectId(task_id)
        assignee_oid = ObjectId(body.assigneeId)
    except InvalidId:
        raise HTTPException(400, "Invalid ID.")

    users_col = get_async_collection("users")
    if not await users_col.find_one({"_id": assignee_oid}):
        raise HTTPException(400, "Assignee not found.")

    tasks_col = get_async_collection("tasks")
    await tasks_col.update_one(
        {"_id": task_oid},
        {"$set": {"assignee": assignee_oid}},
    )
    updated_task = await tasks_col.find_one({"_id": task_oid})
    if not updated_task:
        raise HTTPException(404, "Task not found.")

    await _notify_assignee(updated_task, str(current_user["_id"]))
    
    users_map = {}
    u = await users_col.find_one({"_id": assignee_oid})
    if u:
        users_map[str(u["_id"])] = {"id": str(u["_id"]), "name": u.get("name", ""), "email": u.get("email", ""), "seed": u.get("email", "")}

    return {"task": _format_task_with_user_map(updated_task, users_map)}
