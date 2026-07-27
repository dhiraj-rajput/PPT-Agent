"""
app/routes/tenders.py
---------------------
Tenders API — SAM.gov Opportunities v2 integration with Motor MongoDB caching.

SAM.gov Opportunities API: https://api.sam.gov/opportunities/v2/search
Entity Management API (companies): https://api.sam.gov/entity-information/v3/entities

Strategy:
  - MongoDB (Motor async) is the single source of truth. The frontend never hits SAM.gov directly.
  - SAM.gov is only called when the cache is empty OR the user triggers a manual sync.
  - Cached results include computed lifecycle status (Open / Closing Soon / Expired / Won).

Endpoints:
  GET  /api/tenders          — list cached tenders (search + filter locally in Mongo)
  GET  /api/tenders/meta     — sync metadata (last_synced, count, quota_used)
  POST /api/tenders/sync     — fetch fresh data from SAM.gov and cache it
  GET  /api/tenders/{id}     — single tender detail by noticeId
  POST /api/tenders/{id}/request-draft  — "Ask for Project (Draft)" button
"""

from __future__ import annotations

import asyncio
import logging
import re
import httpx

logger = logging.getLogger(__name__)
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse

from utils.db_client import get_async_collection, get_collection
from config.settings import settings
from app.core.auth import get_current_user

def _sanitize_path_component(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip('_. ')

router = APIRouter(prefix="/tenders", tags=["tenders"])

SAM_OPPORTUNITIES_BASE = getattr(settings, "SAM_GOV_API_URL", "https://api.sam.gov/opportunities/v2/search")


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_match_score(notice_id: str, naics_code: str = "", title: str = "", summary: str = "") -> int:
    try:
        from app.core.match_engine import compute_tender_match_score
        return compute_tender_match_score(notice_id=notice_id, title=title, summary=summary, naics_code=naics_code)
    except Exception:
        return 0


def _format_place_of_performance(pop: Any) -> str:
    if not pop:
        return ""
    if isinstance(pop, str):
        return pop
    if isinstance(pop, dict):
        city = pop.get("city")
        city_str = (city.get("name") or city.get("code")) if isinstance(city, dict) else str(city or "")
        state = pop.get("state")
        state_str = (state.get("code") or state.get("name")) if isinstance(state, dict) else str(state or "")
        country = pop.get("country")
        country_str = (country.get("name") or country.get("code")) if isinstance(country, dict) else str(country or "")
        zip_val = pop.get("zip")
        zip_str = (zip_val.get("code") or zip_val.get("name")) if isinstance(zip_val, dict) else str(zip_val or "")
        
        street = pop.get("streetAddress") or pop.get("address") or ""
        parts = [p for p in [street, city_str, state_str, zip_str, country_str] if p]
        if parts:
            return ", ".join(parts)
        vals = [str(v) for v in pop.values() if v and not isinstance(v, (dict, list))]
        if vals:
            return ", ".join(vals)
    return ""


def _compute_lifecycle(
    closing_date_str: str,
    active_flag: str,
    award_date_str: str = "",
    award_amount: float = 0.0,
) -> dict:
    now = datetime.now(tz=timezone.utc)

    closing_dt = None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
    ):
        try:
            raw = closing_date_str.strip() if closing_date_str else ""
            if not raw:
                break
            if raw.endswith("Z"):
                raw_try = raw[:-1] + "+00:00"
            else:
                raw_try = raw
            try:
                closing_dt = datetime.fromisoformat(raw_try)
                if closing_dt.tzinfo is None:
                    closing_dt = closing_dt.replace(tzinfo=timezone.utc)
                break
            except ValueError:
                closing_dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                break
        except Exception:
            pass

    has_award = bool(award_amount > 0 or award_date_str)
    if has_award:
        return {
            "status": "Won",
            "days_until_close": 0,
            "is_active": False,
            "has_award": True,
            "urgency": "won",
        }

    if not closing_dt:
        is_active = active_flag.strip().lower() in ("yes", "y", "true", "active")
        return {
            "status": "Open" if is_active else "Closed",
            "days_until_close": 999 if is_active else 0,
            "is_active": is_active,
            "has_award": False,
            "urgency": "normal" if is_active else "expired",
        }

    diff_days = (closing_dt - now).days

    if diff_days < 0:
        return {
            "status": "Expired",
            "days_until_close": diff_days,
            "is_active": False,
            "has_award": False,
            "urgency": "expired",
        }
    elif diff_days <= 7:
        return {
            "status": "Closing Soon",
            "days_until_close": diff_days,
            "is_active": True,
            "has_award": False,
            "urgency": "critical",
        }
    elif diff_days <= 30:
        return {
            "status": "Closing Soon",
            "days_until_close": diff_days,
            "is_active": True,
            "has_award": False,
            "urgency": "warning",
        }
    else:
        return {
            "status": "Open",
            "days_until_close": diff_days,
            "is_active": True,
            "has_award": False,
            "urgency": "normal",
        }


