import csv
import io
import re
from datetime import datetime, timezone
from typing import List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import get_collection

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


def _assert_campaign_ownership(campaign_id: ObjectId, user_id: ObjectId) -> bool:
    campaigns_col = get_collection("campaigns")
    campaign = campaigns_col.find_one({"_id": campaign_id, "createdBy": user_id})
    return bool(campaign)


def _format_lead(l: dict) -> dict:
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
        "lastSendError": l.get("lastSendError", ""),
        "sentAt": l.get("sentAt").isoformat() if l.get("sentAt") else None,
        "openedAt": l.get("openedAt").isoformat() if l.get("openedAt") else None,
        "clickedAt": l.get("clickedAt").isoformat() if l.get("clickedAt") else None,
        "repliedAt": l.get("repliedAt").isoformat() if l.get("repliedAt") else None,
        "bouncedAt": l.get("bouncedAt").isoformat() if l.get("bouncedAt") else None,
        "unsubscribedAt": l.get("unsubscribedAt").isoformat() if l.get("unsubscribedAt") else None,
        "replyPreview": l.get("replyPreview", ""),
        "createdAt": l.get("createdAt").isoformat() if l.get("createdAt") else None,
        "updatedAt": l.get("updatedAt").isoformat() if l.get("updatedAt") else None,
    }


@router.get("")
def list_leads(
    campaignId: str,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_oid = ObjectId(campaignId)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not _assert_campaign_ownership(camp_oid, current_user["_id"]):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    leads_col = get_collection("leads")
    query = {"campaignId": camp_oid}
    if status:
        query["status"] = status

    leads = list(leads_col.find(query).sort("createdAt", -1).limit(2000))
    return {"leads": [_format_lead(l) for l in leads]}


@router.post("", status_code=201)
def create_lead(
    body: LeadCreateBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_oid = ObjectId(body.campaignId)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not _assert_campaign_ownership(camp_oid, current_user["_id"]):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    normalized = normalize_email(body.email)
    if not is_valid_email(normalized) or not is_plausible_domain(extract_domain(normalized)):
        raise HTTPException(status_code=400, detail="Invalid email address.")

    suppressions_col = get_collection("suppressions")
    if suppressions_col.find_one({"email": normalized}):
        raise HTTPException(status_code=400, detail="Email is on the suppression list.")

    leads_col = get_collection("leads")
    # Check duplicate in campaign
    if leads_col.find_one({"campaignId": camp_oid, "email": normalized}):
        raise HTTPException(status_code=409, detail="This email is already a lead in this campaign.")

    doc = {
        "campaignId": camp_oid,
        "companyName": body.companyName or "",
        "contactName": body.contactName or "",
        "email": normalized,
        "title": body.title or "",
        "website": body.website or "",
        "linkedin": body.linkedin or "",
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
    }

    result = leads_col.insert_one(doc)
    lead = leads_col.find_one({"_id": result.inserted_id})
    return {"lead": _format_lead(lead)}


@router.post("/import/csv")
async def import_leads_csv(
    campaignId: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_oid = ObjectId(campaignId)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not _assert_campaign_ownership(camp_oid, current_user["_id"]):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    contents = await file.read()
    try:
        content_str = contents.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content_str))
        if reader.fieldnames:
            reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
        rows = list(reader)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    leads_col = get_collection("leads")
    suppressions_col = get_collection("suppressions")

    existing_emails = set(l["email"] for l in leads_col.find({"campaignId": camp_oid}, {"email": 1}))
    suppressed_emails = set(s["email"] for s in suppressions_col.find({}, {"email": 1}))

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

        existing_emails.add(email)  # Guard against duplicates in same CSV

        # Handle mapped header variants
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
        leads_col.insert_many(to_insert, ordered=False)
    report["imported"] = len(to_insert)

    return {"report": report}


@router.post("/import/api")
def import_leads_api(
    body: BulkImportBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        camp_oid = ObjectId(body.campaignId)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID.")

    if not _assert_campaign_ownership(camp_oid, current_user["_id"]):
        raise HTTPException(status_code=404, detail="Campaign not found.")

    leads_col = get_collection("leads")
    suppressions_col = get_collection("suppressions")

    existing_emails = set(l["email"] for l in leads_col.find({"campaignId": camp_oid}, {"email": 1}))
    suppressed_emails = set(s["email"] for s in suppressions_col.find({}, {"email": 1}))

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
        leads_col.insert_many(to_insert, ordered=False)
    report["imported"] = len(to_insert)

    return {"report": report}


@router.delete("/{id}")
def delete_lead(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead ID.")

    leads_col = get_collection("leads")
    lead = leads_col.find_one({"_id": oid})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    if not _assert_campaign_ownership(lead["campaignId"], current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized.")

    leads_col.delete_one({"_id": oid})
    return {"ok": True}
