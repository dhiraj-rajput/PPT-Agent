"""
app/routes/linkedin_campaigns.py
-----------------------------------
API routes for CRUD operations on LinkedIn Campaigns, target management,
and outgoing message queue approvals.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, insert, update, delete, func

from app.core.auth import get_current_user
from utils.db_client import get_db_session, _mysql_available
from models.sql_models import (
    LinkedInCampaign as SQL_LinkedInCampaign,
    LinkedInTarget as SQL_LinkedInTarget,
    Person as SQL_Person,
    LinkedInAccount as SQL_LinkedInAccount,
    LinkedInMessageLog as SQL_LinkedInMessageLog,
)

router = APIRouter(prefix="/linkedin/campaigns", tags=["linkedin-campaigns"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class CampaignCreateBody(BaseModel):
    name: str
    mode: str = "manual"  # "auto", "manual", "hybrid"
    role_filter: Optional[str] = ""
    message_generation_mode: str = "llm"  # "llm", "manual", "template"
    our_company_profile_id: Optional[int] = None
    connection_note_prompt: Optional[str] = ""
    followup_prompt: Optional[str] = ""
    require_approval: bool = True
    region_routing_rule: Optional[Dict[str, Any]] = None
    linkedin_account_id: Optional[int] = None


class CampaignUpdateBody(BaseModel):
    name: Optional[str] = None
    mode: Optional[str] = None
    role_filter: Optional[str] = None
    message_generation_mode: Optional[str] = None
    our_company_profile_id: Optional[int] = None
    connection_note_prompt: Optional[str] = None
    followup_prompt: Optional[str] = None
    require_approval: Optional[bool] = None
    region_routing_rule: Optional[Dict[str, Any]] = None
    status: Optional[str] = None  # "draft", "running", "paused", "completed"
    linkedin_account_id: Optional[int] = None


class TargetImportBody(BaseModel):
    person_ids: List[int]


class MessageReviewBody(BaseModel):
    content: str
    action: str  # "approve" | "reject" | "edit"
    scheduled_send_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_campaigns(current_user: dict = Depends(get_current_user)):
    """List all LinkedIn campaigns."""
    campaigns = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_LinkedInCampaign).order_by(SQL_LinkedInCampaign.created_at.desc())
                res = await db.execute(stmt)
                for c in res.scalars().all():
                    campaigns.append({
                        "id": c.id,
                        "user_id": c.user_id,
                        "name": c.name,
                        "mode": c.mode,
                        "role_filter": c.role_filter,
                        "message_generation_mode": c.message_generation_mode,
                        "our_company_profile_id": c.our_company_profile_id,
                        "connection_note_prompt": c.connection_note_prompt,
                        "followup_prompt": c.followup_prompt,
                        "region_routing_rule": c.region_routing_rule,
                        "require_approval": c.require_approval,
                        "status": c.status,
                        "linkedin_account_id": c.linkedin_account_id,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                    })
        except Exception as e:
            logger.error(f"Error listing LinkedIn campaigns: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"campaigns": campaigns}


@router.post("", status_code=201)
async def create_campaign(
    body: CampaignCreateBody,
    current_user: dict = Depends(get_current_user),
):
    """Create a new LinkedIn campaign."""
    if not body.name:
        raise HTTPException(status_code=400, detail="Campaign name is required.")

    user_id = int(current_user["id"])
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    if _mysql_available:
        try:
            async for db in get_db_session():
                new_camp = SQL_LinkedInCampaign(
                    user_id=user_id,
                    name=body.name,
                    mode=body.mode,
                    role_filter=body.role_filter or "",
                    message_generation_mode=body.message_generation_mode,
                    our_company_profile_id=body.our_company_profile_id,
                    connection_note_prompt=body.connection_note_prompt or "",
                    followup_prompt=body.followup_prompt or "",
                    region_routing_rule=body.region_routing_rule,
                    require_approval=body.require_approval,
                    status="draft",
                    linkedin_account_id=body.linkedin_account_id,
                    created_at=now_utc,
                    updated_at=now_utc
                )
                db.add(new_camp)
                await db.commit()
                await db.refresh(new_camp)
                
                return {
                    "id": new_camp.id,
                    "name": new_camp.name,
                    "status": new_camp.status,
                    "message": "LinkedIn campaign created successfully."
                }
        except Exception as e:
            logger.error(f"Error creating LinkedIn campaign: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"error": "Database not available"}


@router.get("/{id}")
async def get_campaign(
    id: int,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve detailed info for a single campaign."""
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_LinkedInCampaign).where(SQL_LinkedInCampaign.id == id)
                c = (await db.execute(stmt)).scalar_one_or_none()
                if not c:
                    raise HTTPException(status_code=404, detail="Campaign not found")

                return {
                    "id": c.id,
                    "user_id": c.user_id,
                    "name": c.name,
                    "mode": c.mode,
                    "role_filter": c.role_filter,
                    "message_generation_mode": c.message_generation_mode,
                    "our_company_profile_id": c.our_company_profile_id,
                    "connection_note_prompt": c.connection_note_prompt,
                    "followup_prompt": c.followup_prompt,
                    "region_routing_rule": c.region_routing_rule,
                    "require_approval": c.require_approval,
                    "status": c.status,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting LinkedIn campaign {id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"error": "Database not available"}


@router.patch("/{id}")
async def update_campaign(
    id: int,
    body: CampaignUpdateBody,
    current_user: dict = Depends(get_current_user),
):
    """Update a campaign's configuration."""
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_LinkedInCampaign).where(SQL_LinkedInCampaign.id == id)
                c = (await db.execute(stmt)).scalar_one_or_none()
                if not c:
                    raise HTTPException(status_code=404, detail="Campaign not found")

                # Apply updates
                if body.name is not None:
                    c.name = body.name
                if body.mode is not None:
                    c.mode = body.mode
                if body.role_filter is not None:
                    c.role_filter = body.role_filter
                if body.message_generation_mode is not None:
                    c.message_generation_mode = body.message_generation_mode
                if body.our_company_profile_id is not None:
                    c.our_company_profile_id = body.our_company_profile_id
                if body.connection_note_prompt is not None:
                    c.connection_note_prompt = body.connection_note_prompt
                if body.followup_prompt is not None:
                    c.followup_prompt = body.followup_prompt
                if body.require_approval is not None:
                    c.require_approval = body.require_approval
                if body.region_routing_rule is not None:
                    c.region_routing_rule = body.region_routing_rule
                if body.status is not None:
                    c.status = body.status
                
                c.updated_at = datetime.utcnow()
                await db.commit()
                return {"status": "success", "message": "Campaign updated successfully."}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating LinkedIn campaign {id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"error": "Database not available"}


