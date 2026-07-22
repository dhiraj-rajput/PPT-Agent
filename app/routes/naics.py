from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from typing import Optional, List
from pydantic import BaseModel
import json
import csv
import os
from utils.db_client import get_collection
from app.core.auth import get_current_user
from pymongo import TEXT

router = APIRouter(prefix="/naics", tags=["naics"])

# Auto-import NAICS codes from private CSV on first request or application import
def ensure_naics_populated():
    coll = get_collection("naics_codes")
    if coll.count_documents({}) > 0:
        return

    csv_path = "private/2022_NAICS_Descriptions.csv"
    if not os.path.exists(csv_path):
        print(f"[NAICS] CSV file not found at: {csv_path}. Skipping population.")
        return

    print("[NAICS] Populating naics_codes collection from CSV...")
    records = []
    try:
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = (row.get("Code") or "").strip()
                title = (row.get("Title") or "").strip()
                desc = (row.get("Description") or "").strip()
                if code:
                    records.append({
                        "code": code,
                        "title": title,
                        "description": desc
                    })
        
        if records:
            coll.insert_many(records)
            coll.create_index([("code", 1)], unique=True)
            coll.create_index([("title", TEXT), ("description", TEXT)])
            print(f"[NAICS] Successfully imported {len(records)} NAICS codes.")
    except Exception as e:
        print(f"[NAICS] Error populating NAICS collection: {e}")

# Call populate function on module load
ensure_naics_populated()

import re

def extract_keywords(description: str) -> list[str]:
    if not description:
        return []
    words = re.findall(r"\b[a-zA-Z]{3,}\b", description.lower())
    stop_words = {
        "our", "company", "specializes", "in", "and", "the", "for", "with",
        "services", "products", "related", "work", "we", "are", "provides",
        "providing", "based", "solutions", "business", "clients", "customers",
        "llp", "tech", "technology", "development", "systems", "design", "management",
        "developing", "develop", "developer", "developers"
    }
    keywords = [w for w in words if w not in stop_words]
    return list(dict.fromkeys(keywords))

@router.get("")
def list_naics_codes(
    search: Optional[str] = None,
    sector: Optional[str] = None,
    match_company_description: Optional[bool] = False,
    custom_description: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    coll = get_collection("naics_codes")
    query = {}
    and_conditions = []

    if sector:
        # NAICS sectors can be 2-digit ranges (e.g. 31-33) or single 2-digit prefixes
        if "-" in sector:
            parts = sector.split("-")
            try:
                start = int(parts[0])
                end = int(parts[1])
                # Generate regex matching starting with any digit in the range
                prefixes = [str(x) for x in range(start, end + 1)]
                regex_pattern = "^(" + "|".join(prefixes) + ")"
                and_conditions.append({"code": {"$regex": regex_pattern}})
            except ValueError:
                and_conditions.append({"code": {"$regex": f"^{sector}"}})
        else:
            and_conditions.append({"code": {"$regex": f"^{sector}"}})

    if search:
        search = search.strip()
        # If search matches a numeric NAICS prefix/code
        if search.isdigit():
            and_conditions.append({"code": {"$regex": f"^{search}"}})
        else:
            # Use regex on title/description
            and_conditions.append({
                "$or": [
                    {"title": {"$regex": search, "$options": "i"}},
                    {"description": {"$regex": search, "$options": "i"}}
                ]
            })

    # Check description filter
    desc_to_match = ""
    if custom_description:
        desc_to_match = custom_description.strip()
    elif match_company_description:
        own_col = get_collection("own_company_profile")
        profile = own_col.find_one({}, {"_id": 0})
        # Fallback to default description if own company profile does not exist
        if profile:
            desc_to_match = profile.get("description", "")
        else:
            from app.routes.companies import DEFAULT_OWN_COMPANY
            desc_to_match = DEFAULT_OWN_COMPANY.get("description", "")

    if desc_to_match:
        keywords = extract_keywords(desc_to_match)
        if keywords:
            kw_conditions = []
            for kw in keywords:
                kw_conditions.append({"title": {"$regex": kw, "$options": "i"}})
                kw_conditions.append({"description": {"$regex": kw, "$options": "i"}})
            if kw_conditions:
                and_conditions.append({"$or": kw_conditions})

    if and_conditions:
        query["$and"] = and_conditions

    total = coll.count_documents(query)
    skip = (page - 1) * limit
    
    # Sort by code ascending
    cursor = coll.find(query).sort("code", 1).skip(skip).limit(limit)
    items = []
    for doc in cursor:
        items.append({
            "code": doc["code"],
            "title": doc["title"],
            "description": doc.get("description", "")
        })

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": items
    }


class NaicsCodeCreateBody(BaseModel):
    code: str
    title: str
    description: Optional[str] = ""

@router.post("")
def create_naics_code(
    body: NaicsCodeCreateBody,
    current_user: dict = Depends(get_current_user)
):
    coll = get_collection("naics_codes")
    code = body.code.strip()
    title = body.title.strip()
    desc = body.description.strip() if body.description else ""

    from fastapi import HTTPException
    if not code or not title:
        raise HTTPException(400, "NAICS code and title are required.")

    # Upsert the NAICS code
    coll.update_one(
        {"code": code},
        {"$set": {
            "code": code,
            "title": title,
            "description": desc
        }},
        upsert=True
    )
    
    return {
        "success": True,
        "message": f"NAICS code '{code}' successfully created/updated."
    }

@router.post("/import")
async def import_naics_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    coll = get_collection("naics_codes")
    contents = await file.read()
    filename = file.filename or ""
    
    imported_count = 0
    from fastapi import HTTPException
    import io
    
    try:
        # Check if JSON
        if filename.endswith(".json") or contents.strip().startswith(b"["):
            data = json.loads(contents.decode("utf-8-sig"))
            if not isinstance(data, list):
                raise HTTPException(400, "JSON file must contain an array of NAICS code objects.")
            
            for item in data:
                code = str(item.get("code") or item.get("Code") or "").strip()
                title = str(item.get("title") or item.get("Title") or "").strip()
                desc = str(item.get("description") or item.get("Description") or "").strip()
                if code and title:
                    coll.update_one(
                        {"code": code},
                        {"$set": {"code": code, "title": title, "description": desc}},
                        upsert=True
                    )
                    imported_count += 1
                    
        # Otherwise assume CSV
        else:
            stream = io.StringIO(contents.decode("utf-8-sig"))
            reader = csv.DictReader(stream)
            for row in reader:
                code = str(row.get("Code") or row.get("code") or "").strip()
                title = str(row.get("Title") or row.get("title") or "").strip()
                desc = str(row.get("Description") or row.get("description") or "").strip()
                if code and title:
                    coll.update_one(
                        {"code": code},
                        {"$set": {"code": code, "title": title, "description": desc}},
                        upsert=True
                    )
                    imported_count += 1
                    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Failed to parse import file: {e}")
        
    return {
        "success": True,
        "message": f"Successfully imported/updated {imported_count} NAICS codes."
    }