def _map_opportunity(opp: dict) -> dict:
    notice_id = opp.get("noticeId") or opp.get("_id") or ""
    sol_num = opp.get("solicitationNumber") or opp.get("solnum") or ""
    title = opp.get("title") or opp.get("subject") or "Untitled Opportunity"

    naics = opp.get("naicsCode") or opp.get("naics") or ""
    if isinstance(naics, list):
        naics = naics[0] if naics else ""

    dept = (
        opp.get("fullParentPathName")
        or opp.get("department")
        or opp.get("agency")
        or "U.S. Federal Government"
    )

    set_aside_code = opp.get("typeOfSetAsideCode") or opp.get("setAside") or ""
    set_aside_desc = opp.get("typeOfSetAside") or set_aside_code or "Unrestricted"

    award_info = opp.get("award") or {}
    award_amount = float(award_info.get("amount") or 0.0)
    award_date = award_info.get("date") or ""
    award_awardee = (award_info.get("awardee") or {}).get("name") or ""

    closing = (
        opp.get("responseDeadLine")
        or opp.get("closeDate")
        or opp.get("archiveDate")
        or ""
    )
    active_flag = str(opp.get("active") or "Yes")

    lifecycle = _compute_lifecycle(
        closing_date_str=closing,
        active_flag=active_flag,
        award_date_str=award_date,
        award_amount=award_amount,
    )

    posted = opp.get("postedDate") or opp.get("publishDate") or ""
    if posted and len(posted) >= 10:
        posted_fmt = posted[:10]
    else:
        posted_fmt = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    closing_fmt = ""
    if closing and len(closing) >= 10:
        closing_fmt = closing[:10]

    pocs = opp.get("pointOfContact") or []
    poc_name = ""
    poc_email = ""
    poc_phone = ""
    if pocs and isinstance(pocs, list):
        p0 = pocs[0]
        poc_name = p0.get("fullName") or p0.get("title") or ""
        poc_email = p0.get("email") or ""
        poc_phone = p0.get("phone") or ""

    summary = opp.get("description") or opp.get("synopsis") or ""

    match_score = _compute_match_score(
        notice_id=notice_id,
        naics_code=str(naics),
        title=title,
        summary=summary,
    )

    return {
        "id": notice_id,
        "noticeId": notice_id,
        "title": title,
        "solicitation_number": sol_num,
        "agency": dept,
        "department": dept,
        "naics_code": str(naics),
        "set_aside": set_aside_desc,
        "set_aside_code": set_aside_code,
        "type": opp.get("type") or "Solicitation",
        "postedDate": posted_fmt,
        "posted_date": posted_fmt,
        "closingDate": closing_fmt,
        "closing_date": closing_fmt,
        "days_until_close": lifecycle["days_until_close"],
        "status": lifecycle["status"],
        "urgency": lifecycle["urgency"],
        "is_active": lifecycle["is_active"],
        "has_award": lifecycle["has_award"],
        "award_amount": award_amount,
        "award_date": award_date[:10] if award_date else "",
        "award_awardee": award_awardee,
        "match": match_score,
        "matchScore": match_score,
        "rfp_url": opp.get("uiLink") or f"https://sam.gov/opp/{notice_id}/view",
        "summary": summary[:2000],
        "poc_name": poc_name,
        "poc_email": poc_email,
        "poc_phone": poc_phone,
        "place_of_performance": _format_place_of_performance(opp.get("placeOfPerformance")),
        "updatedAt": _utc_now_iso(),
    }


