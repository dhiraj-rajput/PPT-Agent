"""
app/routes/leads.py
--------------------
Lead management & bulk import endpoints using MySQL (relational) and MongoDB (document store for profiles).
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import get_async_collection, get_db_session, _mysql_available
from models.sql_models import (
    Campaign as SQL_Campaign,
    Lead as SQL_Lead,
    Suppression as SQL_Suppression,
    AuditLog as SQL_AuditLog,
    Person as SQL_Person,
)
from sqlalchemy import select, insert, update, delete, func

router = APIRouter(prefix="/leads", tags=["leads"])

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def is_valid_email(email: str) -> bool:
    return isinstance(email, str) and bool(EMAIL_RE.match(email.strip()))


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def extract_domain(email: str) -> str:
    at = str(email or "").rfind("@")
    return "" if at == -1 else email[at + 1:].lower()


def is_plausible_domain(domain: str) -> bool:
    if not domain or " " in domain:
        return False
    if "." not in domain:
        return False
    if domain in ("localhost", "test.com", "example.com"):
        return False
    return True


class LeadCreateBody(BaseModel):
    campaignId: str
    companyName: Optional[str] = ""
    contactName: Optional[str] = ""
    email: str
    title: Optional[str] = ""
    website: Optional[str] = ""
    linkedin: Optional[str] = ""


class BulkLeadItem(BaseModel):
    companyName: Optional[str] = ""
    contactName: Optional[str] = ""
    email: str
    title: Optional[str] = ""
    website: Optional[str] = ""
    linkedin: Optional[str] = ""


class BulkImportBody(BaseModel):
    campaignId: str
    leads: List[BulkLeadItem]


class CompanySelectItem(BaseModel):
    uei: Optional[str] = ""
    companyName: str
    contactName: Optional[str] = ""
    email: str
    title: Optional[str] = ""
    website: Optional[str] = ""
    linkedin: Optional[str] = ""


class BulkCompanyImportBody(BaseModel):
    campaignId: str
    companies: List[CompanySelectItem]


async def _assert_campaign_ownership(campaign_id: int, user_id: int) -> bool:
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Campaign).where(SQL_Campaign.id == campaign_id)
                res = await db.execute(stmt)
                campaign = res.scalar_one_or_none()
                return bool(campaign)
        except Exception:
            pass
    return False


def _normalize_company_key(name: Optional[str], uei: Optional[str] = "") -> str:
    if uei:
        return f"uei:{str(uei).strip().lower()}"
    return f"name:{re.sub(r'[^a-z0-9]+', '', str(name or '').lower())}"


def _iso(dt: Any) -> Optional[str]:
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


def _format_lead(l: SQL_Lead) -> dict:
    if not l:
        return {}
    return {
        "id": str(l.id),
        "companyName": l.company_name or "",
        "contactName": l.contact_name or "",
        "email": l.email or "",
        "title": l.title or "",
        "website": l.website or "",
        "linkedin": l.linkedin or "",
        "campaignId": str(l.campaign_id),
        "status": l.status or "pending",
        "score": l.score or 0,
        "grade": l.grade or "cold",
        "sendAttempts": l.send_attempts or 0,
        "resendCount": l.resend_count or 0,
        "lastSendError": l.last_send_error or "",
        "sentAt": _iso(l.sent_at),
        "openedAt": _iso(l.opened_at),
        "clickedAt": _iso(l.clicked_at),
        "repliedAt": _iso(l.replied_at),
        "bouncedAt": _iso(l.bounced_at),
        "unsubscribedAt": _iso(l.unsubscribed_at),
        "replyPreview": l.reply_preview or "",
        "createdAt": _iso(l.created_at),
        "updatedAt": _iso(l.updated_at),
    }


@router.get("")
async def list_leads(
    campaignId: str,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_id = int(campaignId)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_id, int(current_user["id"])):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    leads = []
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Lead).where(SQL_Lead.campaign_id == camp_id)
                if status:
                    stmt = stmt.where(SQL_Lead.status == status)
                stmt = stmt.order_by(SQL_Lead.created_at.desc()).limit(2000)
                res = await db.execute(stmt)
                leads = [_format_lead(l) for l in res.scalars().all()]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"leads": leads}


@router.post("", status_code=201)
async def create_lead(
    body: LeadCreateBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_id = int(body.campaignId)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_id, int(current_user["id"])):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    normalized = normalize_email(body.email)
    if not is_valid_email(normalized) or not is_plausible_domain(extract_domain(normalized)):
        raise HTTPException(status_code=400, detail="Invalid email address.")

    user_id = int(current_user["id"])

    if _mysql_available:
        try:
            async for db in get_db_session():
                # Suppression check
                stmt_sup = select(SQL_Suppression).where(SQL_Suppression.email == normalized)
                sup = (await db.execute(stmt_sup)).scalar_one_or_none()
                if sup:
                    raise HTTPException(status_code=400, detail="Email is on the suppression list.")

                # Duplicate check
                stmt_dup = select(SQL_Lead).where(SQL_Lead.campaign_id == camp_id, SQL_Lead.email == normalized)
                dup = (await db.execute(stmt_dup)).scalar_one_or_none()
                if dup:
                    raise HTTPException(status_code=409, detail="This email is already a lead in this campaign.")

                company_key = _normalize_company_key(body.companyName, "") if (body.companyName or "").strip() else ""

                stmt = insert(SQL_Lead).values(
                    campaign_id=camp_id,
                    company_name=body.companyName or "",
                    company_key=company_key,
                    company_uei="",
                    contact_name=body.contactName or "",
                    email=normalized,
                    title=body.title or "",
                    website=body.website or "",
                    linkedin=body.linkedin or "",
                    status="pending",
                    score=0,
                    grade="cold",
                    send_attempts=0,
                    resend_count=0,
                    last_send_error="",
                    sent_at=None,
                    opened_at=None,
                    clicked_at=None,
                    replied_at=None,
                    bounced_at=None,
                    unsubscribed_at=None,
                    reply_preview="",
                    created_by=user_id,
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
                )
                await db.execute(stmt)
                await db.commit()

                stmt_new = select(SQL_Lead).where(SQL_Lead.campaign_id == body.campaignId, SQL_Lead.email == normalized).order_by(SQL_Lead.id.desc())
                lead = (await db.execute(stmt_new)).scalar_one()
                return {"lead": _format_lead(lead)}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


@router.post("/import/csv")
async def import_leads_csv(
    campaignId: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_id = int(campaignId)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_id, int(current_user["id"])):
        raise HTTPException(status_code=404, detail="Campaign not found.")

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
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    user_id = int(current_user["id"])
    report = {"totalRows": len(rows), "imported": 0, "duplicates": 0, "invalidEmail": 0, "suppressed": 0}

    if _mysql_available:
        try:
            async for db in get_db_session():
                extracted_emails = [normalize_email(r.get("email") or "") for r in rows if r.get("email")]
                valid_extracted = [e for e in extracted_emails if is_valid_email(e)]

                if valid_extracted:
                    stmt_existing = select(SQL_Lead.email).where(SQL_Lead.campaign_id == camp_id, SQL_Lead.email.in_(valid_extracted))
                    existing_emails = set((await db.execute(stmt_existing)).scalars().all())

                    stmt_sup = select(SQL_Suppression.email).where(SQL_Suppression.email.in_(valid_extracted))
                    suppressed_emails = set((await db.execute(stmt_sup)).scalars().all())
                else:
                    existing_emails = set()
                    suppressed_emails = set()

                to_insert = []
                for row in rows:
                    raw_email = row.get("email") or ""
                    email = normalize_email(raw_email)

                    if not is_valid_email(email) or not is_plausible_domain(extract_domain(email)):
                        report["invalidEmail"] += 1
                        continue
                    if email in existing_emails:
                        report["duplicates"] += 1
                        continue
                    if email in suppressed_emails:
                        report["suppressed"] += 1
                        continue

                    existing_emails.add(email)

                    company = row.get("companyname") or row.get("company") or ""
                    name = row.get("contactname") or row.get("name") or ""
                    title = row.get("title") or ""
                    website = row.get("website") or ""
                    linkedin = row.get("linkedin") or ""
                    company_key = _normalize_company_key(company, "") if company.strip() else ""

                    to_insert.append({
                        "campaign_id": camp_id,
                        "company_name": company,
                        "company_key": company_key,
                        "company_uei": "",
                        "contact_name": name,
                        "email": email,
                        "title": title,
                        "website": website,
                        "linkedin": linkedin,
                        "status": "pending",
                        "score": 0,
                        "grade": "cold",
                        "send_attempts": 0,
                        "resend_count": 0,
                        "last_send_error": "",
                        "sent_at": None,
                        "opened_at": None,
                        "clicked_at": None,
                        "replied_at": None,
                        "bounced_at": None,
                        "unsubscribed_at": None,
                        "reply_preview": "",
                        "created_by": user_id,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    })

                if to_insert:
                    await db.execute(insert(SQL_Lead).values(to_insert))
                    await db.commit()
                report["imported"] = len(to_insert)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"report": report}


@router.post("/import/api")
async def import_leads_api(
    body: BulkImportBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_id = int(body.campaignId)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_id, int(current_user["id"])):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    user_id = int(current_user["id"])
    report = {"totalRows": len(body.leads), "imported": 0, "duplicates": 0, "invalidEmail": 0, "suppressed": 0}

    if _mysql_available:
        try:
            async for db in get_db_session():
                valid_extracted = [normalize_email(r.email) for r in body.leads if is_valid_email(normalize_email(r.email))]

                if valid_extracted:
                    stmt_existing = select(SQL_Lead.email).where(SQL_Lead.campaign_id == camp_id, SQL_Lead.email.in_(valid_extracted))
                    existing_emails = set((await db.execute(stmt_existing)).scalars().all())

                    stmt_sup = select(SQL_Suppression.email).where(SQL_Suppression.email.in_(valid_extracted))
                    suppressed_emails = set((await db.execute(stmt_sup)).scalars().all())
                else:
                    existing_emails = set()
                    suppressed_emails = set()

                to_insert = []
                for row in body.leads:
                    email = normalize_email(row.email)

                    if not is_valid_email(email) or not is_plausible_domain(extract_domain(email)):
                        report["invalidEmail"] += 1
                        continue
                    if email in existing_emails:
                        report["duplicates"] += 1
                        continue
                    if email in suppressed_emails:
                        report["suppressed"] += 1
                        continue

                    existing_emails.add(email)
                    company_key = _normalize_company_key(row.companyName, "") if (row.companyName or "").strip() else ""

                    to_insert.append({
                        "campaign_id": camp_id,
                        "company_name": row.companyName or "",
                        "company_key": company_key,
                        "company_uei": "",
                        "contact_name": row.contactName or "",
                        "email": email,
                        "title": row.title or "",
                        "website": row.website or "",
                        "linkedin": row.linkedin or "",
                        "status": "pending",
                        "score": 0,
                        "grade": "cold",
                        "send_attempts": 0,
                        "resend_count": 0,
                        "last_send_error": "",
                        "sent_at": None,
                        "opened_at": None,
                        "clicked_at": None,
                        "replied_at": None,
                        "bounced_at": None,
                        "unsubscribed_at": None,
                        "reply_preview": "",
                        "created_by": user_id,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    })

                if to_insert:
                    await db.execute(insert(SQL_Lead).values(to_insert))
                    await db.commit()
                report["imported"] = len(to_insert)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"report": report}


@router.get("/companies-in-use")
async def get_companies_in_use(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    in_use = []

    if _mysql_available:
        try:
            async for db in get_db_session():
                # Get campaigns by user
                stmt_camp = select(SQL_Campaign).where(SQL_Campaign.user_id == user_id)
                res_camp = await db.execute(stmt_camp)
                campaigns = res_camp.scalars().all()
                if not campaigns:
                    return {"inUse": []}

                campaign_ids = [c.id for c in campaigns]
                campaign_names = {str(c.id): c.name or "" for c in campaigns}

                # Get leads with company keys in those campaigns
                stmt_leads = select(SQL_Lead).where(
                    SQL_Lead.campaign_id.in_(campaign_ids),
                    SQL_Lead.company_key != ""
                )
                res_leads = await db.execute(stmt_leads)
                rows = res_leads.scalars().all()

                seen = set()
                for r in rows:
                    key = str(getattr(r, "company_key", "") or "")
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    in_use.append({
                        "companyKey": key,
                        "companyName": r.company_name or "",
                        "campaignId": str(r.campaign_id),
                        "campaignName": campaign_names.get(str(r.campaign_id), ""),
                    })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"inUse": in_use}


@router.post("/import/companies")
async def import_leads_from_companies(
    body: BulkCompanyImportBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_id = int(body.campaignId)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_id, int(current_user["id"])):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    user_id = int(current_user["id"])

    # Profiles stays in MongoDB (document store)
    profile_col = get_async_collection("company_profiles")

    report = {
        "totalSelected": len(body.companies),
        "added": 0,
        "duplicates": 0,
        "invalidEmail": 0,
        "suppressed": 0,
        "conflicts": [],
    }

    if _mysql_available:
        try:
            async for db in get_db_session():
                # Get existing emails
                stmt_existing = select(SQL_Lead.email).where(SQL_Lead.campaign_id == camp_id)
                existing_emails = set((await db.execute(stmt_existing)).scalars().all())

                # Get all suppressed emails
                stmt_sup = select(SQL_Suppression.email)
                suppressed_emails = set((await db.execute(stmt_sup)).scalars().all())

                to_insert = []
                used_keys_this_batch = set()

                for company in body.companies:
                    email = normalize_email(company.email)
                    if not email or "@" not in email:
                        # MongoDB query
                        profile = await profile_col.find_one({
                            "company_name": {"$regex": f"^{re.escape(company.companyName)}$", "$options": "i"}
                        })
                        if profile and profile.get("emails"):
                            email = normalize_email(str(profile["emails"][0]))
                        else:
                            report["invalidEmail"] += 1
                            continue

                    if not is_valid_email(email) or not is_plausible_domain(extract_domain(email)):
                        report["invalidEmail"] += 1
                        continue
                    if email in existing_emails:
                        report["duplicates"] += 1
                        continue
                    if email in suppressed_emails:
                        report["suppressed"] += 1
                        continue

                    company_key = _normalize_company_key(company.companyName, company.uei)

                    if company_key in used_keys_this_batch:
                        report["duplicates"] += 1
                        continue

                    existing_emails.add(email)
                    used_keys_this_batch.add(company_key)

                    to_insert.append({
                        "campaign_id": camp_id,
                        "company_name": company.companyName or "",
                        "company_key": company_key,
                        "company_uei": company.uei or "",
                        "contact_name": company.contactName or "",
                        "email": email,
                        "title": company.title or "",
                        "website": company.website or "",
                        "linkedin": company.linkedin or "",
                        "status": "pending",
                        "score": 0,
                        "grade": "cold",
                        "send_attempts": 0,
                        "resend_count": 0,
                        "last_send_error": "",
                        "sent_at": None,
                        "opened_at": None,
                        "clicked_at": None,
                        "replied_at": None,
                        "bounced_at": None,
                        "unsubscribed_at": None,
                        "reply_preview": "",
                        "created_by": user_id,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    })

                if to_insert:
                    await db.execute(insert(SQL_Lead).values(to_insert))
                    await db.commit()
                report["added"] = len(to_insert)
            return {"report": report}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))



@router.post("/{lead_id}/resend")
async def resend_lead_email(lead_id: int, current_user: dict = Depends(get_current_user)):
    """
    Reset a lead back to pending status so it will be resent on the next worker run.
    Increments resend_count, updates campaign totalResent stats, and logs an audit record.
    """
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Lead).where(SQL_Lead.id == lead_id)
                res = await db.execute(stmt)
                lead = res.scalar_one_or_none()
                if not lead:
                    raise HTTPException(status_code=404, detail="Lead not found.")

                if not await _assert_campaign_ownership(int(getattr(lead, "campaign_id", 0) or 0), int(current_user["id"])):
                    raise HTTPException(status_code=403, detail="Not authorized.")


                now = datetime.utcnow()
                await db.execute(
                    update(SQL_Lead)
                    .where(SQL_Lead.id == lead_id)
                    .values(status="pending", send_after=now, last_send_error="", resend_count=SQL_Lead.resend_count + 1, updated_at=now)
                )

                # Update campaign stats
                campaign_row = (await db.execute(select(SQL_Campaign).where(SQL_Campaign.id == lead.campaign_id))).scalar_one()
                raw_stats = getattr(campaign_row, "stats", {})
                stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                stats["totalResent"] = int(str(stats.get("totalResent", 0) or 0)) + 1



                await db.execute(
                    update(SQL_Campaign)
                    .where(SQL_Campaign.id == lead.campaign_id)
                    .values(stats=stats, updated_at=now)
                )


                # Audit Log
                await db.execute(insert(SQL_AuditLog).values(
                    action="lead.resend",
                    entity_type="Lead",
                    entity_id=str(lead_id),
                    performed_by=int(current_user["id"]),
                    created_at=now
                ))
                await db.commit()

                # refetch
                stmt_new = select(SQL_Lead).where(SQL_Lead.id == lead_id)
                updated = (await db.execute(stmt_new)).scalar_one()
                return {"lead": _format_lead(updated)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


@router.delete("/{id}")
async def delete_lead(id: str, current_user: dict = Depends(get_current_user)):
    try:
        lead_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lead ID.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Lead).where(SQL_Lead.id == lead_id)
                res = await db.execute(stmt)
                lead = res.scalar_one_or_none()
                if not lead:
                    raise HTTPException(status_code=404, detail="Lead not found.")

                if not await _assert_campaign_ownership(int(getattr(lead, "campaign_id", 0) or 0), int(current_user["id"])):

                    raise HTTPException(status_code=403, detail="Not authorized.")

                await db.execute(delete(SQL_Lead).where(SQL_Lead.id == lead_id))
                await db.commit()
                return {"ok": True}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


@router.delete("/suppressions/{email:path}")
async def unsuppress_email(
    email: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove an email address from the suppression list."""
    if current_user.get('role') not in ('Admin', 'Owner', 'Administrator'):
        raise HTTPException(403, 'Only administrators can manage the suppression list.')
    target = email.strip().lower()
    if _mysql_available:
        try:
            async for db in get_db_session():
                await db.execute(delete(SQL_Suppression).where(SQL_Suppression.email == target))
                await db.commit()
                return {"ok": True, "deletedCount": 1, "email": target}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
    raise HTTPException(status_code=500, detail="MySQL database is unavailable.")


