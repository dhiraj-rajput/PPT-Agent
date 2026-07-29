"""
app/routes/campaigns.py
-------------------------
Campaign management & execution endpoints using MySQL.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import get_db_session, _mysql_available
from models.sql_models import (
    Campaign as SQL_Campaign,
    Lead as SQL_Lead,
    AuditLog as SQL_AuditLog,
    SystemStatus as SQL_SystemStatus,
)
from sqlalchemy import select, insert, update, delete, func

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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


def _format_campaign(c: SQL_Campaign) -> dict:
    if not c:
        return {}
    stats = c.stats or {}
    return {
        "id": str(c.id),
        "name": c.name or "",
        "description": c.description or "",
        "status": c.status or "draft",
        "subject": c.subject or "",
        "body": c.body or "",
        "senderEmail": c.sender_email or "",
        "senderName": c.sender_name or "",
        "dailyLimit": c.daily_limit or 200,
        "timezone": c.timezone or "America/Chicago",
        "workingHoursOnly": bool(c.working_hours_only),
        "scheduleStart": _iso(c.schedule_start),
        "attachmentPath": getattr(c, "attachment_path", "") or "",
        "attachmentFilename": getattr(c, "attachment_filename", "") or "",
        "campaignNumber": getattr(c, "campaign_number", 0) or 0,

        "stats": {
            "totalSent": stats.get("totalSent", 0),
            "totalOpened": stats.get("totalOpened", 0),
            "totalClicked": stats.get("totalClicked", 0),
            "totalReplied": stats.get("totalReplied", 0),
            "totalBounced": stats.get("totalBounced", 0),
            "totalUnsubscribed": stats.get("totalUnsubscribed", 0),
            "totalResent": stats.get("totalResent", 0),
        },
        "createdAt": _iso(c.created_at),
        "updatedAt": _iso(c.updated_at),
    }


async def _queue_pending_leads_async(campaign_id: int, daily_limit: int, base_time: Optional[datetime] = None):
    """Calculate and assign send_after timestamps spacing out leads across the day in MySQL."""
    if not _mysql_available:
        return 0

    async for db in get_db_session():
        # Get all pending leads
        stmt = select(SQL_Lead).where(SQL_Lead.campaign_id == campaign_id, SQL_Lead.status == "pending")
        res = await db.execute(stmt)
        pending = res.scalars().all()
        if not pending:
            return 0

        now = datetime.now(timezone.utc)
        start = base_time if (base_time and base_time > now) else now
        limit = daily_limit or 200
        spacing_ms = max(int((24 * 60 * 60 * 1000) / limit), 1000)

        for i, lead in enumerate(pending):
            if i >= limit:
                break
            send_after = start + timedelta(milliseconds=i * spacing_ms)
            await db.execute(
                update(SQL_Lead)
                .where(SQL_Lead.id == lead.id)
                .values(send_after=send_after)
            )
        await db.commit()
        return min(len(pending), limit)


@router.get("/worker-status")
async def get_worker_status(current_user: dict = Depends(get_current_user)):
    """Check if the background email campaign worker is active."""
    if not _mysql_available:
        return {"active": False, "message": "MySQL database is not connected."}

    async for db in get_db_session():
        stmt = select(SQL_SystemStatus).where(SQL_SystemStatus.key_name == "email_worker")
        res = await db.execute(stmt)
        status = res.scalar_one_or_none()
        if not status:
            return {"active": False, "message": "Worker has never been started."}
            
        last_active = getattr(status, "last_active", None)
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
    campaigns = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Campaign).order_by(SQL_Campaign.created_at.desc())
                res = await db.execute(stmt)
                campaigns = [_format_campaign(c) for c in res.scalars().all()]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"campaigns": campaigns}


@router.post("", status_code=201)
async def create_campaign(
    body: CampaignCreateBody,
    current_user: dict = Depends(get_current_user),
):
    if not body.name or not body.subject:
        raise HTTPException(status_code=400, detail="name and subject are required.")

    user_id = int(current_user["id"])

    sched_start = None
    if body.scheduleStart:
        try:
            sched_start = datetime.fromisoformat(body.scheduleStart.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid scheduleStart timestamp format.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                # campaign seq count
                stmt_count = select(func.count()).select_from(SQL_Campaign).where(SQL_Campaign.user_id == user_id)
                campaign_number = ((await db.execute(stmt_count)).scalar() or 0) + 1
                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

                stmt = insert(SQL_Campaign).values(
                    user_id=user_id,
                    name=body.name,
                    description=body.description or "",
                    status="draft",
                    subject=body.subject,
                    body=body.body or "",
                    sender_email=body.senderEmail or "",
                    sender_name=body.senderName or "",
                    daily_limit=body.dailyLimit or 200,
                    timezone=body.timezone or "America/Chicago",
                    working_hours_only=body.workingHoursOnly or False,
                    schedule_start=sched_start,
                    attachment_path=body.attachmentPath or "",
                    attachment_filename=body.attachmentFilename or "",
                    campaign_number=str(campaign_number),
                    stats={
                        "totalSent": 0,
                        "totalOpened": 0,
                        "totalClicked": 0,
                        "totalReplied": 0,
                        "totalBounced": 0,
                        "totalUnsubscribed": 0,
                        "totalResent": 0
                    },
                    created_at=now_utc,
                    updated_at=now_utc
                )
                await db.execute(stmt)
                await db.commit()

                new_c = (await db.execute(select(SQL_Campaign).where(SQL_Campaign.name == body.name, SQL_Campaign.user_id == user_id).order_by(SQL_Campaign.id.desc()))).scalar_one()
                campaign_id = new_c.id


                # Audit Log
                await db.execute(insert(SQL_AuditLog).values(
                    action="campaign.create",
                    entity_type="Campaign",
                    entity_id=str(campaign_id),
                    performed_by=user_id,
                    created_at=datetime.utcnow()
                ))
                await db.commit()

                # fetch campaign
                stmt_new = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                campaign_obj = (await db.execute(stmt_new)).scalar_one()
                return {"campaign": _format_campaign(campaign_obj)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


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
def view_campaign_file(path: str, current_user: dict = Depends(get_current_user)):
    import os
    from fastapi.responses import FileResponse

    allowed_bases = [
        os.path.realpath(str(PROJECT_ROOT / "private" / "uploads")),
        os.path.realpath(str(PROJECT_ROOT / "private" / "reports")),
        os.path.realpath(str(PROJECT_ROOT / "output" / "pdf")),
        os.path.realpath(str(PROJECT_ROOT / "output" / "rfp_respond")),
    ]

    # Handle if path is relative
    clean_path = path.replace("\\", "/").lstrip("/")
    if not os.path.isabs(clean_path):
        resolved = os.path.realpath(str(PROJECT_ROOT / clean_path))
    else:
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
        campaign_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                res = await db.execute(stmt)
                campaign = res.scalar_one_or_none()
                if not campaign:
                    raise HTTPException(status_code=404, detail="Campaign not found.")
                return {"campaign": _format_campaign(campaign)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


@router.patch("/{id}")
async def update_campaign(
    id: str,
    body: CampaignUpdateBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        campaign_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                res = await db.execute(stmt)
                campaign = res.scalar_one_or_none()
                if not campaign:
                    raise HTTPException(status_code=404, detail="Campaign not found.")

                if getattr(campaign, "status", "") == "running":
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
                    updates["sender_email"] = body.senderEmail
                if body.senderName is not None:
                    updates["sender_name"] = body.senderName
                if body.dailyLimit is not None:
                    updates["daily_limit"] = body.dailyLimit
                if body.timezone is not None:
                    updates["timezone"] = body.timezone
                if body.scheduleStart is not None:
                    if body.scheduleStart:
                        try:
                            updates["schedule_start"] = datetime.fromisoformat(body.scheduleStart.replace("Z", "+00:00"))
                        except Exception:
                            raise HTTPException(status_code=400, detail="Invalid scheduleStart format.")
                if body.workingHoursOnly is not None:
                    updates["working_hours_only"] = body.workingHoursOnly
                if body.attachmentPath is not None:
                    updates["attachment_path"] = body.attachmentPath
                if body.attachmentFilename is not None:
                    updates["attachment_filename"] = body.attachmentFilename

                if updates:
                    await db.execute(
                        update(SQL_Campaign)
                        .where(SQL_Campaign.id == campaign_id)
                        .values(**updates, updated_at=datetime.utcnow())
                    )
                    await db.commit()

                    # refetch
                    stmt_new = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                    campaign = (await db.execute(stmt_new)).scalar_one()

                return {"campaign": _format_campaign(campaign)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


@router.delete("/{id}")
async def delete_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        campaign_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                res = await db.execute(stmt)
                campaign = res.scalar_one_or_none()
                if not campaign:
                    raise HTTPException(status_code=404, detail="Campaign not found.")

                await db.execute(delete(SQL_Campaign).where(SQL_Campaign.id == campaign_id))
                await db.execute(delete(SQL_Lead).where(SQL_Lead.campaign_id == campaign_id))

                await db.execute(insert(SQL_AuditLog).values(
                    action="campaign.delete",
                    entity_type="Campaign",
                    entity_id=str(campaign_id),
                    performed_by=int(current_user["id"]),
                    created_at=datetime.utcnow()
                ))
                await db.commit()
                return {"ok": True}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


@router.post("/{id}/duplicate", status_code=201)
async def duplicate_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        campaign_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    user_id = int(current_user["id"])

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                res = await db.execute(stmt)
                source = res.scalar_one_or_none()
                if not source:
                    raise HTTPException(status_code=404, detail="Campaign not found.")

                # Campaign number
                stmt_count = select(func.count()).select_from(SQL_Campaign).where(SQL_Campaign.user_id == user_id)
                cnt = (await db.execute(stmt_count)).scalar() or 0
                campaign_number = cnt + 1

                dup_name = f"{source.name} (copy)"
                stmt_insert = insert(SQL_Campaign).values(
                    user_id=user_id,
                    name=dup_name,
                    description=source.description or "",
                    status="draft",
                    subject=source.subject or "",
                    body=source.body or "",
                    sender_email=source.sender_email or "",
                    sender_name=source.sender_name or "",
                    daily_limit=source.daily_limit or 200,
                    timezone=source.timezone or "America/Chicago",
                    working_hours_only=source.working_hours_only or False,
                    schedule_start=None,
                    attachment_path=getattr(source, "attachment_path", "") or "",
                    attachment_filename=getattr(source, "attachment_filename", "") or "",
                    campaign_number=campaign_number,
                    stats={
                        "totalSent": 0,
                        "totalOpened": 0,
                        "totalClicked": 0,
                        "totalReplied": 0,
                        "totalBounced": 0,
                        "totalUnsubscribed": 0,
                        "totalResent": 0
                    },
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                await db.execute(stmt_insert)
                await db.commit()

                stmt_new = select(SQL_Campaign).where(SQL_Campaign.user_id == user_id, SQL_Campaign.name == dup_name)
                copy = (await db.execute(stmt_new)).scalar_one()
                return {"campaign": _format_campaign(copy)}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


@router.post("/{id}/pause")
async def pause_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        campaign_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                res = await db.execute(stmt)
                campaign = res.scalar_one_or_none()
                if not campaign:
                    raise HTTPException(status_code=404, detail="Campaign not found.")

                await db.execute(
                    update(SQL_Campaign)
                    .where(SQL_Campaign.id == campaign_id)
                    .values(status="paused", updated_at=datetime.utcnow())
                )
                await db.commit()

                # refetch
                stmt_new = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                campaign = (await db.execute(stmt_new)).scalar_one()
                return {"campaign": _format_campaign(campaign)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


@router.post("/{id}/resume")
async def resume_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        campaign_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                res = await db.execute(stmt)
                campaign = res.scalar_one_or_none()
                if not campaign:
                    raise HTTPException(status_code=404, detail="Campaign not found.")

                await db.execute(
                    update(SQL_Campaign)
                    .where(SQL_Campaign.id == campaign_id)
                    .values(status="running", updated_at=datetime.utcnow())
                )
                await db.commit()

                daily_limit = int(str(getattr(campaign, "daily_limit", 200) or 200))
                schedule_start = getattr(campaign, "schedule_start", None)
                base_time_val = schedule_start if isinstance(schedule_start, datetime) else None

                queued = await _queue_pending_leads_async(campaign_id, daily_limit, base_time=base_time_val)
                
                # refetch
                stmt_new = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                refetched = (await db.execute(stmt_new)).scalar_one()
                return {"campaign": _format_campaign(refetched), "queuedLeads": queued}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


@router.post("/{id}/launch")
async def launch_campaign(id: str, current_user: dict = Depends(get_current_user)):
    try:
        campaign_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                res = await db.execute(stmt)
                campaign = res.scalar_one_or_none()
                if not campaign:
                    raise HTTPException(status_code=404, detail="Campaign not found.")

                if getattr(campaign, "status", "") == "running":
                    raise HTTPException(status_code=400, detail="Campaign already running.")

                await db.execute(
                    update(SQL_Campaign)
                    .where(SQL_Campaign.id == campaign_id)
                    .values(status="running", updated_at=datetime.utcnow())
                )
                await db.commit()

                daily_limit = int(str(getattr(campaign, "daily_limit", 200) or 200))
                schedule_start = getattr(campaign, "schedule_start", None)
                base_time_val = schedule_start if isinstance(schedule_start, datetime) else None

                queued = await _queue_pending_leads_async(campaign_id, daily_limit, base_time=base_time_val)


                # Audit Log
                await db.execute(insert(SQL_AuditLog).values(
                    action="campaign.launch",
                    entity_type="Campaign",
                    entity_id=str(campaign_id),
                    performed_by=int(current_user["id"]),
                    details={"queuedLeads": queued},
                    created_at=datetime.utcnow()
                ))
                await db.commit()

                # refetch
                stmt_new = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                refetched = (await db.execute(stmt_new)).scalar_one()
                return {"campaign": _format_campaign(refetched), "queuedLeads": queued}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")
