"""
app/routes/companies.py
-------------------------
Company intelligence, search, filtering, and research management endpoints.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import (
    get_async_collection,
    get_collection,
    update_task_status,
    get_task_status_db,
)
from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/companies", tags=["companies"])


def import_sam_entities_csv():
    """Initialise / populate SAM entities in companies collection from CSV if empty."""
    try:
        col = get_collection("companies")
        if col.count_documents({}) > 0:
            return
        
        csv_path = Path("documents/sam_entities.csv")
        if not csv_path.exists():
            return
            
        logger.info("Seeding initial company database from sam_entities.csv...")
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            batch = []
            for row in reader:
                uei = (row.get("UEI") or row.get("uei", "")).strip()
                if uei:
                    is_small = (row.get("Is_Small_Business") or row.get("is_small_business", "")).strip().upper() in ("Y", "YES", "TRUE")
                    batch.append({
                        "uei": uei,
                        "name": row.get("Legal_Business_Name") or row.get("name") or "Unnamed Company",
                        "status": row.get("Registration_Status") or row.get("status") or "Active",
                        "primary_naics": row.get("Primary_NAICS_Code") or row.get("primary_naics") or "",
                        "primary_naics_desc": row.get("Primary_NAICS_Description") or row.get("primary_naics_desc") or "",
                        "size": "Small" if is_small else "Large",
                        "matchScore": random.randint(75, 98),
                        "industry": row.get("Primary_NAICS_Description") or "Other",
                        "contact": row.get("Gov_Contact_Name") or "N/A",
                        "email": row.get("Gov_Contact_Email") or "info@company.com"
                    })
                if len(batch) >= 500:
                    col.insert_many(batch, ordered=False)
                    batch = []
            if batch:
                col.insert_many(batch, ordered=False)
        logger.info("SAM entities seeded successfully.")
    except Exception as e:
        logger.warning(f"Failed to seed SAM entities CSV: {e}")


class SendCompanyEmailBody(BaseModel):
    to_email: str
    subject: str
    body: str
    proposal_filename: Optional[str] = None
    rfp_filename: Optional[str] = None


@router.get("/attachments")
def get_attachments(current_user: dict = Depends(get_current_user)):
    """List all available proposal and RFP PDF files that can be attached to emails."""
    attachments = []
    
    pdf_dir = Path("output/pdf")
    if pdf_dir.exists():
        for f in pdf_dir.glob("*.pdf"):
            attachments.append({
                "filename": f.name,
                "type": "proposal",
                "label": f"Proposal: {f.name}"
            })
            
    rfp_respond_dir = Path("output/rfp_respond")
    if rfp_respond_dir.exists():
        for f in rfp_respond_dir.glob("*"):
            if f.is_file() and not f.name.startswith("."):
                attachments.append({
                    "filename": f.name,
                    "type": "rfp_respond",
                    "label": f"RFP Respond: {f.name}"
                })
                
    uploads_dir = Path("private/rfp_respond_uploads")
    if uploads_dir.exists():
        for p in uploads_dir.rglob("*"):
            if p.is_file() and not p.name.startswith("."):
                attachments.append({
                    "filename": p.name,
                    "type": "uploaded_rfp",
                    "label": f"Uploaded RFP: {p.name}"
                })
                
    return {"attachments": attachments}


@router.post("/send-email")
async def send_company_email(body: SendCompanyEmailBody, current_user: dict = Depends(get_current_user)):
    """Send a custom email to a company with optional attachments (proposal/RFP)."""
    if not body.to_email:
        raise HTTPException(status_code=400, detail="Recipient email is required.")
    
    attachments_list = []
    
    def locate_and_add_file(filename: str):
        dirs = [
            Path("output/pdf"),
            Path("output/rfp_respond"),
            Path("private/rfp_respond_uploads")
        ]
        for d in dirs:
            if d.exists():
                p = d / filename
                if p.exists() and p.is_file():
                    attachments_list.append({
                        "path": str(p.resolve()),
                        "filename": filename
                    })
                    return True
                for found in d.rglob(filename):
                    if found.is_file():
                        attachments_list.append({
                            "path": str(found.resolve()),
                            "filename": filename
                        })
                        return True
        return False

    if body.proposal_filename:
        found = locate_and_add_file(body.proposal_filename)
        if not found:
            raise HTTPException(status_code=404, detail=f"Proposal file '{body.proposal_filename}' not found on server.")
            
    if body.rfp_filename:
        if body.rfp_filename != body.proposal_filename:
            found = locate_and_add_file(body.rfp_filename)
            if not found:
                raise HTTPException(status_code=404, detail=f"RFP file '{body.rfp_filename}' not found on server.")

    from app.core.mailer import send_company_email_with_attachments
    try:
        await send_company_email_with_attachments(
            to_email=body.to_email,
            subject=body.subject,
            body_html=body.body,
            attachments=attachments_list
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
        
    return {"ok": True, "message": "Email sent successfully!"}


@router.get("")
async def get_companies(
    query: Optional[str] = None,
    size: Optional[str] = None,
    naics: Optional[str] = None,
    researched: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Query companies from MongoDB with search, filters, and pagination using Motor."""
    try:
        col = get_async_collection("companies")
        filter_query = {}

        if query:
            q = re.escape(query.strip())
            filter_query["$or"] = [
                {"name": {"$regex": q, "$options": "i"}},
                {"uei": {"$regex": q, "$options": "i"}},
                {"contact": {"$regex": q, "$options": "i"}},
                {"email": {"$regex": q, "$options": "i"}}
            ]

        if size and size != "All":
            filter_query["size"] = size

        if naics and naics != "All":
            naics_escaped = re.escape(naics.strip())
            naics_condition = {"$or": [
                {"primary_naics": {"$regex": naics_escaped, "$options": "i"}},
                {"primary_naics_desc": {"$regex": naics_escaped, "$options": "i"}}
            ]}
            if "$or" in filter_query:
                filter_query["$and"] = [
                    {"$or": filter_query.pop("$or")},
                    naics_condition,
                ]
            else:
                filter_query.update(naics_condition)

        profiles_col = get_async_collection("company_profiles")
        tasks_col = get_async_collection("task_statuses")
        
        active_task_docs = await tasks_col.find({"type": "company_research"}).to_list(length=1000)
        active_tasks = {t["task_id"].lower(): t["status"] for t in active_task_docs}

        # Identity sets for profile check
        profile_names = set()
        profile_slugs = set()
        profiles_cursor = profiles_col.find({}, {"company_name": 1, "company_slug": 1})
        async for p in profiles_cursor:
            if p.get("company_name"):
                profile_names.add(p["company_name"].strip().lower())
            if p.get("company_slug"):
                profile_slugs.add(p["company_slug"])

        def _slugify(name: str) -> str:
            return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")

        def _is_researched(c: dict) -> bool:
            if bool(c.get("is_researched")) or c.get("research_status") == "completed":
                return True
            name = (c.get("name") or "").strip().lower()
            return name in profile_names or _slugify(c.get("name") or "") in profile_slugs

        researched_norm = (researched or "").strip().lower()
        wants_researched_filter = researched_norm in ("true", "false", "researched", "not_researched")

        if wants_researched_filter:
            want_true = researched_norm in ("true", "researched")
            all_matching = await col.find(filter_query, {"_id": 0}).to_list(length=10000)
            filtered = [c for c in all_matching if _is_researched(c) == want_true]
            total = len(filtered)
            skip = (page - 1) * limit
            results = filtered[skip:skip + limit]
        else:
            total = await col.count_documents(filter_query)
            skip = (page - 1) * limit
            results = await col.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(length=limit)

        # Batch lookup profiles for the paginated results (Fixes N+1 query)
        company_names = [c["name"] for c in results if c.get("name")]
        company_slugs = [_slugify(c["name"]) for c in results if c.get("name")]
        
        prof_map = {}
        if company_names:
            name_regexes = [{"company_name": {"$regex": f"^{re.escape(n)}$", "$options": "i"}} for n in company_names]
            slug_matches = [{"company_slug": {"$in": company_slugs}}]
            or_conditions = name_regexes + slug_matches
            
            matched_profiles = await profiles_col.find({"$or": or_conditions}).to_list(length=len(results) * 2)
            for p in matched_profiles:
                p_name = (p.get("company_name") or "").lower().strip()
                p_slug = p.get("company_slug") or ""
                if p_name:
                    prof_map[p_name] = p
                if p_slug:
                    prof_map[p_slug] = p

        for c in results:
            c_name_lower = (c.get("name") or "").lower().strip()
            c_slug = _slugify(c.get("name"))
            profile = prof_map.get(c_name_lower) or prof_map.get(c_slug)
            
            is_researched_flag = _is_researched(c) or bool(profile)

            if profile:
                if (not c.get("email") or not c["email"].strip()) and profile.get("emails"):
                    c["email"] = profile["emails"][0]
                if (not c.get("phone") or not c["phone"].strip()) and profile.get("phone_numbers"):
                    c["phone"] = profile["phone_numbers"][0]
                if (not c.get("contact") or c.get("contact") == "N/A") and profile.get("leadership"):
                    c["contact"] = profile["leadership"][0]

            c["hasResearchedProfile"] = is_researched_flag
            c["is_researched"] = is_researched_flag
            c["isResearching"] = active_tasks.get((c.get("name") or "").lower()) == "processing"

        naics_list = await col.distinct("primary_naics_desc")
        naics_list = sorted([n for n in naics_list if n])

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "companies": results,
            "naics_codes": naics_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CompanyCreateBody(BaseModel):
    uei: str
    name: str
    dba_name: Optional[str] = ""
    cage_code: Optional[str] = ""
    status: Optional[str] = "Active"
    registration_date: Optional[str] = ""
    expiration_date: Optional[str] = ""
    address: Optional[str] = ""
    location: Optional[str] = ""
    city: Optional[str] = ""
    state: Optional[str] = ""
    zip: Optional[str] = ""
    country: Optional[str] = ""
    entity_structure: Optional[str] = ""
    is_small_business: Optional[str] = ""
    is_minority_owned: Optional[str] = ""
    is_women_owned: Optional[str] = ""
    is_veteran_owned: Optional[str] = ""
    primary_naics: Optional[str] = ""
    primary_naics_desc: Optional[str] = ""
    secondary_naics: Optional[str] = ""
    contact: Optional[str] = "N/A"
    contact_role: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    revenue: Optional[str] = ""
    size: Optional[str] = "Small"
    industry: Optional[str] = "Other"
    matchScore: Optional[int] = None


