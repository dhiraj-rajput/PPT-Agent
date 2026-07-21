"""
app/routes/tenders.py
---------------------
Tenders API — SAM.gov Opportunities v2 integration with MongoDB caching.

SAM.gov Opportunities API: https://api.sam.gov/opportunities/v2/search
Entity Management API (companies): https://api.sam.gov/entity-information/v3/entities

IMPORTANT — Rate limits:
  Non-federal, no SAM role  →  10 requests/day
  Non-federal, with SAM role → 1,000 requests/day  (register at sam.gov to unlock)
  Federal                    → 10,000 requests/day

Strategy:
  - MongoDB is the single source of truth. The frontend never hits SAM.gov directly.
  - SAM.gov is only called when the cache is empty OR the user triggers a manual sync.
  - Cached results include computed lifecycle status (Open / Closing Soon / Expired / Won).

Endpoints:
  GET  /api/tenders          — list cached tenders (search + filter locally in Mongo)
  GET  /api/tenders/meta     — sync metadata (last_synced, count, quota_used)
  POST /api/tenders/sync     — fetch fresh data from SAM.gov and cache it
  GET  /api/tenders/{id}     — single tender detail by noticeId
  POST /api/tenders/{id}/request-draft  — "Ask for Project (Draft)" button
"""

import re
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from utils.db_client import get_collection
from config.settings import settings
from app.core.auth import get_current_user

def _sanitize_path_component(value: str) -> str:
    """Sanitize a string for safe use as a filesystem path component."""
    import re
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip('_. ')

router = APIRouter(prefix="/tenders", tags=["tenders"])

# SAM.gov Opportunities v2 search endpoint
SAM_OPPORTUNITIES_BASE = "https://api.sam.gov/opportunities/v2/search"

# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _compute_match_score(notice_id: str, naics_code: str = "", title: str = "", summary: str = "") -> int:
    """Compute dynamic relevance match score against OrbitAvanya_Services_ADD.xlsx catalog."""
    try:
        from app.core.match_engine import compute_tender_match_score
        return compute_tender_match_score(notice_id=notice_id, title=title, summary=summary, naics_code=naics_code)
    except Exception:
        return 0


def _compute_lifecycle(
    closing_date_str: str,
    active_flag: str,
    award_date_str: str = "",
    award_amount: float = 0.0,
) -> dict:
    """
    Compute the rich lifecycle state of a tender from its dates and flags.

    Returns:
        status          : "Open" | "Closing Soon" | "Expired" | "Won" | "Closed"
        days_until_close: int (positive = days remaining, negative = days past deadline)
        is_active       : bool
        has_award       : bool — True when SAM reports an awarded contract
        urgency         : "critical" | "warning" | "normal" | "expired" | "won"
    """
    now = datetime.now(tz=timezone.utc)

    # Parse closing date
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
            # Handle timezone offset like -05:00
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
                pass
            closing_dt = datetime.strptime(raw[:len(fmt)], fmt)
            if closing_dt.tzinfo is None:
                closing_dt = closing_dt.replace(tzinfo=timezone.utc)
            break
        except (ValueError, AttributeError):
            continue

    days_until_close = None
    if closing_dt:
        delta = closing_dt - now
        days_until_close = delta.days  # negative = past deadline

    is_active = str(active_flag).strip().lower() in ("yes", "true", "1", "active", "y")
    has_award = bool(award_date_str and award_date_str.strip()) or award_amount > 0

    # Determine status and urgency
    if has_award:
        status = "Won"
        urgency = "won"
    elif not is_active and (days_until_close is None or days_until_close < 0):
        status = "Expired"
        urgency = "expired"
    elif days_until_close is not None and days_until_close < 0:
        status = "Expired"
        urgency = "expired"
    elif days_until_close is not None and days_until_close <= 7:
        status = "Closing Soon"
        urgency = "critical"
    elif days_until_close is not None and days_until_close <= 30:
        status = "Closing Soon"
        urgency = "warning"
    elif is_active:
        status = "Open"
        urgency = "normal"
    else:
        status = "Closed"
        urgency = "expired"

    return {
        "status": status,
        "urgency": urgency,
        "days_until_close": days_until_close,
        "is_active": is_active,
        "has_award": has_award,
    }


