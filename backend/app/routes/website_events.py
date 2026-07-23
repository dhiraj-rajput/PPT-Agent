from datetime import datetime, timezone
from typing import Optional, Any
from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.db_client import get_collection
from app.core.email_worker import add_score, SCORE_RULES

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
def log_website_event(body: WebsiteEventBody):
    if body.eventType not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"eventType must be one of: {', '.join(VALID_EVENT_TYPES)}"
        )

    lead_oid = None
    lead = None
    if body.leadId:
        try:
            lead_oid = ObjectId(body.leadId)
            leads_col = get_collection("leads")
            lead = leads_col.find_one({"_id": lead_oid})
            if not lead:
                raise HTTPException(status_code=404, detail="Lead not found.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid lead ID.")

    camp_oid = None
    if body.campaignId:
        try:
            camp_oid = ObjectId(body.campaignId)
            campaigns_col = get_collection("campaigns")
            if not campaigns_col.find_one({"_id": camp_oid}):
                raise HTTPException(status_code=404, detail="Campaign not found.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    doc = {
        "leadId": lead_oid,
        "campaignId": camp_oid,
        "visitorId": body.visitorId or "",
        "page": body.page or "",
        "duration": body.duration or 0.0,
        "eventType": body.eventType,
        "meta": body.meta or {},
        "timestamp": datetime.now(timezone.utc),
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }

    events_col = get_collection("website_events")
    result = events_col.insert_one(doc)

    if lead_oid:
        points = score_for_website_event(body.eventType, body.page or "", body.duration or 0.0)
        if points > 0:
            add_score(lead_oid, points)

        if body.eventType == "form_submit":
            leads_col = get_collection("leads")
            leads_col.update_one(
                {"_id": lead_oid, "status": {"$nin": ["replied", "unsubscribed"]}},
                {"$set": {"status": "clicked", "updatedAt": datetime.now(timezone.utc)}}
            )

    return {"ok": True, "eventId": str(result.inserted_id)}
