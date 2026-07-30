"""
app/routes/tenders.py
---------------------
Tenders API — SAM.gov Opportunities v2 integration with MySQL cache.
"""

from __future__ import annotations

import asyncio
import logging
import re
import httpx
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse

from utils.db_client import get_db_session, get_sync_db_session, _mysql_available
from config.settings import settings
from app.core.auth import get_current_user
from models.sql_models import (
    Tender as SQL_Tender,
    DraftRequest as SQL_DraftRequest,
    SystemSettings as SQL_SystemSettings,
    User as SQLUser,
)
from sqlalchemy import select, update, insert, delete, func, or_, and_

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenders", tags=["tenders"])

SAM_OPPORTUNITIES_BASE = getattr(settings, "SAM_GOV_API_URL", "https://api.sam.gov/opportunities/v2/search")


def _sanitize_path_component(val: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", str(val or "")).strip()



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
        "notice_id": notice_id,
        "title": title,
        "solicitation_number": sol_num,
        "agency": dept,
        "department": dept,
        "naics_code": str(naics),
        "set_aside": set_aside_desc,
        "set_aside_code": set_aside_code,
        "opportunity_type": opp.get("type") or "Solicitation",
        "posted_date": posted_fmt,
        "closing_date": closing_fmt,
        "days_until_close": lifecycle["days_until_close"],
        "status": lifecycle["status"],
        "urgency": lifecycle["urgency"],
        "is_active": lifecycle["is_active"],
        "has_award": lifecycle["has_award"],
        "award_amount": award_amount,
        "award_date": award_date[:10] if award_date else "",
        "award_awardee": award_awardee,
        "match_score": match_score,
        "rfp_url": opp.get("uiLink") or f"https://sam.gov/opp/{notice_id}/view",
        "summary": summary[:2000],
        "poc_name": poc_name,
        "poc_email": poc_email,
        "poc_phone": poc_phone,
        "place_of_performance": _format_place_of_performance(opp.get("placeOfPerformance")),
        "updatedAt": _utc_now_iso(),
    }


def _format_tender(t: SQL_Tender) -> dict:
    if not t:
        return {}
    return {
        "id": t.id,
        "noticeId": t.notice_id,
        "title": t.title or "",
        "solicitation_number": t.solicitation_number or "",
        "solicitationNumber": t.solicitation_number or "",
        "agency": t.agency or "",
        "department": t.department or "",
        "naics_code": t.naics_code or "",
        "set_aside": t.set_aside or "",
        "opportunity_type": t.opportunity_type or "",
        "postedDate": t.posted_date or "",
        "posted_date": t.posted_date or "",
        "closingDate": t.closing_date or "",
        "closing_date": t.closing_date or "",
        "days_until_close": t.days_until_close or 0,
        "status": t.status or "Open",
        "urgency": t.urgency or "normal",
        "is_active": bool(t.is_active),
        "has_award": bool(t.has_award),
        "award_amount": float(getattr(t, "award_amount", 0) or 0.0),
        "award_date": t.award_date or "",
        "award_awardee": t.award_awardee or "",
        "match": t.match_score or 0,
        "matchScore": t.match_score or 0,
        "rfp_url": t.rfp_url or "",
        "summary": t.summary or "",
        "poc_name": t.poc_name or "",
        "poc_email": t.poc_email or "",
        "poc_phone": t.poc_phone or "",
        "place_of_performance": t.place_of_performance or "",
        "updatedAt": t.updated_at.isoformat() if getattr(t, "updated_at", None) else None,
        "raw_sam_data": t.raw_sam_data
    }