@router.get("/meta")
async def get_tenders_meta(current_user: dict = Depends(get_current_user)):
    meta_col = get_async_collection("tenders_meta")
    tenders_col = get_async_collection("tenders")

    meta = await meta_col.find_one({}) or {}
    total_cached = await tenders_col.count_documents({})
    active_cached = await tenders_col.count_documents({"is_active": True})

    return {
        "total_cached": total_cached,
        "active_cached": active_cached,
        "last_synced": meta.get("last_synced"),
        "quota_used_today": meta.get("quota_used_today", 0),
        "quota_max_daily": 10,
    }


@router.get("")
async def get_tenders(
    q: Optional[str] = None,
    naics: Optional[str] = None,
    set_aside: Optional[str] = None,
    status: Optional[str] = None,
    urgency: Optional[str] = None,
    has_award: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    try:
        col = get_async_collection("tenders")
        total_cached = await col.count_documents({})

        filter_q = {}
        and_conditions = []

        if q:
            escaped_q = re.escape(q.strip())
            and_conditions.append({
                "$or": [
                    {"title": {"$regex": escaped_q, "$options": "i"}},
                    {"solicitation_number": {"$regex": escaped_q, "$options": "i"}},
                    {"agency": {"$regex": escaped_q, "$options": "i"}},
                    {"department": {"$regex": escaped_q, "$options": "i"}},
                    {"summary": {"$regex": escaped_q, "$options": "i"}},
                    {"naics_code": {"$regex": escaped_q, "$options": "i"}},
                ]
            })

        if naics and naics.upper() != "ALL":
            and_conditions.append({"naics_code": {"$regex": re.escape(naics.strip()), "$options": "i"}})

        if set_aside and set_aside.upper() != "ALL":
            and_conditions.append({"$or": [
                {"set_aside_code": {"$regex": re.escape(set_aside.strip()), "$options": "i"}},
                {"set_aside": {"$regex": re.escape(set_aside.strip()), "$options": "i"}},
            ]})

        if status and status.upper() != "ALL":
            and_conditions.append({"status": status})

        if urgency and urgency.upper() != "ALL":
            and_conditions.append({"urgency": urgency})

        if has_award is not None:
            and_conditions.append({"has_award": has_award})

        if and_conditions:
            filter_q["$and"] = and_conditions

        total = await col.count_documents(filter_q)
        skip = (page - 1) * limit
        results = await col.find(filter_q, {"_id": 0}).skip(skip).limit(limit).to_list(length=limit)

        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        status_counts_cursor = col.aggregate(pipeline)
        status_counts_raw = await status_counts_cursor.to_list(length=100)
        status_counts = {s["_id"]: s["count"] for s in status_counts_raw if s.get("_id")}

        naics_codes = sorted([n for n in await col.distinct("naics_code") if n])[:100]
        set_aside_opts = sorted([s for s in await col.distinct("set_aside") if s])[:50]

        return {
            "total": total,
            "total_cached": total_cached,
            "page": page,
            "limit": limit,
            "tenders": results,
            "cache_empty": total_cached == 0,
            "naics_codes": naics_codes,
            "set_aside_options": set_aside_opts,
            "status_counts": status_counts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_tenders_from_sam(
    payload: dict = {},
    current_user: dict = Depends(get_current_user),
):
    api_key = settings.SAM_GOV_API_KEY
    force_mock = settings.FORCE_MOCK_SAM_GOV

    if not force_mock:
        meta_col = get_async_collection("tenders_meta")
        meta = await meta_col.find_one({}) or {}
        last_synced_str = meta.get("last_synced")
        if last_synced_str:
            try:
                cleaned_str = last_synced_str.replace("Z", "+00:00")
                last_synced_dt = datetime.fromisoformat(cleaned_str)
                now = datetime.now(timezone.utc)
                elapsed = now - last_synced_dt
                cooldown_hours = 24
                if elapsed < timedelta(hours=cooldown_hours):
                    remaining = timedelta(hours=cooldown_hours) - elapsed
                    hours, remainder = divmod(remaining.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit: Manual SAM.gov sync is on a 24-hour cooldown. Please try again in {hours}h {minutes}m."
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"[Tenders] Cooldown parse warning: {e}")

    if not api_key and not force_mock:
        raise HTTPException(
            status_code=503,
            detail="SAM_GOV_API_KEY is not set. Add it to your .env file.",
        )

    params: dict = {
        "api_key": api_key,
        "limit": min(int(payload.get("limit", 25)), 25),
        "offset": int(payload.get("offset", 0)),
        "active": payload.get("active", "Yes"),
    }

    if payload.get("naicsCode"):
        params["naicsCode"] = payload["naicsCode"].strip()
    if payload.get("keyword"):
        params["keyword"] = payload["keyword"].strip()
    if payload.get("typeOfSetAsideCode"):
        params["typeOfSetAsideCode"] = payload["typeOfSetAsideCode"].strip()
    if payload.get("postedFrom"):
        params["postedFrom"] = payload["postedFrom"].strip()
    if payload.get("postedTo"):
        params["postedTo"] = payload["postedTo"].strip()

    if not force_mock:
        if not params.get("postedFrom"):
            params["postedFrom"] = (datetime.now(tz=timezone.utc) - timedelta(days=90)).strftime("%m/%d/%Y")
        if not params.get("postedTo"):
            params["postedTo"] = datetime.now(tz=timezone.utc).strftime("%m/%d/%Y")

    params = {k: v for k, v in params.items() if v not in (None, "")}

    if force_mock:
        return await _insert_mock_tenders_async(params)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(SAM_OPPORTUNITIES_BASE, params=params)

        if resp.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail=(
                    "SAM.gov rate limit reached (10 requests/day on free tier). "
                    "Register a SAM.gov role at sam.gov/workspace to unlock 1,000 req/day. "
                    "Your cached tenders are still available."
                ),
            )
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="SAM.gov API key is invalid or expired.")
        if resp.status_code == 403:
            raise HTTPException(
                status_code=403,
                detail="SAM.gov returned 403 Forbidden. Check that your API key is a real SAM.gov key (not DEMO_KEY).",
            )
        if not resp.is_success:
            raise HTTPException(
                status_code=502,
                detail=f"SAM.gov returned HTTP {resp.status_code}: {resp.text[:400]}",
            )

        data = resp.json()
        opportunities = (
            data.get("opportunitiesData")
            or data.get("_embedded", {}).get("results", [])
            or []
        )
        total_in_sam = data.get("totalRecords", 0)

        if not opportunities:
            return {
                "status": "ok",
                "fetched": 0,
                "upserted": 0,
                "total_in_sam": total_in_sam,
                "message": (
                    "SAM.gov returned 0 results for these parameters. "
                    "Try broadening the search (fewer filters, wider date range)."
                ),
            }

        return await _upsert_tenders_async(opportunities, params)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SAM.gov request failed: {e}")