# ---------------------------------------------------------------------------
# People leads import
# ---------------------------------------------------------------------------

class PeopleImportBody(BaseModel):
    campaignId: str
    peopleIds: List[int]
    segmentTag: Optional[str] = ""


@router.post("/import/people")
async def import_people_to_campaign(
    body: PeopleImportBody,
    current_user: dict = Depends(get_current_user),
):
    """Import People records as leads into a campaign."""
    try:
        camp_id = int(body.campaignId)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_id, int(current_user["id"])):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    imported = duplicates = invalid_email = 0
    user_id = int(current_user["id"])

    if not _mysql_available:
        raise HTTPException(status_code=500, detail="Database unavailable.")

    try:
        async for db in get_db_session():
            # Get suppressed emails
            supp_rows = (await db.execute(select(SQL_Suppression.email))).scalars().all()
            suppressed_set = set(supp_rows)

            # Get existing lead emails for this campaign
            existing_rows = (await db.execute(
                select(SQL_Lead.email).where(SQL_Lead.campaign_id == camp_id)
            )).scalars().all()
            existing_set = set(existing_rows)

            # Fetch people
            people_rows = (await db.execute(
                select(SQL_Person).where(SQL_Person.id.in_(body.peopleIds))
            )).scalars().all()

            for person in people_rows:
                raw_email = normalize_email(person.email or "")
                if not raw_email or not is_valid_email(raw_email):
                    invalid_email += 1
                    continue
                if raw_email in suppressed_set:
                    invalid_email += 1
                    continue
                if raw_email in existing_set:
                    duplicates += 1
                    continue

                full_name = person.full_name or f"{person.first_name or ''} {person.last_name or ''}".strip() or raw_email
                company = person.organization_name or ""

                await db.execute(insert(SQL_Lead).values(
                    campaign_id=camp_id,
                    people_id=person.id if hasattr(SQL_Lead, 'people_id') else None,
                    people_name=full_name if hasattr(SQL_Lead, 'people_name') else None,
                    company_name=company,
                    company_key=_normalize_company_key(company),
                    company_uei="",
                    contact_name=full_name,
                    email=raw_email,
                    title=person.title or "",
                    website="",
                    linkedin=person.linkedin_url or "",
                    status="pending",
                    score=0,
                    grade="cold",
                    send_attempts=0,
                    resend_count=0,
                    segment_tag=body.segmentTag if hasattr(SQL_Lead, 'segment_tag') else None,
                    created_by=user_id,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                ))
                existing_set.add(raw_email)
                imported += 1

            await db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return {"imported": imported, "duplicates": duplicates, "invalidEmail": invalid_email}


