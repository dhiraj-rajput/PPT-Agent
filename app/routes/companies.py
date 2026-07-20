import csv
import json
import re
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from utils.db_client import get_collection
from app.core.auth import get_current_user, require_admin

router = APIRouter(prefix="/companies", tags=["companies"])

def import_sam_entities_csv():
    """Load sam_entities.csv into MongoDB 'companies' collection if empty."""
    try:
        companies_col = get_collection("companies")
        if companies_col.count_documents({}) == 0:
            csv_path = Path("private/sam_entities.csv")
            if csv_path.exists():
                print(f"Loading {csv_path} into MongoDB...")
                with open(csv_path, mode="r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    documents = []
                    for row in reader:
                        uei = row.get("UEI", "").strip()
                        if not uei:
                            continue
                        
                        from app.core.match_engine import compute_company_match_score
                        match_score = compute_company_match_score(
                            primary_naics=row.get("Primary_NAICS_Code", ""),
                            industry_desc=row.get("Primary_NAICS_Description", ""),
                            company_name=row.get("Legal_Business_Name", "")
                        )
                        
                        # Determine size based on Small Business flag
                        is_small = row.get("Is_Small_Business", "").strip().upper() in ("Y", "YES", "TRUE")
                        size = "Small" if is_small else "Large"
                        
                        doc = {
                            "uei": uei,
                            "name": row.get("Legal_Business_Name", "").strip(),
                            "dba_name": row.get("DBA_Name", "").strip(),
                            "cage_code": row.get("CAGE_Code", "").strip(),
                            "status": row.get("Registration_Status", "").strip(),
                            "registration_date": row.get("Registration_Date", "").strip(),
                            "expiration_date": row.get("Expiration_Date", "").strip(),
                            "last_updated": row.get("Last_Updated_Date", "").strip(),
                            "purpose": row.get("Purpose_of_Registration", "").strip(),
                            "address": f"{row.get('Phys_Address_1','')}, {row.get('Phys_City','')}, {row.get('Phys_State_Province','')}, {row.get('Phys_Country','')}".strip(", "),
                            "location": f"{row.get('Phys_City','')}, {row.get('Phys_State_Province','')}".strip(", "),
                            "city": row.get("Phys_City", "").strip(),
                            "state": row.get("Phys_State_Province", "").strip(),
                            "zip": row.get("Phys_Zip", "").strip(),
                            "country": row.get("Phys_Country", "").strip(),
                            "entity_structure": row.get("Entity_Structure", "").strip(),
                            "is_small_business": row.get("Is_Small_Business", "").strip(),
                            "is_minority_owned": row.get("Is_Minority_Owned", "").strip(),
                            "is_women_owned": row.get("Is_Women_Owned", "").strip(),
                            "is_veteran_owned": row.get("Is_Veteran_Owned", "").strip(),
                            "is_sdvosb": row.get("Is_SDVOSB", "").strip(),
                            "is_hubzone": row.get("Is_HUBZone", "").strip(),
                            "is_8a_program": row.get("Is_8a_Program", "").strip(),
                            "is_non_profit": row.get("Is_Non_Profit", "").strip(),
                            "primary_naics": row.get("Primary_NAICS_Code", "").strip(),
                            "primary_naics_desc": row.get("Primary_NAICS_Description", "").strip(),
                            "secondary_naics": row.get("Secondary_NAICS_Codes_List", "").strip(),
                            "psc_codes": row.get("PSC_Codes_List", "").strip(),
                            "contact": row.get("Gov_Contact_Name", "").strip() or row.get("EBiz_Contact_Name", "").strip() or "",
                            "email": row.get("Gov_Contact_Email", "").strip() or row.get("EBiz_Contact_Email", "").strip() or "",
                            "phone": row.get("Gov_Contact_Phone", "").strip() or row.get("EBiz_Contact_Phone", "").strip() or "",
                            "ebiz_contact": row.get("EBiz_Contact_Name", "").strip(),
                            "ebiz_email": row.get("EBiz_Contact_Email", "").strip(),
                            "ebiz_phone": row.get("EBiz_Contact_Phone", "").strip(),
                            "exclusions": row.get("Has_Active_Exclusions", "").strip(),
                            "revenue": row.get("Exec_Comp_1_Amt", "").strip() or "$2.4M",
                            "size": size,
                            "matchScore": match_score,
                            "industry": row.get("Primary_NAICS_Description", "").strip() or "Other"
                        }
                        documents.append(doc)
                    
                    if documents:
                        companies_col.insert_many(documents)
                        print(f"Loaded {len(documents)} companies from CSV successfully.")
        else:
            print("Companies collection already populated.")
    except Exception as e:
        print(f"Error loading companies CSV: {e}")

class SendCompanyEmailBody(BaseModel):
    to_email: str
    subject: str
    body: str
    proposal_filename: Optional[str] = None
    rfp_filename: Optional[str] = None


@router.get("/attachments")
def get_attachments(current_user: dict = Depends(get_current_user)):
    """List all available proposal and RFP PDF files that can be attached to emails."""
    import os
    from pathlib import Path
    
    attachments = []
    
    # 1. Look in output/pdf (proposal PDFs)
    pdf_dir = Path("output/pdf")
    if pdf_dir.exists():
        for f in pdf_dir.glob("*.pdf"):
            attachments.append({
                "filename": f.name,
                "type": "proposal",
                "label": f"Proposal: {f.name}"
            })
            
    # 2. Look in output/rfp_respond (RFP response PDFs)
    rfp_respond_dir = Path("output/rfp_respond")
    if rfp_respond_dir.exists():
        for f in rfp_respond_dir.glob("*"):
            if f.is_file() and not f.name.startswith("."):
                attachments.append({
                    "filename": f.name,
                    "type": "rfp_respond",
                    "label": f"RFP Respond: {f.name}"
                })
                
    # 3. Look in private/rfp_respond_uploads (uploaded RFP documents)
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
    import os
    from pathlib import Path
    
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
def get_companies(
    query: Optional[str] = None,
    size: Optional[str] = None,
    naics: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Query companies from MongoDB with search, filters, and pagination."""
    try:
        col = get_collection("companies")
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
            # If a query $or is already set, wrap both in $and to avoid collision
            if "$or" in filter_query:
                filter_query["$and"] = [
                    {"$or": filter_query.pop("$or")},
                    naics_condition,
                ]
            else:
                filter_query.update(naics_condition)

        total = col.count_documents(filter_query)
        skip = (page - 1) * limit
        results = list(col.find(filter_query, {"_id": 0}).skip(skip).limit(limit))

        # Get list of unique NAICS descriptions for dropdown filters in the frontend
        naics_list = col.distinct("primary_naics_desc")
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

# ---------------------------------------------------------------------------
# Pydantic model for company creation — prevents mass-assignment
# ---------------------------------------------------------------------------

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
def add_company(
    company_data: CompanyCreateBody,
    current_user: dict = Depends(get_current_user),
):
    """Add a single company record manually."""
    col = get_collection("companies")
    uei = company_data.uei.strip()
    if not uei:
        raise HTTPException(status_code=400, detail="UEI is required")

    if col.find_one({"uei": uei}):
        raise HTTPException(status_code=400, detail="Company with this UEI already exists")

    doc = company_data.model_dump()
    doc["matchScore"] = doc.get("matchScore") or random.randint(70, 98)
    doc["industry"] = doc.get("industry") or doc.get("primary_naics_desc") or "Other"
    doc["contact"] = doc.get("contact") or "N/A"

    col.insert_one(doc)
    return {"status": "success", "message": "Company added successfully"}

@router.post("/import")
def import_companies(payload: dict, current_user: dict = Depends(get_current_user)):
    """Bulk import companies from a raw CSV string or a JSON array."""
    format_type = payload.get("format")
    raw_data = payload.get("data")
    col = get_collection("companies")

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
                if uei and not col.find_one({"uei": uei}):
                    doc = validated_item.model_dump()
                    doc["matchScore"] = doc.get("matchScore") or random.randint(70, 98)
                    doc["industry"] = doc.get("industry") or doc.get("primary_naics_desc") or "Other"
                    doc["contact"] = doc.get("contact") or "N/A"
                    col.insert_one(doc)
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
                if uei and not col.find_one({"uei": uei}):
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
                    col.insert_one(doc)
                    imported_count += 1
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")

    return {"status": "success", "count": imported_count}


# MongoDB-backed progress tracker for company research
from utils.db_client import update_task_status, get_task_status_db, get_collection

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
        from utils.helpers import SUBPROCESS_SEMAPHORE
        update_research_task(task_key, 8, "processing", "Waiting in queue for resources...")
        with SUBPROCESS_SEMAPHORE:
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
def get_research_status(current_user: dict = Depends(get_current_user)):
    col = get_collection("task_statuses")
    tasks = list(col.find({"type": "company_research"}, {"_id": 0, "expireAt": 0, "updatedAt": 0}))
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
def get_compacted_profiles(current_user: dict = Depends(get_current_user)):
    """Retrieve all compacted company profiles."""
    try:
        col = get_collection("company_profiles")
        profiles = list(col.find({}, {"_id": 0}))
        return profiles
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/search")
def search_compacted_profiles(
    q: str = Query(..., description="Company name, website URL, or slug to search"),
    current_user: dict = Depends(get_current_user),
):
    """
    Search compacted profiles by company_name, website, company_slug, or company_name_slug.
    Returns the best matching profile. Used by the frontend after research completes.
    """
    try:
        col = get_collection("company_profiles")
        q_clean = q.strip()
        # Derive slug variants from the query
        import re
        q_slug = re.sub(r"[^a-z0-9]+", "-", q_clean.lower()).strip("-")
        # Remove common URL schemes so "https://infosys.com" -> "infosys.com"
        q_domain = re.sub(r"^https?://", "", q_clean.rstrip("/")).split("/")[0].lower()
        q_domain_slug = re.sub(r"[^a-z0-9]+", "-", q_domain).strip("-")

        profile = col.find_one({
            "$or": [
                {"company_name": {"$regex": re.escape(q_clean), "$options": "i"}},
                {"website": {"$regex": re.escape(q_domain), "$options": "i"}},
                {"company_slug": {"$regex": re.escape(q_domain_slug), "$options": "i"}},
                {"company_name_slug": {"$regex": re.escape(q_slug), "$options": "i"}},
            ]
        }, {"_id": 0})
        # Return profile directly (None if not found) instead of raising 404 to prevent console errors
        return profile
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/latest")
def get_latest_profiles(
    limit: int = 5,
    current_user: dict = Depends(get_current_user),
):
    """Returns the N most recently updated profiles. Used to auto-select after research."""
    try:
        col = get_collection("company_profiles")
        profiles = list(
            col.find({}, {"_id": 0, "company_name": 1, "company_slug": 1, "company_name_slug": 1,
                          "website": 1, "description": 1, "last_updated": 1})
            .sort("last_updated", -1)
            .limit(limit)
        )
        return profiles
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/detail/{slug}")
def get_profile_detail(
    slug: str,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve full detail of a compacted company profile by slug."""
    try:
        col = get_collection("company_profiles")
        profile = col.find_one({
            "$or": [
                {"company_slug": slug},
                {"company_name_slug": slug},
            ]
        }, {"_id": 0})
        if not profile:
            # Fallback: fuzzy match on company_name
            import re
            profile = col.find_one(
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
def set_ai_mode(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    mode = payload.get("mode")
    if mode not in ("auto", "ai", "rule_based"):
        raise HTTPException(status_code=400, detail="Invalid mode. Must be auto, ai, or rule_based.")
    
    # Store setting in MongoDB instead of writing .env file to support multi-worker setups
    try:
        col = get_collection("system_settings")
        col.update_one(
            {"key": "ai_mode"},
            {"$set": {"value": mode, "updated_at": datetime.now(timezone.utc)}},
            upsert=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save AI mode settings: {e}")
        
    from config.settings import settings
    settings.AI_MODE = mode
    return {"status": "success", "ai_mode": mode}


@router.get("/settings/ai-mode")
def get_ai_mode(current_user: dict = Depends(get_current_user)):
    try:
        col = get_collection("system_settings")
        record = col.find_one({"key": "ai_mode"})
        if record and "value" in record:
            return {"ai_mode": record["value"]}
    except Exception:
        pass
    from config.settings import settings
    return {"ai_mode": settings.AI_MODE}


@router.get("/pipeline")
def get_pipeline_items(current_user: dict = Depends(get_current_user)):
    """Retrieve items categorized for the CRM Pipeline stages."""
    companies_col = get_collection("companies")
    tenders_col = get_collection("tenders")
    reports_col = get_collection("reports")
    meetings_col = get_collection("meetings")
    leads_col = get_collection("leads")

    # 1. Prospects
    prospects = list(companies_col.find({}, {"name": 1, "industry": 1, "matchScore": 1, "contact": 1, "uei": 1}).limit(10))
    
    # 2. Contacted
    contacted = list(leads_col.find({"status": {"$in": ["sent", "opened", "clicked", "replied"]}}, {"email": 1, "contactName": 1, "companyName": 1, "status": 1}).limit(10))
    
    # 3. Proposals Sent
    proposals = list(reports_col.find({}, {"title": 1, "company_name": 1, "proposal_type": 1, "size": 1, "filename": 1}).limit(10))
    
    # 4. Meetings Booked
    meetings = list(meetings_col.find({}, {"title": 1, "host": 1, "startTime": 1}).limit(10))
    
    # 5. In Negotiation
    negotiation = list(leads_col.find({"status": "replied"}, {"email": 1, "contactName": 1, "companyName": 1}).limit(10))
    
    # 6. Won
    won = list(tenders_col.find({"has_award": True}, {"title": 1, "agency": 1, "value": 1, "id": 1}).limit(10))

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


@router.get("/{uei}")
def get_company_detail(
    uei: str,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve full details of a specific company by its UEI identifier."""
    col = get_collection("companies")
    company = col.find_one({"uei": uei}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company



