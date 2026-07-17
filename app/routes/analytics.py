from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from utils.db_client import get_collection

router = APIRouter(prefix="/analytics", tags=["analytics"])

DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def _calculate_rates(stats: dict) -> dict:
    sent = stats.get("totalSent", 0)
    def pct(n):
        return round((n / sent) * 100, 1) if sent > 0 else 0.0

    return {
        "totalSent": sent,
        "openRate": pct(stats.get("totalOpened", 0)),
        "clickRate": pct(stats.get("totalClicked", 0)),
        "replyRate": pct(stats.get("totalReplied", 0)),
        "bounceRate": pct(stats.get("totalBounced", 0)),
        "unsubscribeRate": pct(stats.get("totalUnsubscribed", 0)),
    }


@router.get("/overview")
def get_overview(current_user: dict = Depends(get_current_user)):
    campaigns_col = get_collection("campaigns")
    leads_col = get_collection("leads")
    user_id = current_user["_id"]

    campaigns = list(campaigns_col.find({"createdBy": user_id}))

    totals = {
        "totalSent": 0,
        "totalOpened": 0,
        "totalClicked": 0,
        "totalReplied": 0,
        "totalBounced": 0,
        "totalUnsubscribed": 0
    }

    for c in campaigns:
        stats = c.get("stats", {})
        totals["totalSent"] += stats.get("totalSent", 0)
        totals["totalOpened"] += stats.get("totalOpened", 0)
        totals["totalClicked"] += stats.get("totalClicked", 0)
        totals["totalReplied"] += stats.get("totalReplied", 0)
        totals["totalBounced"] += stats.get("totalBounced", 0)
        totals["totalUnsubscribed"] += stats.get("totalUnsubscribed", 0)

    conversions = leads_col.count_documents({
        "createdBy": user_id,
        "status": "replied"
    })

    rates = _calculate_rates(totals)
    sent = totals["totalSent"]
    conversion_rate = round((conversions / sent) * 100, 1) if sent > 0 else 0.0

    return {
        **rates,
        "conversionRate": conversion_rate,
        "activeCampaigns": sum(1 for c in campaigns if c.get("status") == "running"),
        "totalCampaigns": len(campaigns),
    }


@router.get("/campaign/{id}")
def get_campaign_analytics(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    campaigns_col = get_collection("campaigns")
    campaign = campaigns_col.find_one({"_id": oid, "createdBy": current_user["_id"]})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    leads_col = get_collection("leads")
    pipeline = [
        {"$match": {"campaignId": oid}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    lead_counts = list(leads_col.aggregate(pipeline))
    by_status = {r["_id"]: r["count"] for r in lead_counts}

    rates = _calculate_rates(campaign.get("stats", {}))

    return {
        "campaignId": str(campaign["_id"]),
        "name": campaign.get("name", ""),
        "status": campaign.get("status", "draft"),
        **rates,
        "leadsByStatus": by_status,
    }


@router.get("/trends")
def get_weekly_trends(current_user: dict = Depends(get_current_user)):
    campaigns_col = get_collection("campaigns")
    leads_col = get_collection("leads")
    user_id = current_user["_id"]

    campaigns = list(campaigns_col.find({"createdBy": user_id}, {"_id": 1}))
    campaign_ids = [c["_id"] for c in campaigns]

    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)

    # Fetch leads updated in the last 7 days
    leads = list(leads_col.find(
        {"campaignId": {"$in": campaign_ids}, "updatedAt": {"$gte": since}},
        {"sentAt": 1, "openedAt": 1, "clickedAt": 1, "repliedAt": 1}
    ))

    # Initialize buckets for the last 7 days
    buckets = {}
    for i in range(7):
        d = since + timedelta(days=i)
        key = d.isoformat()[:10]  # "YYYY-MM-DD"
        day_index = int(d.strftime("%w"))  # 0 = Sunday
        buckets[key] = {
            "day": DAY_LABELS[day_index],
            "sent": 0,
            "opened": 0,
            "clicked": 0,
            "replied": 0
        }

    def bump(dt: Optional[datetime], field: str):
        if not dt:
            return
        # Handle tz-naive or tz-aware correctly
        dt_utc = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        key = dt_utc.isoformat()[:10]
        if key in buckets:
            buckets[key][field] += 1

    for lead in leads:
        bump(lead.get("sentAt"), "sent")
        bump(lead.get("openedAt"), "opened")
        bump(lead.get("clickedAt"), "clicked")
        bump(lead.get("repliedAt"), "replied")

    sorted_keys = sorted(buckets.keys())
    return [buckets[k] for k in sorted_keys]


@router.get("/website-engagement")
def get_website_engagement(current_user: dict = Depends(get_current_user)):
    campaigns_col = get_collection("campaigns")
    events_col = get_collection("website_events")
    user_id = current_user["_id"]

    campaigns = list(campaigns_col.find({"createdBy": user_id}, {"_id": 1, "name": 1}))
    campaign_ids = [c["_id"] for c in campaigns]
    name_by_id = {str(c["_id"]): c["name"] for c in campaigns}

    pipeline = [
        {"$match": {"campaignId": {"$in": campaign_ids}}},
        {
            "$group": {
                "_id": "$campaignId",
                "pageViews": {"$sum": {"$cond": [{"$eq": ["$eventType", "page_view"]}, 1, 0]}},
                "formSubmits": {"$sum": {"$cond": [{"$eq": ["$eventType", "form_submit"]}, 1, 0]}},
                "avgDuration": {"$avg": "$duration"},
                "uniqueVisitors": {"$addToSet": "$visitorId"}
            }
        }
    ]

    rows = list(events_col.aggregate(pipeline))

    results = []
    for r in rows:
        camp_str_id = str(r["_id"])
        visitors = r.get("uniqueVisitors", [])
        unique_count = len([v for v in visitors if v])
        results.append({
            "campaignId": camp_str_id,
            "campaignName": name_by_id.get(camp_str_id, "Unknown campaign"),
            "pageViews": r.get("pageViews", 0),
            "formSubmits": r.get("formSubmits", 0),
            "avgDuration": round(r.get("avgDuration") or 0.0),
            "uniqueVisitors": unique_count,
        })

    return results
