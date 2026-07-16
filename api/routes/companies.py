import csv
import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from utils.db_client import get_collection

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
                        
                        # Determinstic match score based on UEI to remain consistent
                        random.seed(uei)
                        match_score = random.randint(70, 98)
                        
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

@router.get("")
def get_companies(query: Optional[str] = None, size: Optional[str] = None, naics: Optional[str] = None, page: int = 1, limit: int = 20):
    """Query companies from MongoDB with search, filters, and pagination."""
    try:
        col = get_collection("companies")
        filter_query = {}
        
        if query:
            q = query.strip()
            filter_query["$or"] = [
                {"name": {"$regex": q, "$options": "i"}},
                {"uei": {"$regex": q, "$options": "i"}},
                {"contact": {"$regex": q, "$options": "i"}}
            ]
            
        if size and size != "All":
            filter_query["size"] = size
            
        if naics and naics != "All":
            naics_condition = {"$or": [
                {"primary_naics": {"$regex": naics.strip(), "$options": "i"}},
                {"primary_naics_desc": {"$regex": naics.strip(), "$options": "i"}}
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

@router.post("")
def add_company(company_data: dict):
    """Add a single company record manually."""
    col = get_collection("companies")
    uei = company_data.get("uei", "").strip()
    if not uei:
         raise HTTPException(status_code=400, detail="UEI is required")
         
    if col.find_one({"uei": uei}):
         raise HTTPException(status_code=400, detail="Company with this UEI already exists")
         
    company_data["matchScore"] = company_data.get("matchScore", random.randint(70, 98))
    company_data["size"] = company_data.get("size", "Small")
    company_data["industry"] = company_data.get("industry", company_data.get("primary_naics_desc", "Other"))
    company_data["contact"] = company_data.get("contact", "N/A")
    
    col.insert_one(company_data)
    return {"status": "success", "message": "Company added successfully"}

@router.post("/import")
def import_companies(payload: dict):
    """Bulk import companies from a raw CSV string or a JSON array."""
    format_type = payload.get("format")
    raw_data = payload.get("data")
    col = get_collection("companies")
    
    imported_count = 0
    if format_type == "json":
        try:
            items = (json.loads(raw_data) if isinstance(raw_data, str) else raw_data) or []
            for item in items:
                uei = item.get("uei", "").strip()
                if uei and not col.find_one({"uei": uei}):
                    col.insert_one(item)
                    imported_count += 1
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


# In-memory progress tracker for company research
# Key: company_name/url/slug
# Value: {"progress": int, "status": str, "message": str}
research_tasks = {}

def run_company_research_sync(company_input: str, force_rescrape: bool = False):
    import subprocess
    import sys
    
    task_key = company_input.strip()
    research_tasks[task_key] = {"progress": 10, "status": "processing", "message": "Starting company research..."}
    
    cmd = [
        sys.executable,
        "main.py",
        company_input
    ]
    if force_rescrape:
        cmd.append("--force")
        
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        
        if p.stdout:
            for line in p.stdout:
                print(f"[Research Pipe] {line.strip()}")
                if "classify_input" in line:
                    research_tasks[task_key].update({"progress": 20, "message": "Classifying target input data..."})
                elif "discover_website" in line:
                    research_tasks[task_key].update({"progress": 30, "message": "Locating official company website..."})
                elif "discover_linkedin" in line:
                    research_tasks[task_key].update({"progress": 40, "message": "Finding LinkedIn profiles..."})
                elif "trigger_scrapers" in line:
                    research_tasks[task_key].update({"progress": 50, "message": "Triggering scraper agents in parallel..."})
                elif "run_website_agent" in line:
                    research_tasks[task_key].update({"progress": 60, "message": "Analyzing website content..."})
                elif "run_linkedin_agent" in line:
                    research_tasks[task_key].update({"progress": 70, "message": "Analyzing LinkedIn credentials..."})
                elif "run_compactor" in line:
                    research_tasks[task_key].update({"progress": 85, "message": "Compacting business intelligence metrics..."})
                
        p.wait()
        if p.returncode == 0:
            research_tasks[task_key].update({"progress": 100, "status": "completed", "message": "Research completed successfully!"})
        else:
            research_tasks[task_key].update({"progress": 80, "status": "failed", "message": f"Pipeline failed with exit code {p.returncode}"})
    except Exception as e:
        research_tasks[task_key].update({"progress": 0, "status": "failed", "message": f"Pipeline failed: {str(e)}"})


@router.post("/research")
def trigger_company_research(payload: dict, background_tasks: BackgroundTasks):
    company_input = payload.get("company")
    force_rescrape = payload.get("force", False)
    if not company_input:
        raise HTTPException(status_code=400, detail="Company name, website, or LinkedIn URL is required")
        
    task_key = company_input.strip()
    research_tasks[task_key] = {
        "progress": 5,
        "status": "processing",
        "message": "Queuing company research task...",
        "started_at": datetime.now(timezone.utc),
    }
    background_tasks.add_task(run_company_research_sync, company_input, force_rescrape)
    return {"status": "started", "task_key": task_key}


@router.get("/research/status")
def get_research_status():
    # Auto-clean entries older than 1 hour to prevent memory leak
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    stale_keys = [
        k for k, v in research_tasks.items()
        if v.get("started_at") and v["started_at"] < cutoff
        and v.get("status") in ("completed", "failed")
    ]
    for k in stale_keys:
        del research_tasks[k]
    return research_tasks


@router.get("/profiles")
def get_compacted_profiles():
    """Retrieve all compacted company profiles."""
    try:
        col = get_collection("company_profiles")
        profiles = list(col.find({}, {"_id": 0}))
        return profiles
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/search")
def search_compacted_profiles(q: str = Query(..., description="Company name, website URL, or slug to search")):
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
def get_latest_profiles(limit: int = 5):
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
def get_profile_detail(slug: str):
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
def set_ai_mode(payload: dict):
    mode = payload.get("mode")
    if mode not in ("auto", "ai", "rule_based"):
        raise HTTPException(status_code=400, detail="Invalid mode. Must be auto, ai, or rule_based.")
    
    import re
    from config.settings import settings
    settings.AI_MODE = mode
    
    # Also write to .env to make it persistent
    try:
        env_path = Path(".env")
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if "AI_MODE=" in content:
                content = re.sub(r"AI_MODE=\w+", f"AI_MODE={mode}", content)
            else:
                content += f"\nAI_MODE={mode}"
            env_path.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"Warning: could not write AI_MODE to .env: {e}")
        
    return {"status": "success", "ai_mode": settings.AI_MODE}


@router.get("/settings/ai-mode")
def get_ai_mode():
    from config.settings import settings
    return {"ai_mode": settings.AI_MODE}


@router.get("/{uei}")
def get_company_detail(uei: str):
    """Retrieve full details of a specific company by its UEI identifier."""
    col = get_collection("companies")
    company = col.find_one({"uei": uei}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company