def _fmt_date(raw: str | None) -> str:
    """Safely parse and re-format a SAM.gov date string to YYYY-MM-DD."""
    if not raw:
        return ""
    try:
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y",
        ):
            try:
                raw_try = raw.strip()
                if raw_try.endswith("Z"):
                    raw_try = raw_try[:-1] + "+00:00"
                dt = datetime.fromisoformat(raw_try)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
            try:
                dt = datetime.strptime(raw.strip()[:len(fmt)], fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return raw[:10] if len(raw) >= 10 else raw
    except Exception:
        return raw or ""


def _map_opportunity(opp: dict) -> dict:
    """
    Map a single SAM.gov Opportunities v2 object to our internal schema.
    Handles missing / None fields gracefully.
    """
    notice_id = opp.get("noticeId") or opp.get("id") or ""

    # Award block — SAM nests this inside an award sub-object
    award = opp.get("award") or {}
    raw_value = award.get("amount") or opp.get("award_amount") or 0
    award_date = _fmt_date(award.get("date") or award.get("awardDate") or "")
    try:
        value_dollars = float(str(raw_value).replace(",", "").replace("$", ""))
        if value_dollars >= 1_000_000:
            formatted_value = f"${value_dollars / 1_000_000:.1f}M"
        elif value_dollars >= 1_000:
            formatted_value = f"${value_dollars / 1_000:.0f}K"
        elif value_dollars > 0:
            formatted_value = f"${value_dollars:,.0f}"
        else:
            formatted_value = "N/A"
    except (ValueError, TypeError):
        formatted_value = "N/A"
        value_dollars = 0.0

    posted = _fmt_date(opp.get("postedDate"))
    # responseDeadLine is the solicitation response deadline
    # archiveDate is used when it's been archived without a deadline
    closing_raw = opp.get("responseDeadLine") or opp.get("responseDateDeadline") or opp.get("archiveDate") or ""
    closing = _fmt_date(closing_raw)

    # Lifecycle computation
    active_flag = opp.get("active", "")
    lifecycle = _compute_lifecycle(
        closing_date_str=closing_raw,
        active_flag=active_flag,
        award_date_str=award_date,
        award_amount=value_dollars,
    )

    # Category / type
    raw_type = (
        opp.get("type")
        or opp.get("baseType")
        or opp.get("classificationCode")
        or "Solicitation"
    )

    # Agency — SAM nests this as fullParentPathName or departmentName
    agency_full = (
        opp.get("fullParentPathName")
        or opp.get("departmentName")
        or opp.get("subtierName")
        or opp.get("organizationName")
        or "Federal Agency"
    )
    # fullParentPathName = "DEPT OF DEFENSE.DEPT OF THE ARMY" → take last segment
    agency = agency_full.split(".")[-1].strip().title() if "." in agency_full else agency_full

    description = opp.get("description") or opp.get("synopsis") or ""

    # Solicitation number / POC
    poc_list = opp.get("pointOfContact") or []
    poc_email = ""
    poc_name = ""
    poc_phone = ""
    if poc_list and isinstance(poc_list, list):
        primary_poc = next((p for p in poc_list if p.get("type") == "primary"), poc_list[0] if poc_list else {})
        poc_email = primary_poc.get("email") or ""
        poc_name = primary_poc.get("fullName") or ""
        poc_phone = primary_poc.get("phone") or ""

    # Place of performance
    pop = opp.get("placeOfPerformance") or {}
    pop_city = (pop.get("city") or {}).get("name") or ""
    pop_state = (pop.get("state") or {}).get("code") or ""
    pop_location = f"{pop_city}, {pop_state}".strip(", ") if (pop_city or pop_state) else ""

    return {
        # Identity
        "id": notice_id,
        "solicitation_number": opp.get("solicitationNumber") or "",
        "title": opp.get("title") or "Untitled Opportunity",

        # Agency
        "agency": agency,
        "agency_full_path": agency_full,
        "department_name": opp.get("departmentName") or "",
        "sub_tier": opp.get("subtierName") or "",
        "office": opp.get("officeName") or "",

        # Classification
        "category": raw_type,
        "base_type": opp.get("baseType") or "",
        "naics_code": opp.get("naicsCode") or "",
        "classification_code": opp.get("classificationCode") or "",
        "set_aside_code": opp.get("typeOfSetAsideCode") or "",
        "set_aside": opp.get("typeOfSetAside") or "",

        # Financials
        "value": formatted_value,
        "award_amount": value_dollars,
        "award_date": award_date,
        "award_number": award.get("number") or award.get("awardNumber") or "",
        "award_awardee": (award.get("awardee") or {}).get("name") or award.get("awardeeName") or "",

        # Lifecycle / Dates
        "posted_date": posted,
        "closing_date": closing,
        "archive_date": _fmt_date(opp.get("archiveDate") or ""),
        "status": lifecycle["status"],
        "urgency": lifecycle["urgency"],
        "days_until_close": lifecycle["days_until_close"],
        "is_active": lifecycle["is_active"],
        "has_award": lifecycle["has_award"],

        # Contact
        "poc_name": poc_name,
        "poc_email": poc_email,
        "poc_phone": poc_phone,

        # Place of Performance
        "place_of_performance": pop_location,

        # Content
        "description": description,
        "rfp_url": opp.get("uiLink") or f"https://sam.gov/opp/{notice_id}/view",

        # AI-computed
        "match": _compute_match_score(notice_id, opp.get("naicsCode") or ""),

        # Legacy camelCase aliases so any existing frontend reading .closingDate etc still works
        "postedDate": posted,
        "closingDate": closing,
        "matchScore": _compute_match_score(notice_id, opp.get("naicsCode") or ""),

        # Internal metadata
        "_cached_at": _utc_now_iso(),
    }


# ---------------------------------------------------------------------------
# GET /api/tenders/meta  — MUST be before /{id} to avoid route shadowing
# ---------------------------------------------------------------------------

@router.get("/meta")
def get_tenders_meta(current_user: dict = Depends(get_current_user)):
    """Return sync metadata: last_synced, total cached, quota used today."""
    meta_col = get_collection("tenders_meta")
    tenders_col = get_collection("tenders")
    meta = meta_col.find_one({}, {"_id": 0}) or {}
    count = tenders_col.count_documents({})
    return {
        "last_synced": meta.get("last_synced"),
        "total_cached": count,
        "quota_used_today": meta.get("quota_used_today", 0),
        "last_sync_params": meta.get("last_sync_params", {}),
        "rate_limit_note": (
            "Free tier: 10 req/day. Register a role at sam.gov/workspace → 1,000 req/day. "
            "Cached results never expire — sync only when you need fresh data."
        ),
    }


# ---------------------------------------------------------------------------
# GET /api/tenders
# ---------------------------------------------------------------------------

@router.get("")
def get_tenders(
    query: Optional[str] = None,
    naics: Optional[str] = None,
    set_aside: Optional[str] = None,
    status: Optional[str] = None,
    urgency: Optional[str] = None,
    has_award: Optional[bool] = None,
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """
    Return cached tenders from MongoDB with optional local filtering.
    No SAM.gov calls — everything served from the cache.

    status options: Open | Closing Soon | Expired | Won | Closed | All
    urgency options: critical | warning | normal | expired | won
    """
    try:
        col = get_collection("tenders")
        total_cached = col.count_documents({})

        if total_cached == 0:
            return {
                "total": 0,
                "page": page,
                "limit": limit,
                "tenders": [],
                "cache_empty": True,
                "naics_codes": [],
                "set_aside_options": [],
                "message": "No tenders cached yet. Use the Sync button to fetch from SAM.gov.",
            }

        # Build filter
        filter_q: dict = {}
        and_conditions: list = []

        if query:
            q = re.escape(query.strip())
            and_conditions.append({"$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"agency": {"$regex": q, "$options": "i"}},
                {"solicitation_number": {"$regex": q, "$options": "i"}},
                {"description": {"$regex": q, "$options": "i"}},
                {"naics_code": {"$regex": q, "$options": "i"}},
            ]})

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

        total = col.count_documents(filter_q)
        skip = (page - 1) * limit
        results = list(col.find(filter_q, {"_id": 0}).skip(skip).limit(limit))

        # Summary counts by lifecycle status
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        status_counts_raw = list(col.aggregate(pipeline))
        status_counts = {s["_id"]: s["count"] for s in status_counts_raw if s.get("_id")}

        # Dropdown options from cached data
        naics_codes = sorted([n for n in col.distinct("naics_code") if n])[:100]
        set_aside_opts = sorted([s for s in col.distinct("set_aside") if s])[:50]

        return {
            "total": total,
            "total_cached": total_cached,
            "page": page,
            "limit": limit,
            "tenders": results,
            "cache_empty": False,
            "naics_codes": naics_codes,
            "set_aside_options": set_aside_opts,
            "status_counts": status_counts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/tenders/sync
# ---------------------------------------------------------------------------

@router.post("/sync")
def sync_tenders_from_sam(
    payload: dict = {},
    current_user: dict = Depends(get_current_user),
):
    """
    Fetch opportunities from SAM.gov Opportunities v2 API and cache them in MongoDB.

    SAM.gov Opportunities API parameters (all optional):
    {
        "naicsCode":          "541511",    // 6-digit NAICS code (primary NAICS on the solicitation)
        "keyword":            "AI cloud",  // free-text search across title + description
        "typeOfSetAsideCode": "SBA",       // set-aside type: SBA, WOSB, 8A, SDVOSBC, HZC, VSB...
        "postedFrom":         "01/01/2026", // MM/DD/YYYY
        "postedTo":           "12/31/2026", // MM/DD/YYYY
        "active":             "Yes",        // "Yes" = active only, "No" = archived only
        "limit":              25,           // SAM hard max = 25 per request
        "offset":             0             // pagination offset (0, 25, 50 ...)
    }

    Rate limit reminder:
      - No SAM.gov role: 10 req/day (each call here = 1 request)
      - With SAM.gov role: 1,000 req/day → register at sam.gov to unlock this
    """
    api_key = settings.SAM_GOV_API_KEY
    force_mock = settings.FORCE_MOCK_SAM_GOV

    if not force_mock:
        # Check manual sync cooldown of 24 hours
        meta_col = get_collection("tenders_meta")
        meta = meta_col.find_one({}) or {}
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
                print(f"[Tenders] Cooldown parse warning: {e}")

    if not api_key and not force_mock:
        raise HTTPException(
            status_code=503,
            detail="SAM_GOV_API_KEY is not set. Add it to your .env file.",
        )

    # Build SAM.gov Opportunities v2 query params
    params: dict = {
        "api_key": api_key,
        "limit": min(int(payload.get("limit", 25)), 25),   # SAM hard max = 25
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

    # SAM.gov Opportunities v2 mandates postedFrom and postedTo dates
    if not force_mock:
        if not params.get("postedFrom"):
            params["postedFrom"] = (datetime.now(tz=timezone.utc) - timedelta(days=90)).strftime("%m/%d/%Y")
        if not params.get("postedTo"):
            params["postedTo"] = datetime.now(tz=timezone.utc).strftime("%m/%d/%Y")

    # Strip empty values (forbidden chars / unexpected behaviour)
    params = {k: v for k, v in params.items() if v not in (None, "")}

    if force_mock:
        print("[Tenders] FORCE_MOCK_SAM_GOV=true — using mock data, no API call made")
        return _insert_mock_tenders(params)

    # --- Live SAM.gov Opportunities API call ---
    try:
        print(f"[Tenders] -> GET {SAM_OPPORTUNITIES_BASE} params={params}")
        with httpx.Client(timeout=30) as client:
            resp = client.get(SAM_OPPORTUNITIES_BASE, params=params)

        print(f"[Tenders] <- HTTP {resp.status_code}")

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
        # Opportunities v2 wraps results in "opportunitiesData"
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

        return _upsert_tenders(opportunities, params)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SAM.gov request failed: {e}")


def _upsert_tenders(opportunities: list, sync_params: dict, is_mock: bool = False) -> dict:
    """Upsert a list of SAM.gov opportunity dicts into MongoDB and refresh metadata."""
    tenders_col = get_collection("tenders")
    meta_col = get_collection("tenders_meta")
    upserted = 0

    for opp in opportunities:
        mapped = _map_opportunity(opp)
        if not mapped.get("id"):
            continue
        mapped["raw_sam_data"] = opp
        if is_mock:
            mapped["_data_source"] = "mock"
        tenders_col.update_one(
            {"id": mapped["id"]},
            {"$set": mapped},
            upsert=True,
        )
        upserted += 1

    meta_col.update_one(
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

    # Recompute lifecycle statuses for already-cached tenders whose deadlines have passed
    _refresh_expired_statuses(tenders_col)

    print(f"[Tenders] Upserted {upserted} tenders into MongoDB.")
    return {
        "status": "ok",
        "fetched": len(opportunities),
        "upserted": upserted,
        "message": (
            f"Successfully cached {upserted} tenders from SAM.gov. "
            "Results are stored permanently — no need to sync again unless you want fresher data."
        ),
    }


def _refresh_expired_statuses(col) -> None:
    """
    Re-evaluate lifecycle status for all cached tenders.
    Run after every sync so tenders that have expired since last fetch
    are correctly marked as Expired rather than showing stale Open status.
    """
    now = datetime.now(tz=timezone.utc)
    cutoff = now.strftime("%Y-%m-%d")
    try:
        # Mark expired: closing_date < today AND status is NOT Won/Expired
        col.update_many(
            {
                "closing_date": {"$lt": cutoff, "$ne": ""},
                "status": {"$nin": ["Won", "Expired"]},
            },
            {"$set": {"status": "Expired", "urgency": "expired", "is_active": False}},
        )
        # Mark closing-soon: closing_date within next 7 days
        in_7_days = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        col.update_many(
            {
                "closing_date": {"$gte": cutoff, "$lte": in_7_days},
                "status": "Open",
            },
            {"$set": {"status": "Closing Soon", "urgency": "critical"}},
        )
        # Mark closing-soon (warning): closing_date within next 30 days
        in_30_days = (now + timedelta(days=30)).strftime("%Y-%m-%d")
        col.update_many(
            {
                "closing_date": {"$gt": in_7_days, "$lte": in_30_days},
                "status": "Open",
            },
            {"$set": {"status": "Closing Soon", "urgency": "warning"}},
        )
    except Exception as e:
        print(f"[Tenders] Warning: lifecycle refresh failed: {e}")


def _insert_mock_tenders(params: dict) -> dict:
    """Mock data for dev/demo — uses realistic SAM.gov Opportunities v2 shape."""
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
    return _upsert_tenders(mock_raw, params, is_mock=True)


# ---------------------------------------------------------------------------
# GET /api/tenders/{notice_id}
# ---------------------------------------------------------------------------

@router.get("/{notice_id}")
def get_tender_detail(
    notice_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve a single cached tender by its noticeId."""
    col = get_collection("tenders")
    tender = col.find_one({"id": notice_id}, {"_id": 0})
    if not tender:
        raise HTTPException(
            status_code=404,
            detail=f"Tender '{notice_id}' not found in cache. Sync from SAM.gov first.",
        )
    return tender


# ---------------------------------------------------------------------------
# POST /api/tenders/{notice_id}/request-draft
# ---------------------------------------------------------------------------

@router.post("/{notice_id}/request-draft")
def request_draft(
    notice_id: str,
    background_tasks: BackgroundTasks,
    payload: dict = {},
    current_user: dict = Depends(get_current_user),
):
    """
    Wire the action buttons in TenderDetail.jsx.

    Modes
    -----
    prime        — We respond to the open RFP directly as the prime contractor.
                   Stores the draft request and queues RFP response generation.
    subcontract  — The contract was already awarded to another company (status=Won).
                   We pitch ourselves to the winning prime contractor for a subcontract.
                   Queues the partnership proposal pipeline with `winner` = award_awardee.
    reference    — The RFP has expired. We generate a reference/template proposal
                   for similar future opportunities.

    Body (all optional):
    {
        "mode":           "prime" | "subcontract" | "reference",
        "requester":      "John Doe",
        "notes":          "Focus on AI volume and past performance",
        "target_company": "TechForward Solutions LLC"   # auto-filled for subcontract
    }
    """
    tenders_col = get_collection("tenders")
    tender = tenders_col.find_one({"id": notice_id}, {"_id": 0})
    if not tender:
        raise HTTPException(
            status_code=404,
            detail=f"Tender '{notice_id}' not found. Sync from SAM.gov before requesting a draft.",
        )

    # Resolve mode from payload or infer from tender status
    tender_status = tender.get("status", "Open")
    has_award = tender.get("has_award", False)
    award_awardee = tender.get("award_awardee", "")

    mode = payload.get("mode", "")
    if not mode:
        if tender_status in ("Won", "Expired", "Closed") or has_award:
            mode = "subcontract"
        else:
            mode = "prime"

    # For subcontract, the target company is the winner
    target_company = payload.get("target_company") or (award_awardee if mode == "subcontract" else "")

    drafts_col = get_collection("draft_requests")
    # Check for existing request with the same mode
    existing = drafts_col.find_one({"notice_id": notice_id, "mode": mode})
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

    drafts_col.insert_one(record)

    # Trigger RFP documents download in the background for prime mode
    if mode == "prime":
        sol_num = tender.get("solicitation_number")
        if sol_num:
            background_tasks.add_task(ensure_rfp_downloaded, notice_id, sol_num)

    # --- Mode-specific messages ---
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
def get_draft_request_status(
    notice_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Returns all existing draft requests for a tender so the frontend
    can pre-populate button states on page load without re-submitting.
    """
    drafts_col = get_collection("draft_requests")
    requests = list(drafts_col.find(
        {
            "$or": [
                {"notice_id": notice_id},
                {"solicitation_number": notice_id}
            ]
        },
        {"_id": 0}
    ))
    return {
        "notice_id": notice_id,
        "requests": requests,
        "modes_requested": [r["mode"] for r in requests],
    }


@router.get("/draft-requests/all")
def get_all_draft_requests(current_user: dict = Depends(get_current_user)):
    """
    Returns all draft requests across all tenders so the Proposal Builder
    can display the pending and active drafts list.
    """
    try:
        drafts_col = get_collection("draft_requests")
        requests = list(drafts_col.find({}, {"_id": 0}).sort("requested_at", -1))
        return requests
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



def ensure_rfp_downloaded(notice_id: str, solicitation_number: str) -> None:
    """
    Checks if RFP PDF/document files are already downloaded for this solicitation.
    If not, fetches the raw opportunity from cache or SAM.gov and triggers the
    SAMOpportunitiesClient to download them locally.
    """
    from pathlib import Path
    import os
    
    # Opportunities are saved to: downloads/opportunities/{solicitation_number}/rfp_docs/
    downloads_path = Path("downloads") / "opportunities" / solicitation_number / "rfp_docs"
    if downloads_path.exists() and any(downloads_path.iterdir()):
        print(f"[Tenders] RFP docs already downloaded for {solicitation_number}")
        return

    # Check MongoDB cache for the raw SAM.gov payload
    from utils.db_client import get_collection
    tender = get_collection("tenders").find_one({"id": notice_id})
    raw_opp = None
    if tender and "raw_sam_data" in tender:
        raw_opp = tender["raw_sam_data"]

    from app.sam_gov.opportunities import SAMOpportunitiesClient
    opp_client = SAMOpportunitiesClient()

    if not raw_opp:
        print(f"[Tenders] Raw data missing. Querying SAM.gov for solicitation: {solicitation_number}")
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
            print(f"[Tenders] Failed searching SAM.gov: {e}")

    if raw_opp:
        print(f"[Tenders] Triggering download and structuring for {solicitation_number}")
        try:
            opp_client.structure_rfp_profile(raw_opp)
            print(f"[Tenders] Successfully downloaded and parsed RFP documents for {solicitation_number}")
        except Exception as e:
            print(f"[Tenders] Error downloading RFP documents: {e}")
    else:
        print(f"[Tenders] Warning: Could not find raw opportunity for {solicitation_number} to download RFP.")


# ---------------------------------------------------------------------------
# Tender document serving endpoints
# ---------------------------------------------------------------------------

@router.get("/{notice_id}/documents")
async def list_tender_documents(
    notice_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    List all downloaded documents for a specific tender.
    Returns file metadata: name, size, type, path key for viewing.
    """
    import os
    from pathlib import Path

    # Look up the tender to get solicitation number
    col = get_collection("tenders")
    tender = col.find_one({"noticeId": notice_id}, {"solicitationNumber": 1, "title": 1})
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
    """
    Stream/serve a specific downloaded tender document.
    Prevents path traversal attacks by validating the filename.
    """
    import os
    from pathlib import Path
    from fastapi.responses import FileResponse

    # Security: prevent path traversal
    safe_filename = Path(filename).name
    if not safe_filename or safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    col = get_collection("tenders")
    tender = col.find_one({"noticeId": notice_id}, {"solicitationNumber": 1})
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    sol_num = _sanitize_path_component(tender.get("solicitationNumber") or notice_id)
    file_path = Path("downloads") / "opportunities" / sol_num / "rfp_docs" / safe_filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    # Determine media type
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
