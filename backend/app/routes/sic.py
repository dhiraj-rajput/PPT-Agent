"""
app/routes/sic.py
------------------
UK SIC 2007 classification codes endpoints for Companies House integration.
"""

from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from typing import Optional, List
from pydantic import BaseModel
import json
import csv
import io
from utils.db_client import get_db_session, get_sync_db_session, _mysql_available
from app.core.auth import get_current_user
from models.sql_models import SicCode as SQL_SicCode
from sqlalchemy import select, update, insert, delete, func, or_, and_

router = APIRouter(prefix="/sic", tags=["sic"])


def ensure_sic_populated():
    if not _mysql_available:
        return

    try:
        with get_sync_db_session() as db:
            cnt = db.execute(select(func.count()).select_from(SQL_SicCode)).scalar()
            if (cnt or 0) > 0:
                return

            default_sic_codes = [
                {"code": "62010", "title": "Computer programming activities", "description": "Writing, modifying, testing and supporting software."},
                {"code": "62020", "title": "Information technology consultancy activities", "description": "Planning and designing computer systems."},
                {"code": "62030", "title": "Computer facilities management activities", "description": "On-site management and operation of clients' computer systems."},
                {"code": "62090", "title": "Other information technology and computer service activities", "description": "Other IT services not elsewhere classified."},
                {"code": "63110", "title": "Data processing, hosting and related activities", "description": "Web hosting, streaming, data processing."},
                {"code": "30300", "title": "Manufacture of air and spacecraft and related machinery", "description": "Aerospace, defense, engines and components."},
                {"code": "65110", "title": "Life insurance", "description": "Life assurance and annuity policies."},
                {"code": "70229", "title": "Management consultancy activities other than financial management", "description": "Business strategy and advisory services."}
            ]

            for rec in default_sic_codes:
                db.execute(insert(SQL_SicCode).values(rec))
            db.commit()
            print(f"[SIC] Successfully bootstrapped {len(default_sic_codes)} default UK SIC codes.")
    except Exception as e:
        print(f"[SIC] Error populating default SIC collection: {e}")


@router.get("")
async def list_sic_codes(
    search: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is unavailable.")

    filter_conditions = []

    if search:
        search = search.strip()
        search_or_conditions = []
        if search.isdigit():
            search_or_conditions.append(SQL_SicCode.code.like(f"{search}%"))
        qs = f"%{search}%"
        search_or_conditions.append(SQL_SicCode.title.ilike(qs))
        search_or_conditions.append(SQL_SicCode.description.ilike(qs))
        filter_conditions.append(or_(*search_or_conditions))

    items = []
    total = 0

    try:
        async for db in get_db_session():
            stmt_count = select(func.count()).select_from(SQL_SicCode)
            stmt_select = select(SQL_SicCode)
            if filter_conditions:
                stmt_count = stmt_count.where(and_(*filter_conditions))
                stmt_select = stmt_select.where(and_(*filter_conditions))

            total = (await db.execute(stmt_count)).scalar() or 0
            skip = (page - 1) * limit
            stmt_select = stmt_select.order_by(SQL_SicCode.code.asc()).offset(skip).limit(limit)
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


class SicCodeCreateBody(BaseModel):
    code: str
    title: str
    description: Optional[str] = ""


@router.post("")
async def create_sic_code(
    body: SicCodeCreateBody,
    current_user: dict = Depends(get_current_user)
):
    code = body.code.strip()
    title = body.title.strip()
    desc = body.description.strip() if body.description else ""

    if not code or not title:
        raise HTTPException(status_code=400, detail="SIC code and title are required.")

    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_SicCode).where(SQL_SicCode.code == code)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if existing:
                    await db.execute(
                        update(SQL_SicCode)
                        .where(SQL_SicCode.code == code)
                        .values(title=title, description=desc)
                    )
                else:
                    db.add(SQL_SicCode(code=code, title=title, description=desc))
                await db.commit()
                return {"success": True, "message": f"SIC code '{code}' successfully created/updated."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=500, detail="Database is unavailable.")


@router.post("/import")
async def import_sic_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    contents = await file.read()
    filename = file.filename or ""
    imported_count = 0

    try:
        async for db in get_db_session():
            if filename.endswith(".json") or contents.strip().startswith(b"["):
                data = json.loads(contents.decode("utf-8-sig"))
                for item in data:
                    code = str(item.get("code") or item.get("Code") or "").strip()
                    title = str(item.get("title") or item.get("Title") or "").strip()
                    desc = str(item.get("description") or item.get("Description") or "").strip()
                    if code and title:
                        stmt = select(SQL_SicCode).where(SQL_SicCode.code == code)
                        existing = (await db.execute(stmt)).scalar_one_or_none()
                        if existing:
                            await db.execute(update(SQL_SicCode).where(SQL_SicCode.code == code).values(title=title, description=desc))
                        else:
                            db.add(SQL_SicCode(code=code, title=title, description=desc))
                        imported_count += 1
            else:
                stream = io.StringIO(contents.decode("utf-8-sig"))
                reader = csv.DictReader(stream)
                for row in reader:
                    code = str(row.get("Code") or row.get("code") or "").strip()
                    title = str(row.get("Title") or row.get("title") or "").strip()
                    desc = str(row.get("Description") or row.get("description") or "").strip()
                    if code and title:
                        stmt = select(SQL_SicCode).where(SQL_SicCode.code == code)
                        existing = (await db.execute(stmt)).scalar_one_or_none()
                        if existing:
                            await db.execute(update(SQL_SicCode).where(SQL_SicCode.code == code).values(title=title, description=desc))
                        else:
                            db.add(SQL_SicCode(code=code, title=title, description=desc))
                        imported_count += 1
            await db.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse SIC import file: {e}")

    return {"success": True, "message": f"Successfully imported {imported_count} SIC codes."}