@router.get("/meta")
async def get_tenders_meta(current_user: dict = Depends(get_current_user)):
    total_cached = 0
    active_cached = 0
    last_synced = None
    quota_used_today = 0

    if _mysql_available:
        try:
            async for db in get_db_session():
                total_cached = (await db.execute(select(func.count()).select_from(SQL_Tender))).scalar() or 0
                active_cached = (await db.execute(select(func.count()).select_from(SQL_Tender).where(SQL_Tender.is_active == True))).scalar() or 0

                stmt = select(SQL_SystemSettings).where(SQL_SystemSettings.key_name == "tenders_meta")
                row = (await db.execute(stmt)).scalar_one_or_none()
                if row:
                    val = getattr(row, "value", None)
                    if val:
                        try:
                            data = json.loads(str(val))
                            last_synced = data.get("last_synced")
                            quota_used_today = data.get("quota_used_today", 0)
                        except Exception:
                            pass

        except Exception as e:
            logger.error(f"Failed to load tenders metadata: {e}")

    return {
        "total_cached": total_cached,
        "active_cached": active_cached,
        "last_synced": last_synced,
        "quota_used_today": quota_used_today,
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
    tenders = []
    total = 0
    total_cached = 0
    status_counts = {}
    naics_codes = []
    set_aside_opts = []

    if _mysql_available:
        try:
            async for db in get_db_session():
                total_cached = (await db.execute(select(func.count()).select_from(SQL_Tender))).scalar() or 0

                filter_conditions = []
                if q:
                    qs = f"%{q.strip()}%"
                    filter_conditions.append(or_(
                        SQL_Tender.title.ilike(qs),
                        SQL_Tender.solicitation_number.ilike(qs),
                        SQL_Tender.agency.ilike(qs),
                        SQL_Tender.department.ilike(qs),
                        SQL_Tender.summary.ilike(qs),
                        SQL_Tender.naics_code.ilike(qs)
                    ))

                if naics and naics.upper() != "ALL":
                    filter_conditions.append(SQL_Tender.naics_code.ilike(f"%{naics.strip()}%"))

                if set_aside and set_aside.upper() != "ALL":
                    filter_conditions.append(or_(
                        SQL_Tender.set_aside.ilike(f"%{set_aside.strip()}%"),
                        SQL_Tender.set_aside.ilike(f"%{set_aside.strip()}%")
                    ))

                if status and status.upper() != "ALL":
                    filter_conditions.append(SQL_Tender.status == status)

                if urgency and urgency.upper() != "ALL":
                    filter_conditions.append(SQL_Tender.urgency == urgency)

                if has_award is not None:
                    filter_conditions.append(SQL_Tender.has_award == has_award)

                stmt_count = select(func.count()).select_from(SQL_Tender)
                stmt_select = select(SQL_Tender)
                if filter_conditions:
                    stmt_count = stmt_count.where(and_(*filter_conditions))
                    stmt_select = stmt_select.where(and_(*filter_conditions))

                total = (await db.execute(stmt_count)).scalar() or 0

                skip = (page - 1) * limit
                stmt_select = stmt_select.order_by(SQL_Tender.match_score.desc(), SQL_Tender.posted_date.desc()).offset(skip).limit(limit)
                res = await db.execute(stmt_select)
                tenders = [_format_tender(t) for t in res.scalars().all()]

                # Status counts
                stmt_stat = select(SQL_Tender.status, func.count()).group_by(SQL_Tender.status)
                res_stat = await db.execute(stmt_stat)
                for row in res_stat.all():
                    if row[0]:
                        status_counts[row[0].value if hasattr(row[0], "value") else str(row[0])] = row[1]

                # Distinct lists
                stmt_naics = select(SQL_Tender.naics_code).distinct().where(SQL_Tender.naics_code != "").order_by(SQL_Tender.naics_code.asc()).limit(100)
                naics_codes = [n for n in (await db.execute(stmt_naics)).scalars().all()]

                stmt_sa = select(SQL_Tender.set_aside).distinct().where(SQL_Tender.set_aside != "").order_by(SQL_Tender.set_aside.asc()).limit(50)
                set_aside_opts = [s for s in (await db.execute(stmt_sa)).scalars().all()]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {
        "total": total,
        "total_cached": total_cached,
        "page": page,
        "limit": limit,
        "tenders": tenders,
        "cache_empty": total_cached == 0,
        "naics_codes": naics_codes,
        "set_aside_options": set_aside_opts,
        "status_counts": status_counts,
    }


@router.post("/sync")
async def sync_tenders_from_sam(
    payload: dict = {},
    current_user: dict = Depends(get_current_user),
):
    api_key = settings.SAM_GOV_API_KEY
    force_mock = settings.FORCE_MOCK_SAM_GOV

    if not force_mock:
        # Check cooldown
        if _mysql_available:
            async for db in get_db_session():
                stmt = select(SQL_SystemSettings).where(SQL_SystemSettings.key_name == "tenders_meta")
                row = (await db.execute(stmt)).scalar_one_or_none()
                if row:
                    val = getattr(row, "value", None)
                    if val:
                        try:
                            data = json.loads(str(val))
                            last_synced_str = data.get("last_synced")
                            if last_synced_str:
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
                detail="SAM.gov rate limit reached (10 requests/day). Your cached tenders are still available."
            )
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="SAM.gov API key is invalid or expired.")
        if resp.status_code == 403:
            raise HTTPException(
                status_code=403,
                detail="SAM.gov returned 403 Forbidden. Check that your API key is correct.",
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
                "message": "SAM.gov returned 0 results for these parameters.",
            }

        return await _upsert_tenders_async(opportunities, params)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SAM.gov request failed: {e}")