async def _upsert_tenders_async(opportunities: list, sync_params: dict, is_mock: bool = False) -> dict:
    tenders_col = get_async_collection("tenders")
    meta_col = get_async_collection("tenders_meta")
    upserted = 0

    for opp in opportunities:
        mapped = _map_opportunity(opp)
        if not mapped.get("id"):
            continue
        mapped["raw_sam_data"] = opp
        if is_mock:
            mapped["_data_source"] = "mock"
        await tenders_col.update_one(
            {"id": mapped["id"]},
            {"$set": mapped},
            upsert=True,
        )
        upserted += 1

    await meta_col.update_one(
        {},
        {
            "$set": {
                "last_synced": _utc_now_iso(),
                "last_sync_params": {
                    k: v for k, v in sync_params.items() if k != "api_key"
                },
            },
            "$inc": {"quota_used_today": 1},
        },
        upsert=True,
    )

    await _refresh_expired_statuses_async(tenders_col)

    return {
        "status": "ok",
        "fetched": len(opportunities),
        "upserted": upserted,
        "message": (
            f"Successfully cached {upserted} tenders from SAM.gov. "
            "Results are stored permanently — no need to sync again unless you want fresher data."
        ),
    }


async def _refresh_expired_statuses_async(col) -> None:
    now = datetime.now(tz=timezone.utc)
    cutoff = now.strftime("%Y-%m-%d")
    try:
        await col.update_many(
            {
                "closing_date": {"$lt": cutoff, "$ne": ""},
                "status": {"$nin": ["Won", "Expired"]},
            },
            {"$set": {"status": "Expired", "urgency": "expired", "is_active": False}},
        )
        in_7_days = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        await col.update_many(
            {
                "closing_date": {"$gte": cutoff, "$lte": in_7_days},
                "status": "Open",
            },
            {"$set": {"status": "Closing Soon", "urgency": "critical"}},
        )
        in_30_days = (now + timedelta(days=30)).strftime("%Y-%m-%d")
        await col.update_many(
            {
                "closing_date": {"$gt": in_7_days, "$lte": in_30_days},
                "status": "Open",
            },
            {"$set": {"status": "Closing Soon", "urgency": "warning"}},
        )
    except Exception as e:
        logger.warning(f"[Tenders] Warning: lifecycle refresh failed: {e}")


