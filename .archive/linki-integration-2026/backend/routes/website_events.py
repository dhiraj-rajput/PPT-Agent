"""
app/routes/website_events.py
-----------------------------
Visitor tracking events from pixel / JS snippet — using MySQL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.db_client import get_db_session, _mysql_available
from app.core.email_worker import add_score, SCORE_RULES
from models.sql_models import (
    WebsiteEvent as SQL_WebsiteEvent,
    Lead as SQL_Lead,
    Campaign as SQL_Campaign,
)
from sqlalchemy import select, update, insert, delete

router = APIRouter(prefix="/website-events", tags=["website-events"])

VALID_EVENT_TYPES = {"page_view", "scroll", "button_click", "form_submit"}


class WebsiteEventBody(BaseModel):
    leadId: Optional[str] = None
    campaignId: Optional[str] = None
    visitorId: Optional[str] = ""
    page: Optional[str] = ""
    duration: Optional[float] = 0.0
    eventType: str
    meta: Optional[Any] = None


def score_for_website_event(event_type: str, page: str = "", duration: float = 0.0) -> int:
    if event_type == "form_submit":
        return SCORE_RULES["formSubmitted"]
    if event_type == "page_view":
        p = page.lower()
        if "pricing" in p:
            return SCORE_RULES["pricingPageViewed"]
        if "case-stud" in p or "case_stud" in p:
            return SCORE_RULES["caseStudiesViewed"]
        return SCORE_RULES["websiteVisited"]
    if event_type == "button_click":
        return 0
    if event_type == "scroll" and duration > 300:
        return SCORE_RULES["stayedOver5Min"]
    return 0


@router.post("")
async def log_website_event(body: WebsiteEventBody):
    if body.eventType not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"eventType must be one of: {', '.join(VALID_EVENT_TYPES)}"
        )

    lead_id = None
    campaign_id = None

    if not _mysql_available:
        raise HTTPException(status_code=500, detail="Database is unavailable.")

    async for db in get_db_session():
        if body.leadId:
            try:
                lead_id = int(body.leadId)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid lead ID.")
            
            stmt = select(SQL_Lead).where(SQL_Lead.id == lead_id)
            lead = (await db.execute(stmt)).scalar_one_or_none()
            if not lead:
                raise HTTPException(status_code=404, detail="Lead not found.")

        if body.campaignId:
            try:
                campaign_id = int(body.campaignId)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid campaign ID.")
            
            stmt_c = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
            camp = (await db.execute(stmt_c)).scalar_one_or_none()
            if not camp:
                raise HTTPException(status_code=404, detail="Campaign not found.")

        # Insert event
        new_event = SQL_WebsiteEvent(
            session_id="",
            visitor_id=body.visitorId or "",
            campaign_id=campaign_id,
            lead_id=lead_id,
            event_type=body.eventType,
            page_url=body.page or "",
            referrer="",
            ip_address="",
            user_agent="",
            extra_data=body.meta or {},
            duration=int(body.duration or 0.0),
            created_at=datetime.utcnow()
        )
        db.add(new_event)
        await db.commit()
        await db.refresh(new_event)
        event_id = str(new_event.id)

        if lead_id:
            points = score_for_website_event(body.eventType, body.page or "", body.duration or 0.0)
            if points > 0:
                add_score(lead_id, points)

            if body.eventType == "form_submit":
                await db.execute(
                    update(SQL_Lead)
                    .where(SQL_Lead.id == lead_id, ~SQL_Lead.status.in_(["replied", "unsubscribed"]))
                    .values(status="clicked", updated_at=datetime.utcnow())
                )
                await db.commit()

    return {"ok": True, "eventId": event_id}