@router.delete("/{id}")
async def delete_campaign(
    id: int,
    current_user: dict = Depends(get_current_user),
):
    """Delete a campaign."""
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_LinkedInCampaign).where(SQL_LinkedInCampaign.id == id)
                c = (await db.execute(stmt)).scalar_one_or_none()
                if not c:
                    raise HTTPException(status_code=404, detail="Campaign not found")

                await db.delete(c)
                await db.commit()
                return {"status": "success", "message": "Campaign deleted successfully."}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting LinkedIn campaign {id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"error": "Database not available"}


@router.post("/{id}/import-targets")
async def import_targets(
    id: int,
    person_ids: Optional[str] = Form(None),  # Comma separated list of IDs, e.g. "1,2,3"
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
):
    """Import targets into a campaign from a CSV file or list of CRM people IDs."""
    if _mysql_available:
        try:
            async for db in get_db_session():
                # Validate campaign
                stmt = select(SQL_LinkedInCampaign).where(SQL_LinkedInCampaign.id == id)
                c = (await db.execute(stmt)).scalar_one_or_none()
                if not c:
                    raise HTTPException(status_code=404, detail="Campaign not found")

                target_people_ids = []

                # Parse manual ID list
                if person_ids:
                    try:
                        ids = [int(p.strip()) for p in person_ids.split(",") if p.strip()]
                        target_people_ids.extend(ids)
                    except ValueError:
                        raise HTTPException(status_code=400, detail="Invalid person_ids format.")

                # Parse uploaded file
                if file:
                    contents = await file.read()
                    try:
                        try:
                            content_str = contents.decode("utf-8-sig")
                        except UnicodeDecodeError:
                            content_str = contents.decode("latin-1")
                        reader = csv.DictReader(io.StringIO(content_str))
                        if reader.fieldnames:
                            reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
                        rows = list(reader)
                    except Exception as ex:
                        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {ex}")

                    for r in rows:
                        full_name = r.get("name") or r.get("full_name") or r.get("full name") or ""
                        first_name = r.get("first_name") or r.get("first name") or ""
                        last_name = r.get("last_name") or r.get("last name") or ""
                        if not full_name and (first_name or last_name):
                            full_name = f"{first_name} {last_name}".strip()
                        
                        linkedin_url = r.get("linkedin") or r.get("linkedin_url") or r.get("linkedin url") or ""
                        title = r.get("title") or r.get("role") or ""
                        org = r.get("company") or r.get("company_name") or r.get("organization") or ""

                        if not full_name or not linkedin_url:
                            continue

                        # Check if person already exists in CRM via linkedin_url
                        stmt_person = select(SQL_Person).where(SQL_Person.linkedin_url == linkedin_url)
                        person = (await db.execute(stmt_person)).scalar_one_or_none()

                        if not person:
                            person = SQL_Person(
                                full_name=full_name,
                                first_name=first_name,
                                last_name=last_name,
                                title=title,
                                organization_name=org,
                                linkedin_url=linkedin_url,
                                source="LinkedIn Campaign Upload"
                            )
                            db.add(person)
                            await db.flush()  # populate ID
                        
                        target_people_ids.append(person.id)

                if not target_people_ids:
                    return {"status": "success", "imported": 0, "message": "No targets imported."}

                # Link IDs to targets in this campaign
                imported_count = 0
                for p_id in target_people_ids:
                    # Check if already added to this campaign
                    stmt_exists = select(SQL_LinkedInTarget).where(
                        SQL_LinkedInTarget.campaign_id == id,
                        SQL_LinkedInTarget.person_id == p_id
                    )
                    exists = (await db.execute(stmt_exists)).scalar_one_or_none()
                    if not exists:
                        # Fetch person to evaluate seniority target
                        stmt_p = select(SQL_Person).where(SQL_Person.id == p_id)
                        person_obj = (await db.execute(stmt_p)).scalar_one_or_none()
                        
                        new_target = SQL_LinkedInTarget(
                            person_id=p_id,
                            campaign_id=id,
                            seniority_target=person_obj.seniority if person_obj else None,
                            scrape_status="pending",
                            connection_status="not_sent"
                        )
                        db.add(new_target)
                        imported_count += 1
                
                await db.commit()
                return {
                    "status": "success",
                    "imported": imported_count,
                    "message": f"Successfully imported {imported_count} targets."
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error importing targets to LinkedIn campaign {id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"error": "Database not available"}


@router.get("/{id}/targets")
async def get_campaign_targets(
    id: int,
    scrape_status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve all targets linked to a campaign, matching criteria."""
    targets_list = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_LinkedInTarget).where(SQL_LinkedInTarget.campaign_id == id)
                if scrape_status:
                    stmt = stmt.where(SQL_LinkedInTarget.scrape_status == scrape_status)
                
                res = await db.execute(stmt)
                for t in res.scalars().all():
                    # Joined details
                    stmt_p = select(SQL_Person).where(SQL_Person.id == t.person_id)
                    p = (await db.execute(stmt_p)).scalar_one_or_none()
                    
                    targets_list.append({
                        "id": t.id,
                        "person_id": t.person_id,
                        "campaign_id": t.campaign_id,
                        "assigned_account_id": t.assigned_account_id,
                        "seniority_target": t.seniority_target,
                        "scrape_status": t.scrape_status,
                        "scraped_profile_json": t.scraped_profile_json,
                        "connection_status": t.connection_status,
                        "last_action_at": t.last_action_at.isoformat() if t.last_action_at else None,
                        "person": {
                            "id": p.id,
                            "full_name": p.full_name,
                            "title": p.title,
                            "organization_name": p.organization_name,
                            "linkedin_url": p.linkedin_url,
                        } if p else None
                    })
        except Exception as e:
            logger.error(f"Error getting targets for campaign {id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"targets": targets_list}


@router.get("/{id}/queue")
async def get_campaign_queue(
    id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get the list of messages in this campaign needing review/approval."""
    queue = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_LinkedInMessageLog).where(
                    SQL_LinkedInMessageLog.campaign_id == id,
                    SQL_LinkedInMessageLog.status == "needs_review",
                    SQL_LinkedInMessageLog.direction == "out"
                )
                res = await db.execute(stmt)
                for m in res.scalars().all():
                    # Target info
                    stmt_t = select(SQL_LinkedInTarget).where(SQL_LinkedInTarget.id == m.target_id)
                    target = (await db.execute(stmt_t)).scalar_one_or_none()
                    person = None
                    if target:
                        stmt_p = select(SQL_Person).where(SQL_Person.id == target.person_id)
                        person = (await db.execute(stmt_p)).scalar_one_or_none()

                    queue.append({
                        "id": m.id,
                        "target_id": m.target_id,
                        "campaign_id": m.campaign_id,
                        "account_id_used": m.account_id_used,
                        "direction": m.direction,
                        "content": m.content,
                        "generated_by": m.generated_by,
                        "status": m.status,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                        "target": {
                            "id": target.id if target else None,
                            "connection_status": target.connection_status if target else None,
                            "person": {
                                "id": person.id,
                                "full_name": person.full_name,
                                "title": person.title,
                                "organization_name": person.organization_name,
                            } if person else None
                        }
                    })
        except Exception as e:
            logger.error(f"Error getting queue for campaign {id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"queue": queue}


@router.post("/messages/{message_id}/review")
async def review_message(
    message_id: int,
    body: MessageReviewBody,
    current_user: dict = Depends(get_current_user),
):
    """Approve, reject, or edit a message in the approval queue."""
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_LinkedInMessageLog).where(SQL_LinkedInMessageLog.id == message_id)
                m = (await db.execute(stmt)).scalar_one_or_none()
                if not m:
                    raise HTTPException(status_code=404, detail="Message not found")

                if body.action == "approve":
                    m.status = "approved"
                    m.content = body.content
                    m.sent_at = None
                    if body.scheduled_send_at:
                        try:
                            clean_str = body.scheduled_send_at.replace("Z", "+00:00")
                            m.scheduled_send_at = datetime.fromisoformat(clean_str).replace(tzinfo=None)
                        except Exception as parse_err:
                            logger.warning(f"Failed to parse scheduled_send_at '{body.scheduled_send_at}': {parse_err}")
                            m.scheduled_send_at = None
                    else:
                        m.scheduled_send_at = None
                elif body.action == "reject":
                    m.status = "failed"
                elif body.action == "edit":
                    m.content = body.content
                else:
                    raise HTTPException(status_code=400, detail="Invalid action value")
                
                await db.commit()
                return {
                    "status": "success",
                    "message": f"Message review action '{body.action}' completed successfully."
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error reviewing message {message_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"error": "Database not available"}