async def _upsert_tenders_async(opportunities: list, sync_params: dict, is_mock: bool = False) -> dict:
    upserted = 0

    if _mysql_available:
        try:
            async for db in get_db_session():
                for opp in opportunities:
                    mapped = _map_opportunity(opp)
                    if not mapped.get("notice_id"):
                        continue
                    mapped["raw_sam_data"] = opp
                    if is_mock:
                        mapped["raw_sam_data"]["_data_source"] = "mock"

                    stmt_exist = select(SQL_Tender).where(SQL_Tender.id == mapped["notice_id"])
                    existing = (await db.execute(stmt_exist)).scalar_one_or_none()

                    award_amt = mapped.pop("award_amount", 0.0)

                    if existing:
                        await db.execute(
                            update(SQL_Tender)
                            .where(SQL_Tender.id == mapped["notice_id"])
                            .values(
                                title=mapped["title"],
                                solicitation_number=mapped["solicitation_number"],
                                agency=mapped["agency"],
                                department=mapped["department"],
                                naics_code=mapped["naics_code"],
                                set_aside=mapped["set_aside"],
                                opportunity_type=mapped["opportunity_type"],
                                posted_date=mapped["posted_date"],
                                closing_date=mapped["closing_date"],
                                days_until_close=mapped["days_until_close"],
                                status=mapped["status"],
                                urgency=mapped["urgency"],
                                is_active=mapped["is_active"],
                                has_award=mapped["has_award"],
                                award_amount=award_amt,
                                award_date=mapped["award_date"],
                                award_awardee=mapped["award_awardee"],
                                match_score=mapped["match_score"],
                                rfp_url=mapped["rfp_url"],
                                summary=mapped["summary"],
                                poc_name=mapped["poc_name"],
                                poc_email=mapped["poc_email"],
                                poc_phone=mapped["poc_phone"],
                                place_of_performance=mapped["place_of_performance"],
                                raw_sam_data=mapped["raw_sam_data"],
                                updated_at=datetime.utcnow()
                            )
                        )
                    else:
                        db.add(SQL_Tender(
                            id=mapped["notice_id"],
                            notice_id=mapped["notice_id"],
                            title=mapped["title"],
                            solicitation_number=mapped["solicitation_number"],
                            agency=mapped["agency"],
                            department=mapped["department"],
                            naics_code=mapped["naics_code"],
                            set_aside=mapped["set_aside"],
                            opportunity_type=mapped["opportunity_type"],
                            posted_date=mapped["posted_date"],
                            closing_date=mapped["closing_date"],
                            days_until_close=mapped["days_until_close"],
                            status=mapped["status"],
                            urgency=mapped["urgency"],
                            is_active=mapped["is_active"],
                            has_award=mapped["has_award"],
                            award_amount=award_amt,
                            award_date=mapped["award_date"],
                            award_awardee=mapped["award_awardee"],
                            match_score=mapped["match_score"],
                            rfp_url=mapped["rfp_url"],
                            summary=mapped["summary"],
                            poc_name=mapped["poc_name"],
                            poc_email=mapped["poc_email"],
                            poc_phone=mapped["poc_phone"],
                            place_of_performance=mapped["place_of_performance"],
                            raw_sam_data=mapped["raw_sam_data"],
                            updated_at=datetime.utcnow()
                        ))
                    upserted += 1

                # Save meta inside SystemSettings
                stmt_meta = select(SQL_SystemSettings).where(SQL_SystemSettings.key_name == "tenders_meta")
                meta_row = (await db.execute(stmt_meta)).scalar_one_or_none()

                meta_data = {
                    "last_synced": _utc_now_iso(),
                    "last_sync_params": {k: v for k, v in sync_params.items() if k != "api_key"},
                    "quota_used_today": 1
                }
                if meta_row:
                    val = getattr(meta_row, "value", None)
                    if val:
                        try:
                            old_meta = json.loads(str(val))
                            meta_data["quota_used_today"] = old_meta.get("quota_used_today", 0) + 1
                        except Exception:
                            pass


                if meta_row:
                    await db.execute(
                        update(SQL_SystemSettings)
                        .where(SQL_SystemSettings.key_name == "tenders_meta")
                        .values(value=json.dumps(meta_data), updated_at=datetime.utcnow())
                    )
                else:
                    db.add(SQL_SystemSettings(
                        key_name="tenders_meta",
                        value=json.dumps(meta_data),
                        updated_at=datetime.utcnow()
                    ))

                await db.commit()

                # Refresh statuses
                await _refresh_expired_statuses_async()

                # Trigger background document download worker for all synced opportunities (PDF, XLSX, CSV, Images, Word)
                def _download_all_tender_docs():
                    try:
                        from app.sam_gov.opportunities import SAMOpportunitiesClient
                        opp_client = SAMOpportunitiesClient(api_key=settings.SAM_GOV_API_KEY)
                        for opp in opportunities:
                            try:
                                opp_client.structure_rfp_profile(opp)
                            except Exception as err:
                                logger.warning(f"[Tenders] Document download worker notice error: {err}")
                    except Exception as e:
                        logger.error(f"[Tenders] Document download worker initialization failed: {e}")

                asyncio.create_task(asyncio.to_thread(_download_all_tender_docs))
        except Exception as e:
            logger.error(f"Failed to upsert opportunities: {e}")
            raise HTTPException(500, f"Upsert failed: {e}")

    return {
        "status": "ok",
        "fetched": len(opportunities),
        "upserted": upserted,
        "message": f"Successfully cached {upserted} tenders and initiated background document downloads.",
    }