@router.get("/people-filters")
async def get_people_filters(current_user: dict = Depends(get_current_user)):
    """Return filter options for People segmentation in campaigns."""
    countries = []
    seniorities = []
    has_email_count = 0
    has_phone_count = 0
    has_linkedin_count = 0

    if _mysql_available:
        try:
            async for db in get_db_session():
                # Countries
                c_rows = (await db.execute(
                    select(SQL_Person.country).where(
                        SQL_Person.country != None, SQL_Person.country != ""
                    ).distinct().order_by(SQL_Person.country).limit(100)
                )).scalars().all()
                countries = list(c_rows)

                # Seniorities
                s_rows = (await db.execute(
                    select(SQL_Person.seniority).where(
                        SQL_Person.seniority != None, SQL_Person.seniority != ""
                    ).distinct().order_by(SQL_Person.seniority).limit(50)
                )).scalars().all()
                seniorities = list(s_rows)

                # Counts
                has_email_count = (await db.execute(
                    select(func.count()).select_from(SQL_Person).where(
                        SQL_Person.email != None, SQL_Person.email != ""
                    )
                )).scalar() or 0

                has_phone_count = (await db.execute(
                    select(func.count()).select_from(SQL_Person).where(
                        SQL_Person.phone != None, SQL_Person.phone != ""
                    )
                )).scalar() or 0

                has_linkedin_count = (await db.execute(
                    select(func.count()).select_from(SQL_Person).where(
                        SQL_Person.linkedin_url != None, SQL_Person.linkedin_url != ""
                    )
                )).scalar() or 0
        except Exception as e:
            pass

    return {
        "countries": countries,
        "seniorities": seniorities,
        "hasEmailCount": has_email_count,
        "hasPhoneCount": has_phone_count,
        "hasLinkedinCount": has_linkedin_count,
    }