async def _insert_mock_tenders_async(params: dict) -> dict:
    now = datetime.now(tz=timezone.utc)
    mock_raw = [
        {
            "noticeId": "MOCK-OPEN-001",
            "title": "AI-Powered Technical Proposal Platform",
            "solicitationNumber": "N00164-26-R-0001",
            "fullParentPathName": "DEPT OF COMMERCE.NIST",
            "naicsCode": params.get("naicsCode", "541511"),
            "type": "Solicitation",
            "typeOfSetAsideCode": "SBA",
            "typeOfSetAside": "Small Business Set-Aside",
            "award": {},
            "postedDate": "2026-05-10T00:00:00-05:00",
            "responseDeadLine": (now + timedelta(days=45)).strftime("%Y-%m-%dT00:00:00Z"),
            "active": "Yes",
            "uiLink": "https://sam.gov/opp/MOCK-OPEN-001/view",
            "description": "Seeking a qualified vendor to build an ML pipeline that parses and analyzes Government RFP PDFs, extracts requirements, and auto-drafts compliant responses.",
            "pointOfContact": [{"type": "primary", "fullName": "Jane Contracting Officer", "email": "jane.co@nist.gov", "phone": "301-975-0000"}],
            "placeOfPerformance": {"city": {"name": "Gaithersburg"}, "state": {"code": "MD"}},
        },
        {
            "noticeId": "MOCK-SOON-002",
            "title": "Cybersecurity Zero-Trust Network Upgrade",
            "solicitationNumber": "FAA-26-CY-0088",
            "fullParentPathName": "DEPT OF TRANSPORTATION.FAA",
            "naicsCode": params.get("naicsCode", "541512"),
            "type": "Solicitation",
            "typeOfSetAsideCode": "",
            "typeOfSetAside": "Unrestricted",
            "award": {},
            "postedDate": "2026-05-15T00:00:00-05:00",
            "responseDeadLine": (now + timedelta(days=5)).strftime("%Y-%m-%dT00:00:00Z"),
            "active": "Yes",
            "uiLink": "https://sam.gov/opp/MOCK-SOON-002/view",
            "description": "Full upgrade of perimeter firewalls and implementation of zero-trust network access (ZTNA) with 24/7 SOC monitoring. FIPS-140-2 compliance required.",
            "pointOfContact": [{"type": "primary", "fullName": "Robert Security", "email": "r.security@faa.gov"}],
            "placeOfPerformance": {"city": {"name": "Washington"}, "state": {"code": "DC"}},
        },
        {
            "noticeId": "MOCK-WON-003",
            "title": "Generative AI Procurement Officer Assistant",
            "solicitationNumber": "GSA-26-AI-0042",
            "fullParentPathName": "GENERAL SERVICES ADMINISTRATION",
            "naicsCode": params.get("naicsCode", "541519"),
            "type": "Award Notice",
            "typeOfSetAsideCode": "WOSB",
            "typeOfSetAside": "Women-Owned Small Business",
            "award": {
                "amount": 450000,
                "date": "2026-04-01T00:00:00Z",
                "number": "47QRAA26A0042",
                "awardee": {"name": "TechForward Solutions LLC"},
            },
            "postedDate": "2026-01-18T00:00:00-05:00",
            "responseDeadLine": "2026-03-10T00:00:00Z",
            "active": "No",
            "uiLink": "https://sam.gov/opp/MOCK-WON-003/view",
            "description": "Development of a secure offline-capable LLM assistant to help contract officers with FAR regulations and clause selection.",
            "pointOfContact": [{"type": "primary", "fullName": "Lisa Awards", "email": "l.awards@gsa.gov"}],
        },
        {
            "noticeId": "MOCK-EXPIRED-004",
            "title": "Cloud Migration Services — HHS Data Platform",
            "solicitationNumber": "HHS-26-CM-0014",
            "fullParentPathName": "DEPT OF HEALTH AND HUMAN SERVICES.CMS",
            "naicsCode": params.get("naicsCode", "541513"),
            "type": "Solicitation",
            "typeOfSetAsideCode": "8A",
            "typeOfSetAside": "8(a) Program",
            "award": {},
            "postedDate": "2026-03-01T00:00:00-05:00",
            "responseDeadLine": (now - timedelta(days=10)).strftime("%Y-%m-%dT00:00:00Z"),
            "active": "No",
            "uiLink": "https://sam.gov/opp/MOCK-EXPIRED-004/view",
            "description": "Migration of the CMS on-prem data warehouse to FedRAMP-authorized cloud infrastructure with zero-downtime cutover.",
        },
        {
            "noticeId": "MOCK-OPEN-005",
            "title": "Federal Workforce Learning Management System",
            "solicitationNumber": "OPM-26-LMS-0077",
            "fullParentPathName": "OFFICE OF PERSONNEL MANAGEMENT",
            "naicsCode": params.get("naicsCode", "611430"),
            "type": "Solicitation",
            "typeOfSetAsideCode": "SDVOSBC",
            "typeOfSetAside": "Service-Disabled Veteran-Owned Small Business",
            "award": {},
            "postedDate": "2026-06-01T00:00:00-05:00",
            "responseDeadLine": (now + timedelta(days=60)).strftime("%Y-%m-%dT00:00:00Z"),
            "active": "Yes",
            "uiLink": "https://sam.gov/opp/MOCK-OPEN-005/view",
            "description": "Deploy and configure a SaaS-based LMS covering over 40,000 federal employees, including SCORM-compliant content authoring and HRIS integration.",
        },
    ]
    return await _upsert_tenders_async(mock_raw, params, is_mock=True)