@router.post("")
async def add_company(
    company_data: CompanyCreateBody,
    current_user: dict = Depends(get_current_user),
):
    """Add a single company record manually using Motor."""
    col = get_async_collection("companies")
    uei = company_data.uei.strip()
    if not uei:
        raise HTTPException(status_code=400, detail="UEI is required")

    if await col.find_one({"uei": uei}):
        raise HTTPException(status_code=400, detail="Company with this UEI already exists")

    doc = company_data.model_dump()
    doc["matchScore"] = doc.get("matchScore") or random.randint(70, 98)
    doc["industry"] = doc.get("industry") or doc.get("primary_naics_desc") or "Other"
    doc["contact"] = doc.get("contact") or "N/A"

    await col.insert_one(doc)
    return {"status": "success", "message": "Company added successfully"}


@router.post("/import")
async def import_companies(payload: dict, current_user: dict = Depends(get_current_user)):
    """Bulk import companies from a raw CSV string or a JSON array using Motor."""
    format_type = payload.get("format")
    raw_data = payload.get("data")
    col = get_async_collection("companies")

    imported_count = 0
    if format_type == "json":
        try:
            items = (json.loads(raw_data) if isinstance(raw_data, str) else raw_data) or []
            for item in items:
                try:
                    validated_item = CompanyCreateBody(**item)
                except Exception as ve:
                    raise HTTPException(status_code=400, detail=f"Validation failed for company: {ve}")
                    
                uei = validated_item.uei.strip()
                if uei and not await col.find_one({"uei": uei}):
                    doc = validated_item.model_dump()
                    doc["matchScore"] = doc.get("matchScore") or random.randint(70, 98)
                    doc["industry"] = doc.get("industry") or doc.get("primary_naics_desc") or "Other"
                    doc["contact"] = doc.get("contact") or "N/A"
                    await col.insert_one(doc)
                    imported_count += 1
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")

    elif format_type == "csv":
        try:
            raw_str = (raw_data or "").strip()
            reader = csv.DictReader(raw_str.splitlines())
            for row in reader:
                uei = (row.get("UEI") or row.get("uei", "")).strip()
                if uei and not await col.find_one({"uei": uei}):
                    is_small = (row.get("Is_Small_Business") or row.get("is_small_business", "")).strip().upper() in ("Y", "YES", "TRUE")
                    size = "Small" if is_small else "Large"
                    doc = {
                        "uei": uei,
                        "name": row.get("Legal_Business_Name") or row.get("name") or "Unnamed Company",
                        "status": row.get("Registration_Status") or row.get("status") or "Active",
                        "primary_naics": row.get("Primary_NAICS_Code") or row.get("primary_naics") or "",
                        "primary_naics_desc": row.get("Primary_NAICS_Description") or row.get("primary_naics_desc") or "",
                        "size": size,
                        "matchScore": int(row.get("matchScore") or 82),
                        "industry": row.get("Primary_NAICS_Description") or row.get("industry") or "Other",
                        "contact": row.get("Gov_Contact_Name") or row.get("contact") or "N/A",
                        "email": row.get("Gov_Contact_Email") or row.get("email") or "info@company.com"
                    }
                    await col.insert_one(doc)
                    imported_count += 1
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")

    return {"status": "success", "count": imported_count}


