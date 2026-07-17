from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
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
    scheduleStart: Optional[str] = None


class CampaignUpdateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    senderEmail: Optional[str] = None
    senderName: Optional[str] = None
    dailyLimit: Optional[int] = None
    timezone: Optional[str] = None
    scheduleStart: Optional[str] = None


def _format_campaign(c: dict) -> dict:
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
        "scheduleStart": c.get("scheduleStart").isoformat() if c.get("scheduleStart") else None,
        "stats": c.get("stats", {
            "totalSent": 0,
            "totalOpened": 0,
            "totalClicked": 0,
            "totalReplied": 0,
            "totalBounced": 0,
            "totalUnsubscribed": 0
        }),
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


@router.get("")
def list_campaigns(current_user: dict = Depends(get_current_user)):
    col = get_collection("campaigns")
    user_id = current_user["_id"]
    campaigns = list(col.find({"createdBy": user_id}).sort("createdAt", -1))
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
        "scheduleStart": sched_start,
        "stats": {
            "totalSent": 0,
            "totalOpened": 0,
            "totalClicked": 0,
            "totalReplied": 0,
            "totalBounced": 0,
            "totalUnsubscribed": 0
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


@router.get("/{id}")
def get_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    col = get_collection("campaigns")
    campaign = col.find_one({"_id": oid, "createdBy": current_user["_id"]})
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
    campaign = col.find_one({"_id": oid, "createdBy": current_user["_id"]})
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
        else:
            updates["scheduleStart"] = None

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
    campaign = col.find_one_and_delete({"_id": oid, "createdBy": current_user["_id"]})
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
    source = col.find_one({"_id": oid, "createdBy": current_user["_id"]})
    if not source:
        raise HTTPException(status_code=404, detail="Campaign not found.")

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
        "stats": {
            "totalSent": 0,
            "totalOpened": 0,
            "totalClicked": 0,
            "totalReplied": 0,
            "totalBounced": 0,
            "totalUnsubscribed": 0
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
        {"_id": oid, "createdBy": current_user["_id"]},
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
    campaign = col.find_one({"_id": oid, "createdBy": current_user["_id"]})
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
    campaign = col.find_one({"_id": oid, "createdBy": current_user["_id"]})
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