@router.get("/{notice_id}")
async def get_tender_detail(
    notice_id: str,
    current_user: dict = Depends(get_current_user),
):
    col = get_async_collection("tenders")
    tender = await col.find_one({"id": notice_id}, {"_id": 0})
    if not tender:
        raise HTTPException(
            status_code=404,
            detail=f"Tender '{notice_id}' not found in cache. Sync from SAM.gov first.",
        )
    return tender


@router.post("/{notice_id}/request-draft")
async def request_draft(
    notice_id: str,
    background_tasks: BackgroundTasks,
    payload: dict = {},
    current_user: dict = Depends(get_current_user),
):
    tenders_col = get_async_collection("tenders")
    tender = await tenders_col.find_one({"id": notice_id}, {"_id": 0})
    if not tender:
        raise HTTPException(
            status_code=404,
            detail=f"Tender '{notice_id}' not found. Sync from SAM.gov before requesting a draft.",
        )

    tender_status = tender.get("status", "Open")
    has_award = tender.get("has_award", False)
    award_awardee = tender.get("award_awardee", "")

    mode = payload.get("mode", "")
    if not mode:
        if tender_status in ("Won", "Expired", "Closed") or has_award:
            mode = "subcontract"
        else:
            mode = "prime"

    target_company = payload.get("target_company") or (award_awardee if mode == "subcontract" else "")

    drafts_col = get_async_collection("draft_requests")
    existing = await drafts_col.find_one({"notice_id": notice_id, "mode": mode})
    if existing:
        return {
            "status": "already_requested",
            "mode": mode,
            "message": f"A '{mode}' draft request for this tender already exists. Check the Proposal Builder.",
            "tender_title": tender.get("title"),
            "requested_at": existing.get("requested_at"),
            "target_company": existing.get("target_company"),
        }

    record = {
        "notice_id": notice_id,
        "mode": mode,
        "tender_title": tender.get("title"),
        "agency": tender.get("agency"),
        "solicitation_number": tender.get("solicitation_number"),
        "naics_code": tender.get("naics_code"),
        "set_aside": tender.get("set_aside"),
        "closing_date": tender.get("closing_date"),
        "days_until_close": tender.get("days_until_close"),
        "value": tender.get("value"),
        "tender_status": tender_status,
        "urgency": tender.get("urgency"),
        "poc_email": tender.get("poc_email"),
        "target_company": target_company,
        "award_awardee": award_awardee,
        "requester": payload.get("requester") or current_user.get("name") or current_user.get("email") or "Unknown User",
        "notes": payload.get("notes", ""),
        "draft_status": "pending",
        "requested_at": _utc_now_iso(),
    }

    await drafts_col.insert_one(record)

    if mode == "prime":
        sol_num = tender.get("solicitation_number")
        if sol_num:
            background_tasks.add_task(ensure_rfp_downloaded, notice_id, sol_num)

    if mode == "prime":
        msg = (
            f"Prime contractor draft request saved. You can start building the technical "
            f"response for '{tender.get('title')}' inside the Proposal Builder."
        )
    elif mode == "subcontract":
        msg = (
            f"Subcontract pitch draft request saved targeting '{target_company or 'the prime winner'}'. "
            f"You can launch the profiling and teaming pitch generator inside the Proposal Builder."
        )
    else:
        msg = "Draft request saved. Open the Proposal Builder to launch the build."

    return {
        "status": "success",
        "mode": mode,
        "message": msg,
        "tender_title": tender.get("title"),
        "target_company": target_company,
        "requested_at": record["requested_at"],
    }