def update_research_task(task_key: str, progress: int, status: str, message: str, started_at: Optional[str] = None, resolved_slug: Optional[str] = None):
    extra = {}
    if resolved_slug:
        extra["resolved_slug"] = resolved_slug
    if started_at:
        extra["started_at"] = started_at
    else:
        existing = get_task_status_db(task_key)
        if existing and "started_at" in existing:
            extra["started_at"] = existing["started_at"]
        if existing and "resolved_slug" in existing and not resolved_slug:
            extra["resolved_slug"] = existing["resolved_slug"]
        if "started_at" not in extra:
            extra["started_at"] = datetime.now(timezone.utc).isoformat()
    update_task_status(task_key, "company_research", progress, status, message, None, extra)


def run_company_research_sync(company_input: str, force_rescrape: bool = False):
    import subprocess
    import sys
    import re
    
    task_key = company_input.strip()
    update_research_task(task_key, 10, "processing", "Starting company research...")
    
    cmd = [
        sys.executable,
        "main.py",
        company_input
    ]
    if force_rescrape:
        cmd.append("--force")
        
    try:
        update_research_task(task_key, 10, "processing", "Starting company research...")
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        
        resolved_slug = None
        if p.stdout:
            for line in p.stdout:
                print(f"[Research Pipe] {line.strip()}")
                if "classify_input" in line:
                    update_research_task(task_key, 20, "processing", "Classifying target input data...")
                elif "discover_website" in line:
                    update_research_task(task_key, 30, "processing", "Locating official company website...")
                elif "discover_linkedin" in line:
                    update_research_task(task_key, 40, "processing", "Finding LinkedIn profiles...")
                elif "trigger_scrapers" in line:
                    update_research_task(task_key, 50, "processing", "Triggering scraper agents in parallel...")
                elif "run_website_agent" in line:
                    update_research_task(task_key, 60, "processing", "Analyzing website content...")
                elif "run_linkedin_agent" in line:
                    update_research_task(task_key, 70, "processing", "Analyzing LinkedIn credentials...")
                elif "run_compactor" in line:
                    update_research_task(task_key, 85, "processing", "Compacting business intelligence metrics...")
                
                if "=== Pipeline complete ===" in line and "slug=" in line:
                    m = re.search(r"slug='([^']+)'", line)
                    if m:
                        resolved_slug = m.group(1)
                
        p.wait()
        if p.returncode == 0:
            update_research_task(task_key, 100, "completed", "Research completed successfully!", resolved_slug=resolved_slug)
            try:
                profiles_col = get_collection("company_profiles")
                search_slug = resolved_slug or re.sub(r"[^a-z0-9]+", "-", task_key.lower()).strip("-")
                prof = profiles_col.find_one({
                    "$or": [
                        {"company_slug": search_slug},
                        {"company_name_slug": search_slug},
                        {"company_name": {"$regex": f"^{re.escape(task_key)}$", "$options": "i"}},
                    ]
                })
                if prof:
                    comp_col = get_collection("companies")
                    upd = {
                        "is_researched": True,
                        "research_status": "completed",
                        "last_researched_at": datetime.now(timezone.utc).isoformat(),
                    }
                    if prof.get("emails") and len(prof["emails"]) > 0:
                        upd["email"] = prof["emails"][0]
                    if prof.get("phone_numbers") and len(prof["phone_numbers"]) > 0:
                        upd["phone"] = prof["phone_numbers"][0]
                    if prof.get("leadership") and len(prof["leadership"]) > 0:
                        upd["contact"] = prof["leadership"][0]

                    comp_col.update_many(
                        {"$or": [
                            {"name": {"$regex": f"^{re.escape(task_key)}$", "$options": "i"}},
                            {"uei": task_key}
                        ]},
                        {"$set": upd}
                    )
            except Exception as sync_err:
                print(f"Error syncing researched profile to companies DB: {sync_err}")
        else:
            update_research_task(task_key, 80, "failed", f"Pipeline failed with exit code {p.returncode}")
    except Exception as e:
        update_research_task(task_key, 0, "failed", f"Pipeline failed: {str(e)}")