async def _refresh_expired_statuses_async() -> None:
    now = datetime.now(tz=timezone.utc)
    cutoff = now.strftime("%Y-%m-%d")
    in_7_days = (now + timedelta(days=7)).strftime("%Y-%m-%d")
    in_30_days = (now + timedelta(days=30)).strftime("%Y-%m-%d")

    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(
                    update(SQL_Tender)
                    .where(SQL_Tender.closing_date < cutoff, SQL_Tender.closing_date != "", ~SQL_Tender.status.in_(["Won", "Expired"]))
                    .values(status="Expired", urgency="expired", is_active=False)
                )
                await db.execute(
                    update(SQL_Tender)
                    .where(SQL_Tender.closing_date >= cutoff, SQL_Tender.closing_date <= in_7_days, SQL_Tender.status == "Open")
                    .values(status="Closing Soon", urgency="critical")
                )
                await db.execute(
                    update(SQL_Tender)
                    .where(SQL_Tender.closing_date > in_7_days, SQL_Tender.closing_date <= in_30_days, SQL_Tender.status == "Open")
                    .values(status="Closing Soon", urgency="warning")
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"[Tenders] Lifecycle status refresh warning: {e}")


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
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Tender).where(SQL_Tender.id == notice_id)
                res = await db.execute(stmt)
                tender = res.scalar_one_or_none()
                if not tender:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Tender '{notice_id}' not found in cache. Sync from SAM.gov first.",
                    )
                sol_num = tender.solicitation_number or tender.notice_id
                asyncio.create_task(asyncio.to_thread(ensure_rfp_downloaded, notice_id, sol_num))
                return _format_tender(tender)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(500, "Database is unavailable.")