@router.get("/{notice_id}/request-draft")
async def get_draft_request_status(
    notice_id: str,
    current_user: dict = Depends(get_current_user),
):
    drafts_col = get_async_collection("draft_requests")
    requests = await drafts_col.find(
        {
            "$or": [
                {"notice_id": notice_id},
                {"solicitation_number": notice_id}
            ]
        },
        {"_id": 0}
    ).to_list(length=100)
    return {
        "notice_id": notice_id,
        "requests": requests,
        "modes_requested": [r["mode"] for r in requests],
    }


@router.get("/draft-requests/all")
async def get_all_draft_requests(current_user: dict = Depends(get_current_user)):
    try:
        drafts_col = get_async_collection("draft_requests")
        requests = await drafts_col.find({}, {"_id": 0}).sort("requested_at", -1).to_list(length=1000)
        return requests
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def ensure_rfp_downloaded(notice_id: str, solicitation_number: str) -> None:
    downloads_path = Path("downloads") / "opportunities" / solicitation_number / "rfp_docs"
    if downloads_path.exists() and any(downloads_path.iterdir()):
        logger.info(f"[Tenders] RFP docs already downloaded for {solicitation_number}")
        return

    tender = get_collection("tenders").find_one({"id": notice_id})
    raw_opp = None
    if tender and "raw_sam_data" in tender:
        raw_opp = tender["raw_sam_data"]

    from app.sam_gov.opportunities import SAMOpportunitiesClient
    opp_client = SAMOpportunitiesClient()

    if not raw_opp:
        logger.info(f"[Tenders] Raw data missing. Querying SAM.gov for solicitation: {solicitation_number}")
        try:
            results = opp_client.search_opportunities(query=solicitation_number, posted_days=360)
            if results:
                for opp in results:
                    opp_sol = opp.get("solicitationNumber") or opp.get("solnum") or ""
                    if opp_sol.lower() == solicitation_number.lower():
                        raw_opp = opp
                        break
                if not raw_opp:
                    raw_opp = results[0]
        except Exception as e:
            logger.error(f"[Tenders] Failed searching SAM.gov: {e}")

    if raw_opp:
        logger.info(f"[Tenders] Triggering download and structuring for {solicitation_number}")
        try:
            opp_client.structure_rfp_profile(raw_opp)
            logger.info(f"[Tenders] Successfully downloaded and parsed RFP documents for {solicitation_number}")
        except Exception as e:
            logger.error(f"[Tenders] Error downloading RFP documents: {e}")


