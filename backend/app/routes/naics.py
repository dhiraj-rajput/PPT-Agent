"""
app/routes/naics.py
--------------------
NAICS industry classification codes endpoints — using MySQL.
"""

import csv
import io
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from models.sql_models import NaicsCode as SQL_NaicsCode
from pydantic import BaseModel
from sqlalchemy import and_, func, insert, or_, select, update
from utils.db_client import (
    _mysql_available,
    get_collection,
    get_db_session,
    get_sync_db_session,
)

from app.core.auth import get_current_user

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

router = APIRouter(prefix="/naics", tags=["naics"])


def ensure_naics_populated():
    if not _mysql_available:
        return

    try:
        with get_sync_db_session() as db:
            cnt = db.execute(select(func.count()).select_from(SQL_NaicsCode)).scalar()
            if (cnt or 0) > 0:
                return


            csv_path = _BACKEND_ROOT / "private" / "2022_NAICS_Descriptions.csv"
            if not csv_path.exists():
                print(f"[NAICS] CSV file not found at: {csv_path}. Skipping population.")
                return

            print("[NAICS] Populating naics_codes collection from CSV...")
            records = []
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
                # Chunk insert
                CHUNK = 1000
                for i in range(0, len(records), CHUNK):
                    db.execute(insert(SQL_NaicsCode).values(records[i:i+CHUNK]))
                    db.commit()
                print(f"[NAICS] Successfully imported {len(records)} NAICS codes.")
    except Exception as e:
        print(f"[NAICS] Error populating NAICS collection: {e}")


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
async def list_naics_codes(
    search: str | None = None,
    sector: str | None = None,
    match_company_description: bool | None = False,
    custom_description: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is unavailable.")

    filter_conditions = []

    if sector:
        if "-" in sector:
            parts = sector.split("-")
            try:
                start = int(parts[0])
                end = int(parts[1])
                # Sector ranges like 31-33
                prefixes = [f"{x}%" for x in range(start, end + 1)]
                filter_conditions.append(or_(*[SQL_NaicsCode.code.like(pref) for pref in prefixes]))
            except ValueError:
                filter_conditions.append(SQL_NaicsCode.code.like(f"{sector}%"))
        else:
            filter_conditions.append(SQL_NaicsCode.code.like(f"{sector}%"))

    if search:
        search = search.strip()
        search_or_conditions = []
        if search.isdigit():
            search_or_conditions.append(SQL_NaicsCode.code.like(f"{search}%"))
        
        qs = f"%{search}%"
        search_or_conditions.append(SQL_NaicsCode.title.ilike(qs))
        search_or_conditions.append(SQL_NaicsCode.description.ilike(qs))
        
        for kw in extract_keywords(search):
            search_or_conditions.append(SQL_NaicsCode.title.ilike(f"%{kw}%"))
            search_or_conditions.append(SQL_NaicsCode.description.ilike(f"%{kw}%"))
        
        filter_conditions.append(or_(*search_or_conditions))

    desc_to_match = ""
    if not search and custom_description:
        desc_to_match = custom_description.strip()
    elif not search and match_company_description:
        own_col = get_collection("own_company_profile")
        profile = own_col.find_one({}, {"_id": 0})
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
                kw_conditions.append(SQL_NaicsCode.title.ilike(f"%{kw}%"))
                kw_conditions.append(SQL_NaicsCode.description.ilike(f"%{kw}%"))
            if kw_conditions:
                filter_conditions.append(or_(*kw_conditions))

    items = []
    total = 0

    try:
        async for db in get_db_session():
            stmt_count = select(func.count()).select_from(SQL_NaicsCode)
            stmt_select = select(SQL_NaicsCode)
            if filter_conditions:
                stmt_count = stmt_count.where(and_(*filter_conditions))
                stmt_select = stmt_select.where(and_(*filter_conditions))

            total = (await db.execute(stmt_count)).scalar() or 0

            skip = (page - 1) * limit
            stmt_select = stmt_select.order_by(SQL_NaicsCode.code.asc()).offset(skip).limit(limit)
            res = await db.execute(stmt_select)
            for doc in res.scalars().all():
                items.append({
                    "code": doc.code,
                    "title": doc.title,
                    "description": doc.description or ""
                })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": items
    }


class NaicsCodeCreateBody(BaseModel):
    code: str
    title: str
    description: str | None = ""


@router.post("")
async def create_naics_code(
    body: NaicsCodeCreateBody,
    current_user: dict = Depends(get_current_user)
):
    code = body.code.strip()
    title = body.title.strip()
    desc = body.description.strip() if body.description else ""

    if not code or not title:
        raise HTTPException(status_code=400, detail="NAICS code and title are required.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_NaicsCode).where(SQL_NaicsCode.code == code)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if existing:
                    await db.execute(
                        update(SQL_NaicsCode)
                        .where(SQL_NaicsCode.code == code)
                        .values(title=title, description=desc)
                    )
                else:
                    db.add(SQL_NaicsCode(code=code, title=title, description=desc))
                await db.commit()
                return {
                    "success": True,
                    "message": f"NAICS code '{code}' successfully created/updated."
                }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=500, detail="Database is unavailable.")


@router.post("/import")
async def import_naics_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    MAX_NAICS_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    filename = file.filename or ""

    contents = await file.read()
    if len(contents) > MAX_NAICS_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum allowed size is 5MB.")
    
    imported_count = 0
    
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="Database is unavailable.")

    try:
        async for db in get_db_session():
            # Check if JSON
            if filename.endswith(".json") or contents.strip().startswith(b"["):
                data = json.loads(contents.decode("utf-8-sig"))
                if not isinstance(data, list):
                    raise HTTPException(status_code=400, detail="JSON file must contain an array of NAICS code objects.")
                
                for item in data:
                    code = str(item.get("code") or item.get("Code") or "").strip()
                    title = str(item.get("title") or item.get("Title") or "").strip()
                    desc = str(item.get("description") or item.get("Description") or "").strip()
                    if code and title:
                        stmt = select(SQL_NaicsCode).where(SQL_NaicsCode.code == code)
                        existing = (await db.execute(stmt)).scalar_one_or_none()
                        if existing:
                            await db.execute(
                                update(SQL_NaicsCode)
                                .where(SQL_NaicsCode.code == code)
                                .values(title=title, description=desc)
                            )
                        else:
                            db.add(SQL_NaicsCode(code=code, title=title, description=desc))
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
                        stmt = select(SQL_NaicsCode).where(SQL_NaicsCode.code == code)
                        existing = (await db.execute(stmt)).scalar_one_or_none()
                        if existing:
                            await db.execute(
                                update(SQL_NaicsCode)
                                .where(SQL_NaicsCode.code == code)
                                .values(title=title, description=desc)
                            )
                        else:
                            db.add(SQL_NaicsCode(code=code, title=title, description=desc))
                        imported_count += 1
            await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse import file: {e}")
        
    return {
        "success": True,
        "message": f"Successfully imported/updated {imported_count} NAICS codes."
    }
