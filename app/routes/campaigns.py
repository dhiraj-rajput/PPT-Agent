"""
app/routes/campaigns.py
-------------------------
Campaign management & execution endpoints using async Motor.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import get_async_collection, get_collection

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignCreateBody(BaseModel):
    name: str
    description: Optional[str] = ""
    subject: str
    body: Optional[str] = ""
    senderEmail: Optional[str] = ""
    senderName: Optional[str] = ""
    dailyLimit: Optional[int] = 200
    timezone: Optional[str] = "America/Chicago"
    workingHoursOnly: Optional[bool] = False
    scheduleStart: Optional[str] = None
    attachmentPath: Optional[str] = None
    attachmentFilename: Optional[str] = None


class CampaignUpdateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    senderEmail: Optional[str] = None
    senderName: Optional[str] = None
    dailyLimit: Optional[int] = None
    timezone: Optional[str] = None
    workingHoursOnly: Optional[bool] = None
    scheduleStart: Optional[str] = None
    attachmentPath: Optional[str] = None
    attachmentFilename: Optional[str] = None


def _iso(val: Any) -> Optional[str]:
    if val is not None and hasattr(val, "isoformat"):
        return val.isoformat()
    return None


def _format_campaign(c: Optional[dict]) -> dict:
    if not c:
        return {}
    stats = c.get("stats", {}) or {}
    return {
        "id": str(c["_id"]),
        "name": c.get("name", ""),
        "description": c.get("description", ""),
        "status": c.get("status", "draft"),
        "subject": c.get("subject", ""),
        "body": c.get("body", ""),
        "senderEmail": c.get("senderEmail", ""),
        "senderName": c.get("senderName", ""),
        "dailyLimit": c.get("dailyLimit", 200),
        "timezone": c.get("timezone", "America/Chicago"),
        "workingHoursOnly": c.get("workingHoursOnly", False),
        "scheduleStart": _iso(c.get("scheduleStart")),
        "attachmentPath": c.get("attachmentPath", ""),
        "attachmentFilename": c.get("attachmentFilename", ""),
        "campaignNumber": c.get("campaignNumber", 0),
        "stats": {
            "totalSent": stats.get("totalSent", 0),
            "totalOpened": stats.get("totalOpened", 0),
            "totalClicked": stats.get("totalClicked", 0),
            "totalReplied": stats.get("totalReplied", 0),
            "totalBounced": stats.get("totalBounced", 0),
            "totalUnsubscribed": stats.get("totalUnsubscribed", 0),
            "totalResent": stats.get("totalResent", 0),
        },
        "createdAt": _iso(c.get("createdAt")),
        "updatedAt": _iso(c.get("updatedAt")),
    }


async def _queue_pending_leads_async(campaign_id: ObjectId, daily_limit: int):
    """Calculate and assign send_after timestamps spacing out leads across the day."""
    leads_col = get_async_collection("leads")
    pending = await leads_col.find({"campaignId": campaign_id, "status": "pending"}, {"_id": 1}).to_list(length=10000)
    if not pending:
        return 0

    now = datetime.now(timezone.utc)
    limit = daily_limit or 200
    spacing_ms = max(int((24 * 60 * 60 * 1000) / limit), 1000)

    for i, lead in enumerate(pending):
        if i >= limit:
            break
        send_after = now + timedelta(milliseconds=i * spacing_ms)
        await leads_col.update_one(
            {"_id": lead["_id"]},
            {"$set": {"send_after": send_after}}
        )
    return min(len(pending), limit)


@router.get("/worker-status")
async def get_worker_status(current_user: dict = Depends(get_current_user)):
    """Check if the background email campaign worker is active."""
    col = get_async_collection("system_status")
    status = await col.find_one({"key": "email_worker"})
    if not status:
        return {"active": False, "message": "Worker has never been started."}
        
    last_active = status.get("last_active")
    if not last_active:
        return {"active": False, "message": "No active heartbeat recorded."}
        
    now = datetime.now(timezone.utc)
    if last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)
        
    diff = (now - last_active).total_seconds()
    is_active = diff < 30.0
    
    return {
        "active": is_active,
        "last_active": last_active.isoformat(),
        "diff_seconds": diff,
        "message": "Worker is active and polling." if is_active else "Worker seems to be stalled or offline."
    }


@router.get("")
async def list_campaigns(current_user: dict = Depends(get_current_user)):
    col = get_async_collection("campaigns")
    campaigns = await col.find().sort("createdAt", -1).to_list(length=1000)
    return {"campaigns": [_format_campaign(c) for c in campaigns]}


@router.post("", status_code=201)
async def create_campaign(
    body: CampaignCreateBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.name or not body.subject:
        raise HTTPException(status_code=400, detail="name and subject are required.")

    col = get_async_collection("campaigns")
    user_id = current_user["_id"]

    sched_start = None
    if body.scheduleStart:
        try:
            sched_start = datetime.fromisoformat(body.scheduleStart.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid scheduleStart timestamp format.")

    counters_col = get_async_collection("counters")
    counter_doc = await counters_col.find_one_and_update(
        {"_id": f"campaign_seq:{user_id}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    campaign_number = counter_doc.get("seq", 1) if counter_doc else 1

    doc = {
        "name": body.name,
        "description": body.description or "",
        "status": "draft",
        "subject": body.subject,
        "body": body.body or "",
        "senderEmail": body.senderEmail or "",
        "senderName": body.senderName or "",
        "dailyLimit": body.dailyLimit or 200,
        "timezone": body.timezone or "America/Chicago",
        "workingHoursOnly": body.workingHoursOnly or False,
        "scheduleStart": sched_start,
        "attachmentPath": body.attachmentPath or "",
        "attachmentFilename": body.attachmentFilename or "",
        "campaignNumber": campaign_number,
        "stats": {
            "totalSent": 0,
            "totalOpened": 0,
            "totalClicked": 0,
            "totalReplied": 0,
            "totalBounced": 0,
            "totalUnsubscribed": 0,
            "totalResent": 0
        },
        "createdBy": user_id,
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }

    result = await col.insert_one(doc)
    campaign = await col.find_one({"_id": result.inserted_id})

    audit_col = get_async_collection("audit_logs")
    await audit_col.insert_one({
        "action": "campaign.create",
        "entityType": "Campaign",
        "entityId": result.inserted_id,
        "performedBy": user_id,
        "createdAt": datetime.now(timezone.utc)
    })

    return {"campaign": _format_campaign(campaign)}


@router.post("/upload-attachment")
async def upload_campaign_attachment(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    import os
    import shutil
    try:
        os.makedirs("private/uploads", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        dest_path = os.path.join("private/uploads", filename)
        
        def save_file_sync():
            with open(dest_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

        await asyncio.to_thread(save_file_sync)
            
        return {
            "attachmentPath": dest_path,
            "attachmentFilename": file.filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")


@router.get("/view-file")
def view_campaign_file(path: str):
    import os
    from fastapi.responses import FileResponse

    allowed_bases = [
        os.path.realpath("private/uploads"),
        os.path.realpath("private/reports"),
    ]

    clean_path = path.replace("\\", "/").lstrip("/")
    resolved = os.path.realpath(clean_path)

    if not any(
        resolved == base or resolved.startswith(base + os.sep)
        for base in allowed_bases
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(resolved):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(resolved, media_type="application/pdf")


@router.get("/{id}")
async def get_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_async_collection("campaigns")
    campaign = await col.find_one({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return {"campaign": _format_campaign(campaign)}


@router.patch("/{id}")
async def update_campaign(
    id: str,
    body: CampaignUpdateBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_async_collection("campaigns")
    campaign = await col.find_one({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    if campaign.get("status") == "running":
        raise HTTPException(status_code=400, detail="Pause the campaign before editing it.")

    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.subject is not None:
        updates["subject"] = body.subject
    if body.body is not None:
        updates["body"] = body.body
    if body.senderEmail is not None:
        updates["senderEmail"] = body.senderEmail
    if body.senderName is not None:
        updates["senderName"] = body.senderName
    if body.dailyLimit is not None:
        updates["dailyLimit"] = body.dailyLimit
    if body.timezone is not None:
        updates["timezone"] = body.timezone
    if body.scheduleStart is not None:
        if body.scheduleStart:
            try:
                updates["scheduleStart"] = datetime.fromisoformat(body.scheduleStart.replace("Z", "+00:00"))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid scheduleStart format.")
    if body.workingHoursOnly is not None:
        updates["workingHoursOnly"] = body.workingHoursOnly
    if body.attachmentPath is not None:
        updates["attachmentPath"] = body.attachmentPath
    if body.attachmentFilename is not None:
        updates["attachmentFilename"] = body.attachmentFilename

    if updates:
        updates["updatedAt"] = datetime.now(timezone.utc)
        await col.update_one({"_id": oid}, {"$set": updates})
        campaign = await col.find_one({"_id": oid})

    return {"campaign": _format_campaign(campaign)}


@router.delete("/{id}")
async def delete_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_async_collection("campaigns")
    campaign = await col.find_one_and_delete({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    await get_async_collection("leads").delete_many({"campaignId": oid})

    audit_col = get_async_collection("audit_logs")
    await audit_col.insert_one({
        "action": "campaign.delete",
        "entityType": "Campaign",
        "entityId": oid,
        "performedBy": current_user["_id"],
        "createdAt": datetime.now(timezone.utc)
    })

    return {"ok": True}


@router.post("/{id}/duplicate", status_code=201)
async def duplicate_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_async_collection("campaigns")
    source = await col.find_one({"_id": oid})
    if not source:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    counters_col = get_async_collection("counters")
    counter_doc = await counters_col.find_one_and_update(
        {"_id": f"campaign_seq:{current_user['_id']}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    campaign_number = counter_doc.get("seq", 1) if counter_doc else 1

    doc = {
        "name": f"{source.get('name')} (copy)",
        "description": source.get("description", ""),
        "status": "draft",
        "subject": source.get("subject", ""),
        "body": source.get("body", ""),
        "senderEmail": source.get("senderEmail", ""),
        "senderName": source.get("senderName", ""),
        "dailyLimit": source.get("dailyLimit", 200),
        "timezone": source.get("timezone", "America/Chicago"),
        "scheduleStart": None,
        "campaignNumber": campaign_number,
        "stats": {
            "totalSent": 0,
            "totalOpened": 0,
            "totalClicked": 0,
            "totalReplied": 0,
            "totalBounced": 0,
            "totalUnsubscribed": 0,
            "totalResent": 0
        },
        "createdBy": current_user["_id"],
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }

    result = await col.insert_one(doc)
    copy = await col.find_one({"_id": result.inserted_id})
    return {"campaign": _format_campaign(copy)}


@router.post("/{id}/pause")
async def pause_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_async_collection("campaigns")
    await col.update_one(
        {"_id": oid},
        {"$set": {"status": "paused", "updatedAt": datetime.now(timezone.utc)}},
    )
    campaign = await col.find_one({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return {"campaign": _format_campaign(campaign)}


@router.post("/{id}/resume")
async def resume_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_async_collection("campaigns")
    campaign = await col.find_one({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    await col.update_one({"_id": oid}, {"$set": {"status": "running", "updatedAt": datetime.now(timezone.utc)}})
    campaign = await col.find_one({"_id": oid})
    daily_limit = (campaign or {}).get("dailyLimit", 200)

    queued = await _queue_pending_leads_async(oid, daily_limit)
    return {"campaign": _format_campaign(campaign), "queuedLeads": queued}


@router.post("/{id}/launch")
async def launch_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_async_collection("campaigns")
    campaign = await col.find_one({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    if campaign.get("status") == "running":
        raise HTTPException(status_code=400, detail="Campaign already running.")

    await col.update_one({"_id": oid}, {"$set": {"status": "running", "updatedAt": datetime.now(timezone.utc)}})
    campaign = await col.find_one({"_id": oid})
    daily_limit = (campaign or {}).get("dailyLimit", 200)

    queued = await _queue_pending_leads_async(oid, daily_limit)

    audit_col = get_async_collection("audit_logs")
    await audit_col.insert_one({
        "action": "campaign.launch",
        "entityType": "Campaign",
        "entityId": oid,
        "performedBy": current_user["_id"],
        "details": {"queuedLeads": queued},
        "createdAt": datetime.now(timezone.utc)
    })

    return {"campaign": _format_campaign(campaign), "queuedLeads": queued}