@router.post("/research")
def trigger_company_research(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    company_input = payload.get("company")
    force_rescrape = payload.get("force", False)
    if not company_input:
        raise HTTPException(status_code=400, detail="Company name, website, or LinkedIn URL is required")
        
    task_key = company_input.strip()
    update_research_task(
        task_key,
        5,
        "processing",
        "Queuing company research task...",
        datetime.now(timezone.utc).isoformat(),
    )
    background_tasks.add_task(run_company_research_sync, company_input, force_rescrape)
    return {"status": "started", "task_key": task_key}


@router.get("/research/status")
async def get_research_status(current_user: dict = Depends(get_current_user)):
    col = get_async_collection("task_statuses")
    tasks = await col.find({"type": "company_research"}, {"_id": 0, "expireAt": 0, "updatedAt": 0}).to_list(length=1000)
    result = {}
    for t in tasks:
        task_id = t["task_id"]
        result[task_id] = {
            "progress": t["progress"],
            "status": t["status"],
            "message": t["message"],
            "started_at": t.get("started_at"),
            "resolved_slug": t.get("resolved_slug")
        }
    return result


@router.get("/profiles")
async def get_compacted_profiles(current_user: dict = Depends(get_current_user)):
    """Retrieve all compacted company profiles."""
    try:
        col = get_async_collection("company_profiles")
        profiles = await col.find({}, {"_id": 0}).to_list(length=1000)
        return profiles
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/search")
async def search_compacted_profiles(
    q: str = Query(..., description="Company name, website URL, or slug to search"),
    current_user: dict = Depends(get_current_user),
):
    """
    Search compacted profiles by company_name, website, company_slug, or company_name_slug.
    Returns the best matching profile. Used by the frontend after research completes.
    """
    try:
        col = get_async_collection("company_profiles")
        q_clean = q.strip()
        q_slug = re.sub(r"[^a-z0-9]+", "-", q_clean.lower()).strip("-")
        q_domain = re.sub(r"^https?://", "", q_clean.rstrip("/")).split("/")[0].lower()
        q_domain_slug = re.sub(r"[^a-z0-9]+", "-", q_domain).strip("-")

        profile = await col.find_one({
            "$or": [
                {"company_name": {"$regex": re.escape(q_clean), "$options": "i"}},
                {"website": {"$regex": re.escape(q_domain), "$options": "i"}},
                {"company_slug": {"$regex": re.escape(q_domain_slug), "$options": "i"}},
                {"company_name_slug": {"$regex": re.escape(q_slug), "$options": "i"}},
            ]
        }, {"_id": 0})
        return profile
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/latest")
async def get_latest_profiles(
    limit: int = 5,
    current_user: dict = Depends(get_current_user),
):
    """Returns the N most recently updated profiles."""
    try:
        col = get_async_collection("company_profiles")
        profiles = await col.find({}, {"_id": 0, "company_name": 1, "company_slug": 1, "company_name_slug": 1,
                              "website": 1, "description": 1, "last_updated": 1}).sort("last_updated", -1).limit(limit).to_list(length=limit)
        return profiles
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/detail/{slug}")
async def get_profile_detail(
    slug: str,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve full detail of a compacted company profile by slug."""
    try:
        col = get_async_collection("company_profiles")
        profile = await col.find_one({
            "$or": [
                {"company_slug": slug},
                {"company_name_slug": slug},
            ]
        }, {"_id": 0})
        if not profile:
            profile = await col.find_one(
                {"company_name": {"$regex": re.escape(slug.replace("-", " ")), "$options": "i"}},
                {"_id": 0}
            )
        if not profile:
            raise HTTPException(status_code=404, detail="Compacted profile not found")
        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/ai-mode")
async def set_ai_mode(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    mode = payload.get("mode")
    if mode not in ("auto", "ai", "rule_based"):
        raise HTTPException(status_code=400, detail="Invalid mode. Must be auto, ai, or rule_based.")
    
    try:
        col = get_async_collection("system_settings")
        await col.update_one(
            {"key": "ai_mode"},
            {"$set": {"value": mode, "updated_at": datetime.now(timezone.utc)}},
            upsert=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save AI mode settings: {e}")
        
    settings.AI_MODE = mode
    return {"status": "success", "ai_mode": mode}


@router.get("/settings/ai-mode")
async def get_ai_mode(current_user: dict = Depends(get_current_user)):
    try:
        col = get_async_collection("system_settings")
        record = await col.find_one({"key": "ai_mode"})
        if record and "value" in record:
            return {"ai_mode": record["value"]}
    except Exception:
        pass
    return {"ai_mode": settings.AI_MODE}


@router.get("/pipeline")
async def get_pipeline_items(current_user: dict = Depends(get_current_user)):
    """Retrieve items categorized for the CRM Pipeline stages."""
    companies_col = get_async_collection("companies")
    tenders_col = get_async_collection("tenders")
    reports_col = get_async_collection("reports")
    meetings_col = get_async_collection("meetings")
    leads_col = get_async_collection("leads")

    prospects = await companies_col.find({}, {"name": 1, "industry": 1, "matchScore": 1, "contact": 1, "uei": 1}).limit(10).to_list(length=10)
    contacted = await leads_col.find({"status": {"$in": ["sent", "opened", "clicked", "replied"]}}, {"email": 1, "contactName": 1, "companyName": 1, "status": 1}).limit(10).to_list(length=10)
    proposals = await reports_col.find({}, {"title": 1, "company_name": 1, "proposal_type": 1, "size": 1, "filename": 1}).limit(10).to_list(length=10)
    meetings = await meetings_col.find({}, {"title": 1, "host": 1, "startTime": 1}).limit(10).to_list(length=10)
    negotiation = await leads_col.find({"status": "replied"}, {"email": 1, "contactName": 1, "companyName": 1}).limit(10).to_list(length=10)
    won = await tenders_col.find({"has_award": True}, {"title": 1, "agency": 1, "value": 1, "id": 1}).limit(10).to_list(length=10)

    def fmt_id(doc):
        doc["id"] = str(doc.get("_id") or doc.get("id") or doc.get("uei") or doc.get("filename") or "")
        if "_id" in doc:
            del doc["_id"]
        return doc

    return {
        "leads": [fmt_id(p) for p in prospects],
        "contacted": [fmt_id(c) for c in contacted],
        "proposals": [fmt_id(p) for p in proposals],
        "meetings": [fmt_id(m) for m in meetings],
        "negotiation": [fmt_id(n) for n in negotiation],
        "won": [fmt_id(w) for w in won]
    }


DEFAULT_OWN_PROFILE = {
    "company_name": "Orbit Avanya LLP",
    "legal_name": "Orbit Avanya Limited Liability Partnership",
    "company_slug": "orbit-avanya",
    "uei": "UEI_ORBITAVANYA1",
    "cage_code": "9AB12",
    "primary_naics": "541512",
    "primary_naics_desc": "Computer Systems Design Services",
    "size": "Small",
    "website": "https://orbitavanya.com",
    "email": "contact@orbitavanya.com",
    "phone": "+1 (800) 555-0199",
    "address": "McLean, VA 22102",
    "capabilities": [
        "AI-Powered Visual Analytics Dashboards",
        "Predictive Modeling & Disaster Expenditure Forecasting",
        "AWS & Cloud Infrastructure Migration",
        "Medical & Operating Room Video Systems Integration",
        "Automated RFP Analysis & Proposal Generation",
    ],
    "products": [
        {"name": "Orbit Avanya HMS", "description": "Operating Room Video & Medical Imaging Integration"},
        {"name": "Orbit Avanya Analytics", "description": "Predictive Analytics & Executive BI Dashboards"},
        {"name": "Orbit BidForge", "description": "Automated Government RFP & Teaming Proposal Platform"},
    ],
}


@router.get("/own-profile")
async def get_own_company_profile(
    current_user: dict = Depends(get_current_user),
):
    """Retrieve Orbit Avanya's own company profile & inventory."""
    col = get_async_collection("own_company_profile")
    doc = await col.find_one({})
    if not doc:
        return DEFAULT_OWN_PROFILE
    doc["id"] = str(doc.get("_id") or "orbit-avanya")
    if "_id" in doc:
        del doc["_id"]
    return doc


@router.post("/own-profile")
async def update_own_company_profile(
    data: dict,
    current_user: dict = Depends(get_current_user),
):
    """Update or save Orbit Avanya's own company profile."""
    col = get_async_collection("own_company_profile")
    data["updatedAt"] = datetime.now(timezone.utc)
    res = await col.find_one_and_update(
        {},
        {"$set": data},
        upsert=True,
        return_document=True,
    )
    if res and "_id" in res:
        res["id"] = str(res["_id"])
        del res["_id"]
    return res or data


@router.get("/{uei}")
async def get_company_detail(
    uei: str,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve full details of a specific company by its UEI identifier."""
    col = get_async_collection("companies")
    company = await col.find_one({"uei": uei}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