@router.get("/{notice_id}/documents")
async def list_tender_documents(
    notice_id: str,
    current_user: dict = Depends(get_current_user),
):
    col = get_async_collection("tenders")
    tender = await col.find_one({"noticeId": notice_id}, {"solicitationNumber": 1, "title": 1})
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    sol_num = _sanitize_path_component(tender.get("solicitationNumber") or notice_id)
    rfp_docs_dir = Path("downloads") / "opportunities" / sol_num / "rfp_docs"
    
    documents = []
    if rfp_docs_dir.exists():
        for f in sorted(rfp_docs_dir.iterdir()):
            if f.is_file():
                ext = f.suffix.lower()
                file_type = {
                    ".pdf": "PDF",
                    ".png": "Image (PNG)",
                    ".jpg": "Image (JPEG)",
                    ".jpeg": "Image (JPEG)",
                    ".gif": "Image (GIF)",
                    ".webp": "Image (WebP)",
                    ".docx": "Word Document",
                    ".doc": "Word Document",
                    ".xlsx": "Spreadsheet",
                    ".xls": "Spreadsheet",
                    ".txt": "Text File",
                    ".html": "HTML Document",
                    ".zip": "Archive",
                }.get(ext, "File")
                stat = f.stat()
                size_bytes = stat.st_size
                if size_bytes > 1024 * 1024:
                    size_str = f"{size_bytes / (1024*1024):.1f} MB"
                elif size_bytes > 1024:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_str = f"{size_bytes} B"
                
                documents.append({
                    "filename": f.name,
                    "type": file_type,
                    "size": size_str,
                    "size_bytes": size_bytes,
                    "modified": stat.st_mtime,
                    "path_key": f"opportunities/{sol_num}/rfp_docs/{f.name}",
                })

    return {
        "notice_id": notice_id,
        "solicitation_number": sol_num,
        "total": len(documents),
        "documents": documents,
    }


@router.get("/{notice_id}/documents/{filename}")
async def serve_tender_document(
    notice_id: str,
    filename: str,
    current_user: dict = Depends(get_current_user),
):
    safe_filename = Path(filename).name
    if not safe_filename or safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    col = get_async_collection("tenders")
    tender = await col.find_one({"noticeId": notice_id}, {"solicitationNumber": 1})
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    sol_num = _sanitize_path_component(tender.get("solicitationNumber") or notice_id)
    file_path = Path("downloads") / "opportunities" / sol_num / "rfp_docs" / safe_filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    ext = file_path.suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".txt": "text/plain",
        ".html": "text/html",
        ".zip": "application/zip",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=safe_filename,
        headers={"Content-Disposition": f'inline; filename="{safe_filename}"'},
    )
