"""
app/routes/leads.py
--------------------
Lead management & bulk import endpoints using async Motor.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Any, List, Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import get_async_collection

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


async def _assert_campaign_ownership(campaign_id: ObjectId, user_id: ObjectId) -> bool:
    campaigns_col = get_async_collection("campaigns")
    campaign = await campaigns_col.find_one({"_id": campaign_id})
    return bool(campaign)


def _normalize_company_key(name: Optional[str], uei: Optional[str] = "") -> str:
    if uei:
        return f"uei:{str(uei).strip().lower()}"
    return f"name:{re.sub(r'[^a-z0-9]+', '', str(name or '').lower())}"


def _iso(dt: Any) -> Optional[str]:
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


def _format_lead(l: Optional[dict]) -> dict:
    if not l:
        return {}
    return {
        "id": str(l["_id"]),
        "companyName": l.get("companyName", ""),
        "contactName": l.get("contactName", ""),
        "email": l.get("email", ""),
        "title": l.get("title", ""),
        "website": l.get("website", ""),
        "linkedin": l.get("linkedin", ""),
        "campaignId": str(l["campaignId"]),
        "status": l.get("status", "pending"),
        "score": l.get("score", 0),
        "grade": l.get("grade", "cold"),
        "sendAttempts": l.get("sendAttempts", 0),
        "resendCount": l.get("resendCount", 0),
        "lastSendError": l.get("lastSendError", ""),
        "sentAt": _iso(l.get("sentAt")),
        "openedAt": _iso(l.get("openedAt")),
        "clickedAt": _iso(l.get("clickedAt")),
        "repliedAt": _iso(l.get("repliedAt")),
        "bouncedAt": _iso(l.get("bouncedAt")),
        "unsubscribedAt": _iso(l.get("unsubscribedAt")),
        "replyPreview": l.get("replyPreview", ""),
        "createdAt": _iso(l.get("createdAt")),
        "updatedAt": _iso(l.get("updatedAt")),
    }


@router.get("")
async def list_leads(
    campaignId: str,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_oid = ObjectId(campaignId)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_oid, current_user["_id"]):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    leads_col = get_async_collection("leads")
    query: dict = {"campaignId": camp_oid}
    if status:
        query["status"] = status

    leads = await leads_col.find(query).sort("createdAt", -1).limit(2000).to_list(length=2000)
    return {"leads": [_format_lead(l) for l in leads]}


@router.post("", status_code=201)
async def create_lead(
    body: LeadCreateBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_oid = ObjectId(body.campaignId)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_oid, current_user["_id"]):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    normalized = normalize_email(body.email)
    if not is_valid_email(normalized) or not is_plausible_domain(extract_domain(normalized)):
        raise HTTPException(status_code=400, detail="Invalid email address.")

    suppressions_col = get_async_collection("suppressions")
    if await suppressions_col.find_one({"email": normalized}):
        raise HTTPException(status_code=400, detail="Email is on the suppression list.")

    leads_col = get_async_collection("leads")
    if await leads_col.find_one({"campaignId": camp_oid, "email": normalized}):
        raise HTTPException(status_code=409, detail="This email is already a lead in this campaign.")

    company_key = _normalize_company_key(body.companyName, "") if (body.companyName or "").strip() else ""

    doc = {
        "campaignId": camp_oid,
        "companyName": body.companyName or "",
        "companyKey": company_key,
        "contactName": body.contactName or "",
        "email": normalized,
        "title": body.title or "",
        "website": body.website or "",
        "linkedin": body.linkedin or "",
        "status": "pending",
        "score": 0,
        "grade": "cold",
        "sendAttempts": 0,
        "resendCount": 0,
        "lastSendError": "",
        "sentAt": None,
        "openedAt": None,
        "clickedAt": None,
        "repliedAt": None,
        "bouncedAt": None,
        "unsubscribedAt": None,
        "replyPreview": "",
        "createdBy": current_user["_id"],
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }

    result = await leads_col.insert_one(doc)
    lead = await leads_col.find_one({"_id": result.inserted_id})
    return {"lead": _format_lead(lead)}


@router.post("/import/csv")
async def import_leads_csv(
    campaignId: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_oid = ObjectId(campaignId)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_oid, current_user["_id"]):
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

    leads_col = get_async_collection("leads")
    suppressions_col = get_async_collection("suppressions")

    # Batch set lookup for existing and suppressed emails
    extracted_emails = [normalize_email(r.get("email") or "") for r in rows if r.get("email")]
    valid_extracted = [e for e in extracted_emails if is_valid_email(e)]

    existing_docs = await leads_col.find({"campaignId": camp_oid, "email": {"$in": valid_extracted}}, {"email": 1}).to_list(length=len(valid_extracted))
    existing_emails = set(l["email"] for l in existing_docs)

    suppressed_docs = await suppressions_col.find({"email": {"$in": valid_extracted}}, {"email": 1}).to_list(length=len(valid_extracted))
    suppressed_emails = set(s["email"] for s in suppressed_docs)

    report = {"totalRows": len(rows), "imported": 0, "duplicates": 0, "invalidEmail": 0, "suppressed": 0}
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

        to_insert.append({
            "campaignId": camp_oid,
            "companyName": company,
            "contactName": name,
            "email": email,
            "title": title,
            "website": website,
            "linkedin": linkedin,
            "status": "pending",
            "score": 0,
            "grade": "cold",
            "sendAttempts": 0,
            "lastSendError": "",
            "sentAt": None,
            "openedAt": None,
            "clickedAt": None,
            "repliedAt": None,
            "bouncedAt": None,
            "unsubscribedAt": None,
            "replyPreview": "",
            "createdBy": current_user["_id"],
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        })

    if to_insert:
        await leads_col.insert_many(to_insert, ordered=False)
    report["imported"] = len(to_insert)

    return {"report": report}


@router.post("/import/api")
async def import_leads_api(
    body: BulkImportBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_oid = ObjectId(body.campaignId)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_oid, current_user["_id"]):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    leads_col = get_async_collection("leads")
    suppressions_col = get_async_collection("suppressions")

    valid_extracted = [normalize_email(r.email) for r in body.leads if is_valid_email(normalize_email(r.email))]
    
    existing_docs = await leads_col.find({"campaignId": camp_oid, "email": {"$in": valid_extracted}}, {"email": 1}).to_list(length=len(valid_extracted))
    existing_emails = set(l["email"] for l in existing_docs)

    suppressed_docs = await suppressions_col.find({"email": {"$in": valid_extracted}}, {"email": 1}).to_list(length=len(valid_extracted))
    suppressed_emails = set(s["email"] for s in suppressed_docs)

    report = {"totalRows": len(body.leads), "imported": 0, "duplicates": 0, "invalidEmail": 0, "suppressed": 0}
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
        to_insert.append({
            "campaignId": camp_oid,
            "companyName": row.companyName or "",
            "contactName": row.contactName or "",
            "email": email,
            "title": row.title or "",
            "website": row.website or "",
            "linkedin": row.linkedin or "",
            "status": "pending",
            "score": 0,
            "grade": "cold",
            "sendAttempts": 0,
            "lastSendError": "",
            "sentAt": None,
            "openedAt": None,
            "clickedAt": None,
            "repliedAt": None,
            "bouncedAt": None,
            "unsubscribedAt": None,
            "replyPreview": "",
            "createdBy": current_user["_id"],
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        })

    if to_insert:
        await leads_col.insert_many(to_insert, ordered=False)
    report["imported"] = len(to_insert)

    return {"report": report}


@router.get("/companies-in-use")
async def get_companies_in_use(current_user: dict = Depends(get_current_user)):
    campaigns_col = get_async_collection("campaigns")
    leads_col = get_async_collection("leads")

    campaigns = await campaigns_col.find({"createdBy": current_user["_id"]}, {"_id": 1, "name": 1}).to_list(length=1000)
    if not campaigns:
        return {"inUse": []}

    campaign_ids = [c["_id"] for c in campaigns]
    campaign_names = {str(c["_id"]): c.get("name", "") for c in campaigns}

    rows = await leads_col.find(
        {"campaignId": {"$in": campaign_ids}, "companyKey": {"$ne": ""}},
        {"companyKey": 1, "companyName": 1, "campaignId": 1}
    ).to_list(length=5000)

    in_use = []
    seen = set()
    for r in rows:
        key = r.get("companyKey")
        if not key or key in seen:
            continue
        seen.add(key)
        in_use.append({
            "companyKey": key,
            "companyName": r.get("companyName", ""),
            "campaignId": str(r["campaignId"]),
            "campaignName": campaign_names.get(str(r["campaignId"]), ""),
        })

    return {"inUse": in_use}


@router.post("/import/companies")
async def import_leads_from_companies(
    body: BulkCompanyImportBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_oid = ObjectId(body.campaignId)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not await _assert_campaign_ownership(camp_oid, current_user["_id"]):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    leads_col = get_async_collection("leads")
    suppressions_col = get_async_collection("suppressions")
    profile_col = get_async_collection("company_profiles")

    existing_docs = await leads_col.find({"campaignId": camp_oid}, {"email": 1}).to_list(length=10000)
    existing_emails = set(l["email"] for l in existing_docs)
    
    suppressed_docs = await suppressions_col.find({}, {"email": 1}).to_list(length=10000)
    suppressed_emails = set(s["email"] for s in suppressed_docs)

    report = {
        "totalSelected": len(body.companies),
        "added": 0,
        "duplicates": 0,
        "invalidEmail": 0,
        "suppressed": 0,
        "conflicts": [],
    }
    to_insert = []
    used_keys_this_batch = set()

    for company in body.companies:
        email = normalize_email(company.email)
        if not email or "@" not in email:
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
            "campaignId": camp_oid,
            "companyName": company.companyName or "",
            "companyKey": company_key,
            "companyUei": company.uei or "",
            "contactName": company.contactName or "",
            "email": email,
            "title": company.title or "",
            "website": company.website or "",
            "linkedin": company.linkedin or "",
            "status": "pending",
            "score": 0,
            "grade": "cold",
            "sendAttempts": 0,
            "resendCount": 0,
            "lastSendError": "",
            "sentAt": None,
            "openedAt": None,
            "clickedAt": None,
            "repliedAt": None,
            "bouncedAt": None,
            "unsubscribedAt": None,
            "replyPreview": "",
            "createdBy": current_user["_id"],
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        })

    if to_insert:
        await leads_col.insert_many(to_insert, ordered=False)
    report["added"] = len(to_insert)

    return {"report": report}


@router.post("/{id}/resend")
async def resend_lead(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid lead ID.")

    leads_col = get_async_collection("leads")
    lead = await leads_col.find_one({"_id": oid})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    if not await _assert_campaign_ownership(lead["campaignId"], current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized.")

    now = datetime.now(timezone.utc)
    await leads_col.update_one(
        {"_id": oid},
        {
            "$set": {
                "status": "pending",
                "send_after": now,
                "lastSendError": "",
                "updatedAt": now,
            },
            "$inc": {"resendCount": 1},
        }
    )

    campaigns_col = get_async_collection("campaigns")
    await campaigns_col.update_one(
        {"_id": lead["campaignId"]},
        {"$inc": {"stats.totalResent": 1}, "$set": {"updatedAt": now}}
    )

    audit_col = get_async_collection("audit_logs")
    await audit_col.insert_one({
        "action": "lead.resend",
        "entityType": "Lead",
        "entityId": oid,
        "performedBy": current_user["_id"],
        "createdAt": now,
    })

    updated = await leads_col.find_one({"_id": oid})
    return {"lead": _format_lead(updated)}


@router.delete("/{id}")
async def delete_lead(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid lead ID.")

    leads_col = get_async_collection("leads")
    lead = await leads_col.find_one({"_id": oid})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    if not await _assert_campaign_ownership(lead["campaignId"], current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized.")

    await leads_col.delete_one({"_id": oid})
    return {"ok": True}


@router.delete("/suppressions/{email:path}")
async def unsuppress_email(
    email: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove an email address from the suppression list."""
    suppressions_col = get_async_collection("suppressions")
    target = email.strip().lower()
    res = await suppressions_col.delete_one({"email": target})
    return {"ok": True, "deletedCount": res.deleted_count, "email": target}
