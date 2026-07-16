"""
api/routes/tasks.py
--------------------
Tasks CRUD — mirrors Node.js server/routes/tasks.js exactly.

Endpoints:
  GET  /api/tasks              — list all tasks (with assignee populated)
  POST /api/tasks              — create task, email + notify assignee
  PATCH /api/tasks/:id/toggle  — flip done status
  PATCH /api/tasks/:id/assignee — reassign + notify
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.utils.auth import get_current_user
from api.utils.mailer import send_task_assigned_email
from utils.db_client import get_collection

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _populate_assignee(task: dict, users_col) -> dict:
    """Return the task dict with an embedded 'assignee' sub-doc."""
    assignee = None
    if task.get("assignee"):
        try:
            u = users_col.find_one({"_id": ObjectId(str(task["assignee"]))})
            if u:
                assignee = {
                    "id": str(u["_id"]),
                    "name": u.get("name", ""),
                    "email": u.get("email", ""),
                    "seed": u.get("email", ""),
                }
        except Exception:
            pass
    return {
        "id": str(task["_id"]),
        "title": task.get("title", ""),
        "due": task.get("due", ""),
        "priority": task.get("priority", "Medium"),
        "done": task.get("done", False),
        "assigneeId": str(task["assignee"]) if task.get("assignee") else None,
        "assignee": assignee,
        "createdAt": task.get("createdAt", ""),
    }


async def _notify_assignee(task: dict, assigner_id: str, users_col) -> None:
    """Email the assignee (best-effort) when a task is assigned or re-assigned."""
    if not task.get("assignee"):
        return
    try:
        assignee = users_col.find_one({"_id": ObjectId(str(task["assignee"]))})
        assigner = users_col.find_one({"_id": ObjectId(assigner_id)})
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
        _push_notification(
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
        import logging
        logging.getLogger(__name__).warning(f"[Tasks] Notify assignee failed: {exc}")


def _push_notification(
    user_id: str, notif_type: str, title: str, message: str,
    link: str = "", related_id: str = "",
) -> None:
    try:
        get_collection("notifications").insert_one({
            "user": ObjectId(user_id),
            "type": notif_type,
            "title": title,
            "message": message,
            "link": link,
            "relatedId": related_id,
            "read": False,
            "createdAt": datetime.now(tz=timezone.utc),
        })
    except Exception:
        pass


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
    tasks_col = get_collection("tasks")
    users_col = get_collection("users")
    tasks = list(tasks_col.find().sort("createdAt", -1))
    return {"tasks": [_populate_assignee(t, users_col) for t in tasks]}


@router.post("", status_code=201)
async def create_task(
    body: CreateTaskBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.title:
        raise HTTPException(400, "Title is required.")

    users_col = get_collection("users")
    assignee_oid = None
    if body.assigneeId:
        try:
            assignee_oid = ObjectId(body.assigneeId)
        except Exception:
            raise HTTPException(400, "Invalid assignee ID.")
        if not users_col.find_one({"_id": assignee_oid}):
            raise HTTPException(400, "Assignee not found.")

    tasks_col = get_collection("tasks")
    result = tasks_col.insert_one({
        "title": body.title,
        "due": body.due or "",
        "priority": body.priority or "Medium",
        "done": False,
        "assignee": assignee_oid,
        "createdBy": current_user["_id"],
        "createdAt": datetime.now(tz=timezone.utc),
    })

    task = tasks_col.find_one({"_id": result.inserted_id})
    await _notify_assignee(task, str(current_user["_id"]), users_col)
    return {"task": _populate_assignee(task, users_col)}


@router.patch("/{task_id}/toggle")
async def toggle_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(400, "Invalid task ID.")

    tasks_col = get_collection("tasks")
    task = tasks_col.find_one({"_id": oid})
    if not task:
        raise HTTPException(404, "Task not found.")

    new_done = not task.get("done", False)
    task = tasks_col.find_one_and_update(
        {"_id": oid},
        {"$set": {"done": new_done}},
        return_document=True,
    )
    return {"task": _populate_assignee(task, get_collection("users"))}


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
    except Exception:
        raise HTTPException(400, "Invalid ID.")

    users_col = get_collection("users")
    if not users_col.find_one({"_id": assignee_oid}):
        raise HTTPException(400, "Assignee not found.")

    tasks_col = get_collection("tasks")
    task = tasks_col.find_one_and_update(
        {"_id": task_oid},
        {"$set": {"assignee": assignee_oid}},
        return_document=True,
    )
    if not task:
        raise HTTPException(404, "Task not found.")

    await _notify_assignee(task, str(current_user["_id"]), users_col)
    return {"task": _populate_assignee(task, users_col)}