@router.post("/{notice_id}/request-draft")
async def request_draft(
    notice_id: str,
    background_tasks: BackgroundTasks,
    payload: dict = {},
    current_user: dict = Depends(get_current_user),
):
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="Database is unavailable.")

    try:
        async for db in get_db_session():
            stmt = select(SQL_Tender).where(SQL_Tender.id == notice_id)
            tender = (await db.execute(stmt)).scalar_one_or_none()
            if not tender:
                raise HTTPException(
                    status_code=404,
                    detail=f"Tender '{notice_id}' not found. Sync from SAM.gov before requesting a draft.",
                )

            tender_status = tender.status or "Open"
            has_award = bool(tender.has_award)
            award_awardee = tender.award_awardee or ""

            mode = payload.get("mode", "")
            if not mode:
                if tender_status in ("Won", "Expired", "Closed") or has_award:
                    mode = "subcontract"
                else:
                    mode = "prime"

            target_company = payload.get("target_company") or (award_awardee if mode == "subcontract" else "")

            # Check if existing
            stmt_exist = select(SQL_DraftRequest).where(SQL_DraftRequest.notice_id == notice_id, SQL_DraftRequest.mode == mode)
            existing = (await db.execute(stmt_exist)).scalar_one_or_none()
            if existing:
                return {
                    "status": "already_requested",
                    "mode": mode,
                    "message": f"A '{mode}' draft request for this tender already exists. Check the Proposal Builder.",
                    "tender_title": tender.title,
                    "requested_at": existing.created_at.isoformat() if getattr(existing, "created_at", None) else "",
                    "target_company": existing.extra_data.get("target_company") if (existing and isinstance(existing.extra_data, dict)) else "",
                }

            extra_info = {
                "tender_title": tender.title,
                "agency": tender.agency,
                "solicitation_number": tender.solicitation_number,
                "naics_code": tender.naics_code,
                "set_aside": tender.set_aside,
                "closing_date": tender.closing_date,
                "days_until_close": tender.days_until_close,
                "value": str(tender.award_amount or 0.0),
                "tender_status": tender_status,
                "urgency": tender.urgency,
                "poc_email": tender.poc_email,
                "target_company": target_company,
                "award_awardee": award_awardee,
                "requester_str": payload.get("requester") or current_user.get("name") or current_user.get("email") or "Unknown User",
            }

            new_req = SQL_DraftRequest(
                notice_id=notice_id,
                mode=mode,
                requester=int(current_user["id"]),
                draft_status="pending",
                notes=payload.get("notes", ""),
                extra_data=extra_info,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(new_req)
            await db.commit()
            await db.refresh(new_req)

            if mode == "prime":
                sol_num = str(getattr(tender, "solicitation_number", "") or "")
                if sol_num:
                    background_tasks.add_task(ensure_rfp_downloaded, str(notice_id), sol_num)

            if mode == "prime":

                msg = (
                    f"Prime contractor draft request saved. You can start building the technical "
                    f"response for '{tender.title}' inside the Proposal Builder."
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
                "tender_title": tender.title,
                "target_company": target_company,
                "requested_at": new_req.created_at.isoformat(),
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{notice_id}/request-draft")
async def get_draft_request_status(
    notice_id: str,
    current_user: dict = Depends(get_current_user),
):
    requests_list = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                conds = [SQL_DraftRequest.notice_id == notice_id]
                if notice_id.isdigit():
                    conds.append(SQL_DraftRequest.id == int(notice_id))
                stmt = select(SQL_DraftRequest).where(or_(*conds))

                res = await db.execute(stmt)
                for r in res.scalars().all():
                    extra = r.extra_data or {}
                    requests_list.append({
                        "notice_id": r.notice_id,
                        "mode": r.mode,
                        "tender_title": extra.get("tender_title"),
                        "agency": extra.get("agency"),
                        "solicitation_number": extra.get("solicitation_number"),
                        "naics_code": extra.get("naics_code"),
                        "set_aside": extra.get("set_aside"),
                        "closing_date": extra.get("closing_date"),
                        "days_until_close": extra.get("days_until_close"),
                        "value": extra.get("value"),
                        "tender_status": extra.get("tender_status"),
                        "urgency": extra.get("urgency"),
                        "poc_email": extra.get("poc_email"),
                        "target_company": extra.get("target_company"),
                        "award_awardee": extra.get("award_awardee"),
                        "requester": extra.get("requester_str"),
                        "notes": r.notes or "",
                        "draft_status": r.draft_status.value if hasattr(r.draft_status, "value") else str(r.draft_status or "pending"),
                        "requested_at": r.created_at.isoformat() if getattr(r, "created_at", None) else "",
                    })
        except Exception as e:
            logger.error(f"Failed to fetch draft request status: {e}")

    return {
        "notice_id": notice_id,
        "requests": requests_list,
        "modes_requested": [r["mode"] for r in requests_list],
    }


@router.get("/draft-requests/all")
async def get_all_draft_requests(current_user: dict = Depends(get_current_user)):
    requests_list = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_DraftRequest).order_by(SQL_DraftRequest.created_at.desc())
                res = await db.execute(stmt)
                for r in res.scalars().all():
                    extra = r.extra_data or {}
                    requests_list.append({
                        "notice_id": r.notice_id,
                        "mode": r.mode,
                        "tender_title": extra.get("tender_title") or r.notice_id,
                        "agency": extra.get("agency"),
                        "solicitation_number": extra.get("solicitation_number"),
                        "naics_code": extra.get("naics_code"),
                        "set_aside": extra.get("set_aside"),
                        "closing_date": extra.get("closing_date"),
                        "days_until_close": extra.get("days_until_close"),
                        "value": extra.get("value"),
                        "tender_status": extra.get("tender_status"),
                        "urgency": extra.get("urgency"),
                        "poc_email": extra.get("poc_email"),
                        "target_company": extra.get("target_company"),
                        "award_awardee": extra.get("award_awardee"),
                        "requester": extra.get("requester_str"),
                        "notes": r.notes or "",
                        "draft_status": r.draft_status.value if hasattr(r.draft_status, "value") else str(r.draft_status or "pending"),
                        "requested_at": r.created_at.isoformat() if getattr(r, "created_at", None) else "",
                    })
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return requests_list


def ensure_rfp_downloaded(notice_id: str, solicitation_number: str) -> None:
    downloads_path = Path("downloads") / "opportunities" / solicitation_number / "rfp_docs"
    if downloads_path.exists() and any(downloads_path.iterdir()):
        logger.info(f"[Tenders] RFP docs already downloaded for {solicitation_number}")
        return

    raw_opp = None
    if _mysql_available:
        try:
            with get_sync_db_session() as db:
                row = db.execute(select(SQL_Tender).where(SQL_Tender.id == notice_id)).scalar_one_or_none()
                if row and getattr(row, "raw_sam_data", None):
                    raw_opp = row.raw_sam_data
        except Exception as e:
            logger.warning(f"Failed to query tender raw data from MySQL: {e}")

    from app.sam_gov.opportunities import SAMOpportunitiesClient
    opp_client = SAMOpportunitiesClient()

    if raw_opp is None or not isinstance(raw_opp, dict):
        logger.info(f"[Tenders] Raw data missing. Querying SAM.gov for solicitation: {solicitation_number}")
        try:
            results = opp_client.search_opportunities(query=solicitation_number, posted_days=360)
            if results:
                for opp in results:
                    opp_sol = opp.get("solicitationNumber") or opp.get("solnum") or ""
                    if opp_sol.lower() == solicitation_number.lower():
                        raw_opp = opp
                        break
                if raw_opp is None:
                    raw_opp = results[0]
        except Exception as e:
            logger.error(f"[Tenders] Failed searching SAM.gov: {e}")

    if isinstance(raw_opp, dict):
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
    sol_num = notice_id
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Tender).where(SQL_Tender.id == notice_id)
                tender = (await db.execute(stmt)).scalar_one_or_none()
                if tender:
                    sol_num = _sanitize_path_component(str(getattr(tender, "solicitation_number", "") or notice_id))
        except Exception:
            pass

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

    sol_num = notice_id
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Tender).where(SQL_Tender.id == notice_id)
                tender = (await db.execute(stmt)).scalar_one_or_none()
                if tender:
                    sol_num = _sanitize_path_component(str(getattr(tender, "solicitation_number", "") or notice_id))
        except Exception:
            pass


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
