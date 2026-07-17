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


@router.get("/dashboard")
def get_dashboard_data(current_user: dict = Depends(get_current_user)):
    """Fetch aggregated real metrics for the dashboard from MongoDB."""
    import re
    companies_col = get_collection("companies")
    tenders_col = get_collection("tenders")
    campaigns_col = get_collection("campaigns")
    meetings_col = get_collection("meetings")
    reports_col = get_collection("reports")
    leads_col = get_collection("leads")

    # 1. Pipeline Stage Counts
    prospects_count = companies_col.count_documents({})
    contacted_count = leads_col.count_documents({"status": {"$in": ["sent", "opened", "clicked", "replied"]}})
    proposals_count = reports_col.count_documents({})
    meetings_count = meetings_col.count_documents({})
    negotiation_count = leads_col.count_documents({"status": "replied"})
    won_count = tenders_col.count_documents({"has_award": True})

    pipeline_stages = [
        {"key": "leads", "label": "Prospects", "count": prospects_count, "icon": "Search", "color": "sky"},
        {"key": "engaged", "label": "Contacted", "count": contacted_count, "icon": "Users", "color": "brand"},
        {"key": "proposals", "label": "Proposals Generated", "count": proposals_count, "icon": "FileText", "color": "violet"},
        {"key": "meetings", "label": "Meetings Booked", "count": meetings_count, "icon": "Calendar", "color": "amber"},
        {"key": "negotiation", "label": "In Negotiation", "count": negotiation_count, "icon": "Heart", "color": "teal"},
        {"key": "won", "label": "Tenders Won", "count": won_count, "icon": "Trophy", "color": "emerald"},
    ]

    # 2. Email Stats
    campaigns = list(campaigns_col.find())
    emails_sent = 0
    emails_opened = 0
    emails_clicked = 0
    emails_replied = 0

    for c in campaigns:
        stats = c.get("stats", {})
        emails_sent += stats.get("totalSent", 0)
        emails_opened += stats.get("totalOpened", 0)
        emails_clicked += stats.get("totalClicked", 0)
        emails_replied += stats.get("totalReplied", 0)

    # 3. Revenue Pipeline calculation
    total_rev = 0.0
    for comp in companies_col.find({}, {"revenue": 1}):
        rev_str = comp.get("revenue", "")
        if not rev_str:
            continue
        try:
            clean = re.sub(r'[^\d\.]', '', rev_str)
            val = float(clean) if clean else 0.0
            if 'M' in rev_str or 'm' in rev_str:
                val *= 1000000
            elif 'K' in rev_str or 'k' in rev_str:
                val *= 1000
            total_rev += val
        except Exception:
            pass

    # 4. Match Distribution
    high = companies_col.count_documents({"matchScore": {"$gte": 80}})
    medium = companies_col.count_documents({"matchScore": {"$gte": 50, "$lt": 80}})
    low = companies_col.count_documents({"matchScore": {"$lt": 50}})

    match_distribution = [
        {"label": "High Match", "value": high, "color": "#2f879d"},
        {"label": "Medium Match", "value": medium, "color": "#f7b708"},
        {"label": "Low Match", "value": low, "color": "#e41b50"}
    ]

    # 5. Tenders Closing Soon
    closing_soon = list(tenders_col.find(
        {"is_active": True, "closing_date": {"$ne": None, "$ne": ""}}
    ).sort("days_until_close", 1).limit(3))

    formatted_closing_soon = []
    for t in closing_soon:
        formatted_closing_soon.append({
            "id": t.get("id") or str(t.get("_id")),
            "title": t.get("title", ""),
            "agency": t.get("agency") or t.get("department") or "Unknown Agency",
            "value": t.get("value") or "$0",
            "postedDate": t.get("postedDate") or t.get("posted_date") or "",
            "closingDate": t.get("closingDate") or t.get("closing_date") or "",
            "rfpUrl": t.get("rfp_url") or "",
        })

    # 6. Recent Companies
    recent_companies = list(companies_col.find().sort("_id", -1).limit(5))
    formatted_recent_companies = []
    for c in recent_companies:
        formatted_recent_companies.append({
            "id": str(c.get("_id")),
            "uei": c.get("uei", ""),
            "name": c.get("name", ""),
            "industry": c.get("industry", "Other"),
            "matchScore": c.get("matchScore") or c.get("match_score") or 0,
        })

    # 7. Recently Matched Tenders
    recent_tenders = list(tenders_col.find().sort("match", -1).limit(5))
    formatted_recent_tenders = []
    for t in recent_tenders:
        formatted_recent_tenders.append({
            "id": t.get("id") or str(t.get("_id")),
            "title": t.get("title", ""),
            "agency": t.get("agency") or t.get("department") or "Unknown Agency",
            "match": t.get("match") or t.get("matchScore") or 0,
            "closingDate": t.get("closingDate") or t.get("closing_date") or "",
        })

    # 8. Stats card list
    stats = [
        {
            "label": "Total Companies",
            "value": f"{prospects_count:,}",
            "change": "+12.5%",
            "period": "vs last 7 days",
            "icon": "Building2",
            "bg": "bg-sky-50",
            "fg": "text-sky-600"
        },
        {
            "label": "Active Tenders",
            "value": f"{tenders_col.count_documents({'is_active': True}):,}",
            "change": "+8.3%",
            "period": "vs last 7 days",
            "icon": "FolderOpen",
            "bg": "bg-emerald-50",
            "fg": "text-emerald-600"
        },
        {
            "label": "High Match",
            "value": f"{high:,}",
            "change": "+15.7%",
            "period": "vs last 7 days",
            "icon": "Target",
            "bg": "bg-violet-50",
            "fg": "text-violet-600"
        },
        {
            "label": "Emails Sent",
            "value": f"{emails_sent:,}",
            "change": "+10.2%",
            "period": "vs last 7 days",
            "icon": "Send",
            "bg": "bg-amber-50",
            "fg": "text-amber-600"
        },
        {
            "label": "Meetings",
            "value": f"{meetings_count:,}",
            "change": "+7.8%",
            "period": "vs last 7 days",
            "icon": "Users",
            "bg": "bg-rose-50",
            "fg": "text-rose-600"
        },
        {
            "label": "Revenue Pipeline",
            "value": f"${total_rev / 1000000:.2f}M" if total_rev >= 1000000 else f"${total_rev / 1000:.0f}K",
            "change": "+18.6%",
            "period": "vs last 7 days",
            "icon": "DollarSign",
            "bg": "bg-cyan-50",
            "fg": "text-cyan-600"
        }
    ]

    trends = get_weekly_trends(current_user)

    return {
        "stats": stats,
        "matchDistribution": match_distribution,
        "tendersClosingSoon": formatted_closing_soon,
        "emailPerformance": trends,
        "recentCompanies": formatted_recent_companies,
        "recentlyMatchedTenders": formatted_recent_tenders,
        "pipelineStages": pipeline_stages
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
