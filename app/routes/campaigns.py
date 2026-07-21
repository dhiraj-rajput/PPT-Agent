from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from utils.db_client import get_collection

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


def _format_campaign(c: dict) -> dict:
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
        "scheduleStart": c.get("scheduleStart").isoformat() if c.get("scheduleStart") else None,
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
        "createdAt": c.get("createdAt").isoformat() if c.get("createdAt") else None,
        "updatedAt": c.get("updatedAt").isoformat() if c.get("updatedAt") else None,
    }


def _queue_pending_leads(campaign_id: ObjectId, daily_limit: int):
    """Calculate and assign send_after timestamps spacing out leads across the day."""
    leads_col = get_collection("leads")
    pending = list(leads_col.find({"campaignId": campaign_id, "status": "pending"}, {"_id": 1}))
    if not pending:
        return 0

    now = datetime.now(timezone.utc)
    limit = daily_limit or 200
    spacing_ms = max(int((24 * 60 * 60 * 1000) / limit), 1000)

    for i, lead in enumerate(pending):
        if i >= limit:
            break
        send_after = now + timedelta(milliseconds=i * spacing_ms)
        leads_col.update_one(
            {"_id": lead["_id"]},
            {"$set": {"send_after": send_after}}
        )
    return min(len(pending), limit)


@router.get("/worker-status")
def get_worker_status(current_user: dict = Depends(get_current_user)):
    """Check if the background email campaign worker is active."""
    col = get_collection("system_status")
    status = col.find_one({"key": "email_worker"})
    if not status:
        return {"active": False, "message": "Worker has never been started."}
        
    last_active = status.get("last_active")
    if not last_active:
        return {"active": False, "message": "No active heartbeat recorded."}
        
    # Check if last_active is within 30 seconds
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
def list_campaigns(current_user: dict = Depends(get_current_user)):
    col = get_collection("campaigns")
    campaigns = list(col.find().sort("createdAt", -1))
    return {"campaigns": [_format_campaign(c) for c in campaigns]}


@router.post("", status_code=201)
def create_campaign(
    body: CampaignCreateBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.name or not body.subject:
        raise HTTPException(status_code=400, detail="name and subject are required.")

    col = get_collection("campaigns")
    user_id = current_user["_id"]

    sched_start = None
    if body.scheduleStart:
        try:
            sched_start = datetime.fromisoformat(body.scheduleStart.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid scheduleStart timestamp format.")

    # Atomically assign the next campaign number so the UI can show a
    # running "Campaign #N" counter.
    counters_col = get_collection("counters")
    counter_doc = counters_col.find_one_and_update(
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

    result = col.insert_one(doc)
    campaign = col.find_one({"_id": result.inserted_id})

    # Log action in audit logs
    get_collection("audit_logs").insert_one({
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
        
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
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

    # Resolve to a real absolute path and verify it is actually contained
    # within one of the allowed directories. A plain string-prefix check on
    # the raw path (the previous approach) can be bypassed with "../"
    # sequences that still start with the right string but resolve outside
    # the allowed folder — this endpoint is intentionally public (email
    # recipients open it without logging in), so that containment check has
    # to be airtight.
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
def get_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_collection("campaigns")
    campaign = col.find_one({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return {"campaign": _format_campaign(campaign)}


@router.patch("/{id}")
def update_campaign(
    id: str,
    body: CampaignUpdateBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_collection("campaigns")
    campaign = col.find_one({"_id": oid})
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
        col.update_one({"_id": oid}, {"$set": updates})
        campaign = col.find_one({"_id": oid})

    return {"campaign": _format_campaign(campaign)}


@router.delete("/{id}")
def delete_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_collection("campaigns")
    campaign = col.find_one_and_delete({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    # Delete all associated leads
    get_collection("leads").delete_many({"campaignId": oid})

    # Log action
    get_collection("audit_logs").insert_one({
        "action": "campaign.delete",
        "entityType": "Campaign",
        "entityId": oid,
        "performedBy": current_user["_id"],
        "createdAt": datetime.now(timezone.utc)
    })

    return {"ok": True}


@router.post("/{id}/duplicate", status_code=201)
def duplicate_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_collection("campaigns")
    source = col.find_one({"_id": oid})
    if not source:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    counters_col = get_collection("counters")
    counter_doc = counters_col.find_one_and_update(
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

    result = col.insert_one(doc)
    copy = col.find_one({"_id": result.inserted_id})
    return {"campaign": _format_campaign(copy)}


@router.post("/{id}/pause")
def pause_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_collection("campaigns")
    campaign = col.find_one_and_update(
        {"_id": oid},
        {"$set": {"status": "paused", "updatedAt": datetime.now(timezone.utc)}},
        return_document=True
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return {"campaign": _format_campaign(campaign)}


@router.post("/{id}/resume")
def resume_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_collection("campaigns")
    campaign = col.find_one({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    col.update_one({"_id": oid}, {"$set": {"status": "running", "updatedAt": datetime.now(timezone.utc)}})
    campaign = col.find_one({"_id": oid})

    queued = _queue_pending_leads(oid, campaign.get("dailyLimit", 200))
    return {"campaign": _format_campaign(campaign), "queuedLeads": queued}


@router.post("/{id}/launch")
def launch_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_collection("campaigns")
    campaign = col.find_one({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    if campaign.get("status") == "running":
        raise HTTPException(status_code=400, detail="Campaign already running.")

    col.update_one({"_id": oid}, {"$set": {"status": "running", "updatedAt": datetime.now(timezone.utc)}})
    campaign = col.find_one({"_id": oid})

    queued = _queue_pending_leads(oid, campaign.get("dailyLimit", 200))

    # Log action
    get_collection("audit_logs").insert_one({
        "action": "campaign.launch",
        "entityType": "Campaign",
        "entityId": oid,
        "performedBy": current_user["_id"],
        "details": {"queuedLeads": queued},
        "createdAt": datetime.now(timezone.utc)
    })

    return {"campaign": _format_campaign(campaign), "queuedLeads": queued}

