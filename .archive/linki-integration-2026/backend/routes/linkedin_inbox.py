"""
app/routes/linkedin_inbox.py
------------------------------
Unified LinkedIn inbox routes for displaying incoming replies across all accounts
and queuing manual responses.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, insert, update, delete, func

from app.core.auth import get_current_user
from utils.db_client import get_db_session, _mysql_available
from models.sql_models import (
    LinkedInMessageLog as SQL_LinkedInMessageLog,
    LinkedInTarget as SQL_LinkedInTarget,
    Person as SQL_Person,
    LinkedInCampaign as SQL_LinkedInCampaign,
    LinkedInReplyClassification as SQL_LinkedInReplyClassification,
)

router = APIRouter(prefix="/linkedin/inbox", tags=["linkedin-inbox"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class SendReplyBody(BaseModel):
    target_id: int
    content: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def get_unified_inbox(
    current_user: dict = Depends(get_current_user),
):
    """
    Get all incoming messages across campaigns for accounts owned by this user.
    """
    inbox_messages = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                # Get campaigns created by this user
                user_id = int(current_user["id"])
                stmt_camps = select(SQL_LinkedInCampaign.id).where(SQL_LinkedInCampaign.user_id == user_id)
                camp_ids = (await db.execute(stmt_camps)).scalars().all()
                
                if not camp_ids:
                    return {"inbox": []}

                # Query incoming messages (direction="in") for these campaigns
                stmt = (
                    select(SQL_LinkedInMessageLog)
                    .where(
                        SQL_LinkedInMessageLog.campaign_id.in_(camp_ids),
                        SQL_LinkedInMessageLog.direction == "in"
                    )
                    .order_by(SQL_LinkedInMessageLog.created_at.desc())
                )
                res = await db.execute(stmt)
                
                for m in res.scalars().all():
                    # Joined details
                    stmt_t = select(SQL_LinkedInTarget).where(SQL_LinkedInTarget.id == m.target_id)
                    target = (await db.execute(stmt_t)).scalar_one_or_none()
                    
                    person = None
                    if target:
                        stmt_p = select(SQL_Person).where(SQL_Person.id == target.person_id)
                        person = (await db.execute(stmt_p)).scalar_one_or_none()

                    # Check for intent classifications
                    stmt_class = select(SQL_LinkedInReplyClassification).where(
                        SQL_LinkedInReplyClassification.message_log_id == m.id
                    )
                    classification = (await db.execute(stmt_class)).scalar_one_or_none()

                    inbox_messages.append({
                        "id": m.id,
                        "target_id": m.target_id,
                        "campaign_id": m.campaign_id,
                        "account_id_used": m.account_id_used,
                        "direction": m.direction,
                        "content": m.content,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                        "target": {
                            "id": target.id if target else None,
                            "connection_status": target.connection_status if target else None,
                            "person": {
                                "id": person.id,
                                "full_name": person.full_name,
                                "title": person.title,
                                "organization_name": person.organization_name,
                                "linkedin_url": person.linkedin_url,
                            } if person else None
                        } if target else None,
                        "classification": {
                            "intent": classification.intent,
                            "confidence": float(classification.confidence or 0.0),
                            "suggested_next_action": classification.suggested_next_action,
                        } if classification else None
                    })
        except Exception as e:
            logger.error(f"Error retrieving unified LinkedIn inbox: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"inbox": inbox_messages}


@router.post("/reply")
async def send_manual_reply(
    body: SendReplyBody,
    current_user: dict = Depends(get_current_user),
):
    """
    Queue a manual reply for sending.
    Inserts an outgoing log with status='approved' (or 'queued') which the sender worker will execute.
    """
    if not body.content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                # Validate and retrieve target info
                stmt_t = select(SQL_LinkedInTarget).where(SQL_LinkedInTarget.id == body.target_id)
                target = (await db.execute(stmt_t)).scalar_one_or_none()
                if not target:
                    raise HTTPException(status_code=404, detail="Target prospect not found.")

                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

                # Queue the outgoing message
                m = SQL_LinkedInMessageLog(
                    target_id=target.id,
                    campaign_id=target.campaign_id,
                    account_id_used=target.assigned_account_id,
                    direction="out",
                    content=body.content,
                    generated_by="manual",
                    status="queued",  # Queued for worker execution
                    created_at=now_utc
                )
                db.add(m)
                await db.commit()
                return {
                    "status": "success",
                    "message": "Manual reply queued for sending.",
                    "message_id": m.id
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error queuing manual LinkedIn reply: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"error": "Database not available"}
