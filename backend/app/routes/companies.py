"""
app/routes/companies.py
-------------------------
Company intelligence, search, filtering, and research management endpoints.
Uses MySQL for relational companies and task status databases, and MongoDB for company profiles.
"""

from __future__ import annotations

import asyncio
import codecs
import csv
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, UploadFile, File, Form
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import (
    get_async_collection,
    get_collection,
    update_task_status,
    get_task_status_db,
    get_db_session,
    get_sync_db_session,
    _mysql_available,
)
from models.sql_models import (
    Company as SQL_Company,
    Lead as SQL_Lead,
    Report as SQL_Report,
    Meeting as SQL_Meeting,
    Tender as SQL_Tender,
    NaicsCode as SQL_NaicsCode,
    TaskStatus as SQL_TaskStatus,
    SystemSettings as SQL_SystemSettings,
)
from sqlalchemy import select, insert, update, delete, func, or_, and_
from config.settings import settings
from app.core.match_engine import compute_company_match_score

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/companies", tags=["companies"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_OWN_COMPANY = {
    "name": "OrbitAvanya Tech LLP",
    "uei": "ORBIT1234567",
    "cage_code": "8A9B0",
    "primary_naics": "541512",
    "primary_naics_desc": "Computer Systems Design Services",
    "naics_codes": ["541511", "541512", "541519", "541330", "541611"],
    "city": "Dallas",
    "state": "TX",
    "country": "USA",
    "contact": "Prasanna Dhamal",
    "contact_role": "Managing Director",
    "email": settings.SMTP_FROM or settings.SMTP_USER or "info@winbid.avanyaedge.com",
    "phone": "+1-214-555-0199",
    "size": "Small",
    "status": "Active",
    "certifications": ["SBA 8(a) Certified", "WOSB", "HUBZone", "ISO 27001"],
    "past_performance_count": 12,
    "description": "Our company specializes in IT consulting, software development, cloud systems migration, and cyber security services.",
    "sub_companies": [],
    "last_updated": datetime.now(timezone.utc).isoformat()
}


def import_sam_entities_csv():
    """Initialise / populate SAM entities in companies table from CSV if empty."""
    if not _mysql_available:
        return

    try:
        with get_sync_db_session() as db:
            stmt = select(func.count()).select_from(SQL_Company)
            cnt = db.execute(stmt).scalar()
            if (cnt or 0) > 0:
                return


            csv_path = PROJECT_ROOT / "private" / "sam_entities.csv"
            if not csv_path.exists():
                csv_path = PROJECT_ROOT / "documents" / "sam_entities.csv"
            if not csv_path.exists():
                return

            logger.info("Seeding initial company database from sam_entities.csv...")

            from app.core.company_catalog import load_services_catalog
            load_services_catalog()  # warms the in-process cache

            MAX_SEED_ROWS = 5000

            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                batch = []
                row_count = 0
                for row in reader:
                    if row_count >= MAX_SEED_ROWS:
                        break
                    uei = (row.get("UEI") or row.get("uei", "")).strip()
                    if uei:
                        is_small = (row.get("Is_Small_Business") or row.get("is_small_business", "")).strip().upper() in ("Y", "YES", "TRUE")
                        primary_naics = row.get("Primary_NAICS_Code") or row.get("primary_naics") or ""
                        primary_naics_desc = row.get("Primary_NAICS_Description") or row.get("primary_naics_desc") or ""
                        name = row.get("Legal_Business_Name") or row.get("name") or "Unnamed Company"
                        
                        batch.append({
                            "uei": uei,
                            "name": name,
                            "status": row.get("Registration_Status") or row.get("status") or "Active",
                            "naics_code": primary_naics,
                            "industry": primary_naics_desc or "Other",
                            "size": "Small" if is_small else "Large",
                            "is_small_business": "Y" if is_small else "N",
                            "match_score": compute_company_match_score(
                                primary_naics=primary_naics,
                                industry_desc=primary_naics_desc or "Other",
                                company_name=name
                            ),
                            "contact": row.get("Gov_Contact_Name") or "N/A",
                            "email": row.get("Gov_Contact_Email") or "info@company.com"
                        })
                        row_count += 1
                    if len(batch) >= 500:
                        db.execute(insert(SQL_Company).values(batch))
                        db.commit()
                        batch = []
                if batch:
                    db.execute(insert(SQL_Company).values(batch))
                    db.commit()
            logger.info(f"SAM entities seeded successfully ({row_count} records).")
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
    
    pdf_dir = PROJECT_ROOT / "output" / "pdf"
    if pdf_dir.exists():
        for f in pdf_dir.glob("*.pdf"):
            attachments.append({
                "filename": f.name,
                "type": "proposal",
                "label": f"Proposal: {f.name}"
            })
            
    rfp_respond_dir = PROJECT_ROOT / "output" / "rfp_respond"
    if rfp_respond_dir.exists():
        for f in rfp_respond_dir.glob("*"):
            if f.is_file() and not f.name.startswith("."):
                attachments.append({
                    "filename": f.name,
                    "type": "rfp_respond",
                    "label": f"RFP Respond: {f.name}"
                })
                
    uploads_dir = PROJECT_ROOT / "private" / "rfp_respond_uploads"
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
    from pathlib import Path
    def _safe_attachment_path(base_dir: Path, fname: str) -> Path:
        resolved = (base_dir / fname).resolve()
        if not str(resolved).startswith(str(base_dir.resolve())):
            raise ValueError(f"Path traversal attempt detected: {fname!r}")
        return resolved

    def locate_and_add_file(filename: str):
        dirs = [
            PROJECT_ROOT / "output" / "pdf",
            PROJECT_ROOT / "output" / "rfp_respond",
            PROJECT_ROOT / "private" / "rfp_respond_uploads"
        ]
        for d in dirs:
            if d.exists():
                try:
                    p = _safe_attachment_path(d, filename)
                except ValueError:
                    continue
                if p.exists() and p.is_file():
                    attachments_list.append({
                        "path": str(p),
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


def _iso(dt: Any) -> Optional[str]:
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


def _format_company(c: SQL_Company) -> dict:
    if not c:
        return {}
    return {
        "id": str(c.id),
        "uei": c.uei or "",
        "name": c.name or "",
        "website": c.website or "",
        "industry": c.industry or "",
        "size": c.size or "",
        "location": c.location or "",
        "description": c.description or "",
        "naics_code": c.naics_code or "",
        "matchScore": c.match_score or 0,
        "contact": c.contact or "N/A",
        "email": c.email or "",
        "phone": c.phone or "",
        "cage_code": c.cage_code or "",
        "status": c.status or "Active",
        "address": c.address or "",
        "is_small_business": c.is_small_business or "N",
        "is_minority_owned": c.is_minority_owned or "N",
        "is_women_owned": c.is_women_owned or "N",
        "is_veteran_owned": c.is_veteran_owned or "N",
        "secondary_naics": c.secondary_naics or "",
        "is_researched": bool(c.is_researched),
        "research_status": c.research_status or "pending",
        "last_researched_at": _iso(c.last_researched_at),
        "createdAt": _iso(c.created_at),
        "updatedAt": _iso(c.updated_at)
    }


@router.get("")
async def get_companies(
    query: Optional[str] = None,
    size: Optional[str] = None,
    naics: Optional[str] = None,
    researched: Optional[str] = None,
    match_company_description: Optional[bool] = False,
    custom_description: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Query companies from MySQL with search, filters, and pagination."""
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is not connected.")

    try:
        filter_conditions = []

        # Unified search conditions
        search_conditions = []
        if query and query.strip():
            q = query.strip()
            search_conditions.extend([
                SQL_Company.name.ilike(f"%{q}%"),
                SQL_Company.uei.ilike(f"%{q}%"),
                SQL_Company.contact.ilike(f"%{q}%"),
                SQL_Company.email.ilike(f"%{q}%"),
            ])

        if size and size != "All":
            filter_conditions.append(SQL_Company.size == size)

        if naics and naics != "All":
            naics_clean = naics.strip()
            filter_conditions.append(or_(
                SQL_Company.naics_code.ilike(f"%{naics_clean}%"),
                SQL_Company.industry.ilike(f"%{naics_clean}%")
            ))

        # Description-keyword matching
        desc_to_match = ""
        if query and query.strip():
            desc_to_match = query.strip()
        elif custom_description:
            desc_to_match = custom_description.strip()
        elif match_company_description:
            own_col = get_async_collection("own_company_profile")
            profile = (await own_col.find_one({}, {"_id": 0})) or DEFAULT_OWN_COMPANY
            desc_to_match = profile.get("description", "")

        if desc_to_match:
            keywords = extract_keywords(desc_to_match)
            if keywords:
                # Get db session to find naics codes
                matched_naics_codes = []
                async for db in get_db_session():
                    stmt_naics = select(SQL_NaicsCode.code).where(or_(
                        *[SQL_NaicsCode.title.ilike(f"%{kw}%") for kw in keywords] + 
                         [SQL_NaicsCode.description.ilike(f"%{kw}%") for kw in keywords]
                    ))
                    res_naics = await db.execute(stmt_naics)
                    matched_naics_codes = res_naics.scalars().all()

                if matched_naics_codes:
                    search_conditions.append(SQL_Company.naics_code.in_(matched_naics_codes))
                    for code in matched_naics_codes:
                        search_conditions.append(SQL_Company.secondary_naics.ilike(f"%{code}%"))

                for kw in keywords:
                    search_conditions.append(SQL_Company.name.ilike(f"%{kw}%"))
                    search_conditions.append(SQL_Company.industry.ilike(f"%{kw}%"))

        if search_conditions:
            filter_conditions.append(or_(*search_conditions))

        # Build main statement
        stmt = select(SQL_Company)
        if filter_conditions:
            stmt = stmt.where(and_(*filter_conditions))
        stmt = stmt.order_by(SQL_Company.created_at.desc())

        # Load profiles check (MongoDB) — ultra-fast single query
        profiles_col = get_async_collection("company_profiles")
        prof_map = {}
        profile_names = set()
        profile_slugs = set()
        try:
            all_profiles = await profiles_col.find({}, projection={"company_name": 1, "company_slug": 1, "_id": 1}).to_list(length=1000)
            for p in all_profiles:
                p_name = (p.get("company_name") or "").strip().lower()
                p_slug = (p.get("company_slug") or "").strip().lower()
                if p_name:
                    profile_names.add(p_name)
                    prof_map[p_name] = p
                if p_slug:
                    profile_slugs.add(p_slug)
                    prof_map[p_slug] = p
        except Exception as e:
            logger.warning(f"Failed to load MongoDB company_profiles: {e}")

        def _slugify(name: str) -> str:
            return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")

        def _is_researched(c: SQL_Company) -> bool:
            if getattr(c, "is_researched", False) or getattr(c, "research_status", "") == "completed":
                return True
            name = (c.name or "").strip().lower()
            return name in profile_names or _slugify(str(c.name or "")) in profile_slugs

        # Get active tasks
        active_tasks = {}
        async for db in get_db_session():
            task_stmt = select(SQL_TaskStatus).where(SQL_TaskStatus.task_type == "company_research")
            res_tasks = await db.execute(task_stmt)
            for t in res_tasks.scalars().all():
                active_tasks[str(t.task_id).lower()] = t.status

        researched_norm = (researched or "").strip().lower()
        wants_researched_filter = researched_norm in ("true", "false", "researched", "not_researched")

        # Fetch records
        results = []
        total = 0
        async for db in get_db_session():
            if wants_researched_filter:
                want_true = researched_norm in ("true", "researched")
                if want_true and profile_names:
                    # Filter efficiently using SQL + memory
                    names_list = list(profile_names)
                    stmt_res = stmt.where(or_(SQL_Company.is_researched == True, func.lower(SQL_Company.name).in_(names_list)))
                    res = await db.execute(stmt_res)
                    all_matching = res.scalars().all()
                    filtered = [c for c in all_matching if _is_researched(c) == want_true]
                else:
                    res = await db.execute(stmt)
                    all_matching = res.scalars().all()
                    filtered = [c for c in all_matching if _is_researched(c) == want_true]

                total = len(filtered)
                skip = (page - 1) * limit
                results = filtered[skip:skip + limit]
            else:
                count_stmt = select(func.count()).select_from(SQL_Company)
                if filter_conditions:
                    count_stmt = count_stmt.where(and_(*filter_conditions))
                total = (await db.execute(count_stmt)).scalar() or 0

                skip = (page - 1) * limit
                res = await db.execute(stmt.offset(skip).limit(limit))
                results = res.scalars().all()

        # Format results
        formatted_results = []
        for c in results:
            c_formatted = _format_company(c)
            c_name_lower = (c.name or "").lower().strip()
            c_slug = _slugify(str(c.name or ""))

            profile = prof_map.get(c_name_lower) or prof_map.get(c_slug)
            is_researched_flag = _is_researched(c) or bool(profile)

            if profile:
                if (not c_formatted.get("email") or not c_formatted["email"].strip()) and profile.get("emails"):
                    c_formatted["email"] = profile["emails"][0]
                if (not c_formatted.get("phone") or not c_formatted["phone"].strip()) and profile.get("phone_numbers"):
                    c_formatted["phone"] = profile["phone_numbers"][0]
                if (not c_formatted.get("contact") or c_formatted.get("contact") == "N/A") and profile.get("leadership"):
                    c_formatted["contact"] = profile["leadership"][0]

            c_formatted["hasResearchedProfile"] = is_researched_flag
            c_formatted["is_researched"] = is_researched_flag
            c_formatted["isResearching"] = active_tasks.get((c.name or "").lower()) == "processing"
            formatted_results.append(c_formatted)

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "companies": formatted_results,
            "naics_codes": []
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
    """Add a single company record manually to MySQL."""
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is unavailable.")

    uei = company_data.uei.strip()
    if not uei:
        raise HTTPException(status_code=400, detail="UEI is required")

    try:
        async for db in get_db_session():
            stmt = select(SQL_Company).where(SQL_Company.uei == uei)
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if existing:
                raise HTTPException(status_code=400, detail="Company with this UEI already exists")

            match_score = company_data.matchScore or compute_company_match_score(
                primary_naics=company_data.primary_naics or "",
                industry_desc=company_data.industry or company_data.primary_naics_desc or "Other",
                company_name=company_data.name or ""
            )

            stmt_ins = insert(SQL_Company).values(
                uei=uei,
                name=company_data.name,
                website=company_data.location or "",
                industry=company_data.industry or company_data.primary_naics_desc or "Other",
                size=company_data.size or "Small",
                location=company_data.location or "",
                description=company_data.primary_naics_desc or "",
                naics_code=company_data.primary_naics or "",
                match_score=match_score,
                contact=company_data.contact or "N/A",
                email=company_data.email or "",
                phone=company_data.phone or "",
                cage_code=company_data.cage_code or "",
                status=company_data.status or "Active",
                address=company_data.address or "",
                is_small_business=company_data.is_small_business or "N",
                is_minority_owned=company_data.is_minority_owned or "N",
                is_women_owned=company_data.is_women_owned or "N",
                is_veteran_owned=company_data.is_veteran_owned or "N",
                secondary_naics=company_data.secondary_naics or "",
                is_researched=False,
                research_status="pending",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            await db.execute(stmt_ins)
            await db.commit()
            return {"status": "success", "message": "Company added successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.post("/import")
async def import_companies(payload: dict, current_user: dict = Depends(get_current_user)):
    """Bulk import companies from a raw JSON array (small payloads only). For CSV use /import/file."""
    format_type = payload.get("format")
    raw_data = payload.get("data")

    imported_count = 0
    if format_type == "json":
        try:
            items = (json.loads(raw_data) if isinstance(raw_data, str) else raw_data) or []
            async for db in get_db_session():
                for item in items:
                    try:
                        validated_item = CompanyCreateBody(**item)
                    except Exception:
                        continue

                    uei = validated_item.uei.strip().upper()
                    stmt = select(SQL_Company).where(SQL_Company.uei == uei)
                    existing = (await db.execute(stmt)).scalar_one_or_none()
                    if uei and not existing:
                        try:
                            match_score = validated_item.matchScore or compute_company_match_score(
                                primary_naics=validated_item.primary_naics or "",
                                industry_desc=validated_item.industry or validated_item.primary_naics_desc or "Other",
                                company_name=validated_item.name or ""
                            )
                        except Exception:
                            match_score = 75

                        await db.execute(insert(SQL_Company).values(
                            uei=uei,
                            name=validated_item.name,
                            website=validated_item.location or "",
                            industry=validated_item.industry or validated_item.primary_naics_desc or "Other",
                            size=validated_item.size or "Small",
                            location=validated_item.location or "",
                            description=validated_item.primary_naics_desc or "",
                            naics_code=validated_item.primary_naics or "",
                            match_score=match_score,
                            contact=validated_item.contact or "N/A",
                            email=validated_item.email or "",
                            phone=validated_item.phone or "",
                            cage_code=validated_item.cage_code or "",
                            status=validated_item.status or "Active",
                            address=validated_item.address or "",
                            is_small_business=validated_item.is_small_business or "N",
                            is_minority_owned=validated_item.is_minority_owned or "N",
                            is_women_owned=validated_item.is_women_owned or "N",
                            is_veteran_owned=validated_item.is_veteran_owned or "N",
                            secondary_naics=validated_item.secondary_naics or "",
                            is_researched=False,
                            research_status="pending",
                            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                            updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
                        ))

                        imported_count += 1
                await db.commit()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
    elif format_type == "csv":
        try:
            raw_str = (raw_data or "").replace("\x00", "").strip()
            if not raw_str:
                return {"status": "success", "count": 0}
            imported_count = await _process_csv_stream(io.StringIO(raw_str))
        except Exception as e:
            logger.error(f"CSV import failed: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")

    return {"status": "success", "count": imported_count}


@router.post("/import/file")
async def import_companies_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Stream-import companies from a CSV file upload (handles files of any size) to MySQL.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")

    try:
        text_stream = codecs.iterdecode(file.file, "utf-8", errors="replace")
        imported_count = await _process_csv_stream(text_stream)
    except Exception as e:
        logger.error(f"CSV file import failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"CSV processing failed: {str(e)}")
    finally:
        await file.close()

    return {"status": "success", "count": imported_count}


async def _process_csv_stream(text_stream) -> int:
    """
    reads rows from any text iterable, bulk-inserts into MySQL companies table in chunks.
    """
    reader = csv.DictReader(text_stream)
    imported_count = 0
    seen_ueis_in_file: set[str] = set()
    docs_to_insert: list[dict] = []
    CHUNK = 500

    async def _flush_chunk(chunk: list) -> int:
        if not chunk:
            return 0
        all_ueis = [d["uei"] for d in chunk]
        
        existing_ueis: set[str] = set()
        async for db in get_db_session():
            stmt = select(SQL_Company.uei).where(SQL_Company.uei.in_(all_ueis))
            existing_ueis = set((await db.execute(stmt)).scalars().all())

            new_docs = [d for d in chunk if d["uei"] not in existing_ueis]
            if new_docs:
                await db.execute(insert(SQL_Company).values(new_docs))
                await db.commit()
                return len(new_docs)
        return 0

    for row in reader:
        if not isinstance(row, dict):
            continue
        uei = (
            row.get("UEI") or row.get("uei") or
            row.get("Unique_Entity_ID") or row.get("SAM_UEI") or
            row.get("Unique Entity ID") or ""
        )
        if not isinstance(uei, str):
            uei = str(uei or "")
        uei = uei.strip().upper()
        if not uei or uei in seen_ueis_in_file:
            continue

        name = (
            row.get("Legal_Business_Name") or row.get("DBA_Name") or
            row.get("name") or ""
        ).strip()
        if not name:
            continue

        seen_ueis_in_file.add(uei)

        city = (row.get("Phys_City") or row.get("city") or "").strip().title()
        state = (row.get("Phys_State_Province") or row.get("state") or "").strip().upper()
        country = (row.get("Phys_Country") or row.get("country") or "").strip().upper()
        location = f"{city}, {state}" if city and state else (city or state or country or "USA")

        is_small = (row.get("Is_Small_Business") or row.get("is_small_business") or "").strip().upper() in ("Y", "YES", "TRUE")
        primary_naics = (row.get("Primary_NAICS_Code") or row.get("primary_naics") or "").strip()
        primary_naics_desc = (row.get("Primary_NAICS_Description") or row.get("primary_naics_desc") or "").strip()
        contact = (row.get("Gov_Contact_Name") or row.get("EBiz_Contact_Name") or row.get("contact") or "N/A").strip()
        email_val = (row.get("Gov_Contact_Email") or row.get("EBiz_Contact_Email") or row.get("email") or "info@company.com").strip()
        phone = (row.get("Gov_Contact_Phone") or row.get("EBiz_Contact_Phone") or row.get("phone") or "").strip()
        phys_addr1 = (row.get("Phys_Address_1") or row.get("address") or "").strip()
        phys_zip = (row.get("Phys_Zip") or row.get("zip") or "").strip()
        full_address = ", ".join(filter(None, [phys_addr1, city, state, phys_zip, country])) or location
        dba_name = (row.get("DBA_Name") or "").strip()
        cage_code = (row.get("CAGE_Code") or row.get("cage_code") or "").strip()

        try:
            match_score = compute_company_match_score(
                primary_naics=primary_naics,
                industry_desc=primary_naics_desc or "Other",
                company_name=name,
            )
        except Exception:
            match_score = 75

        docs_to_insert.append({
            "uei": uei,
            "name": name,
            "website": location or "",
            "industry": primary_naics_desc or "Other",
            "size": "Small" if is_small else "Large",
            "location": location,
            "description": primary_naics_desc or "",
            "naics_code": primary_naics,
            "match_score": match_score,
            "contact": contact,
            "email": email_val,
            "phone": phone,
            "cage_code": cage_code,
            "status": (row.get("Registration_Status") or row.get("status") or "Active").strip().title(),
            "address": full_address,
            "is_small_business": "Y" if is_small else "N",
            "is_minority_owned": (row.get("Is_Minority_Owned") or "").strip().upper() or "N",
            "is_women_owned": (row.get("Is_Women_Owned") or "").strip().upper() or "N",
            "is_veteran_owned": (row.get("Is_Veteran_Owned") or "").strip().upper() or "N",
            "secondary_naics": (row.get("Secondary_NAICS_Codes") or "").strip(),
            "is_researched": False,
            "research_status": "pending",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })

        if len(docs_to_insert) >= CHUNK:
            imported_count += await _flush_chunk(docs_to_insert)
            docs_to_insert = []

    if docs_to_insert:
        imported_count += await _flush_chunk(docs_to_insert)

    return imported_count


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
    from utils.helpers import get_python_executable
    
    task_key = company_input.strip()
    update_research_task(task_key, 10, "processing", "Starting company research...")
    
    python_bin = get_python_executable()
    cmd = [
        python_bin,
        str(PROJECT_ROOT / "main.py"),
        company_input
    ]
    if force_rescrape:
        cmd.append("--force")
        
    try:
        update_research_task(task_key, 10, "processing", "Starting company research...")
        child_env = os.environ.copy()

        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            text=True,
            encoding="utf-8",
            errors="ignore",
            env=child_env,
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
        
        search_slug = resolved_slug or re.sub(r"[^a-z0-9]+", "-", task_key.lower()).strip("-")
        try:
            profiles_col = get_collection("company_profiles")
            prof = profiles_col.find_one({
                "$or": [
                    {"company_slug": search_slug},
                    {"company_name_slug": search_slug},
                    {"company_name": {"$regex": f"^{re.escape(task_key)}$", "$options": "i"}},
                ]
            })
        except Exception:
            prof = None

        if prof or p.returncode == 0:
            if not resolved_slug:
                resolved_slug = search_slug
            update_research_task(task_key, 100, "completed", "Research completed successfully!", resolved_slug=resolved_slug)
            try:
                if prof:
                    with get_sync_db_session() as db:
                        stmt = update(SQL_Company).where(or_(
                            SQL_Company.name.ilike(task_key),
                            SQL_Company.uei == task_key
                        )).values(
                            is_researched=True,
                            research_status="completed",
                            last_researched_at=datetime.utcnow(),
                            email=prof["emails"][0] if (prof.get("emails") and len(prof["emails"]) > 0) else SQL_Company.email,
                            phone=prof["phone_numbers"][0] if (prof.get("phone_numbers") and len(prof["phone_numbers"]) > 0) else SQL_Company.phone,
                            contact=prof["leadership"][0] if (prof.get("leadership") and len(prof["leadership"]) > 0) else SQL_Company.contact
                        )
                        db.execute(stmt)
                        db.commit()
            except Exception as sync_err:
                print(f"Error syncing researched profile to companies DB: {sync_err}")
        else:
            update_research_task(task_key, 0, "failed", f"Research pipeline exited with code {p.returncode}. Please check server logs.")
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
    result = {}
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_TaskStatus).where(
                    or_(
                        SQL_TaskStatus.task_type == "company_research",
                        SQL_TaskStatus.task_type == "",
                        SQL_TaskStatus.task_type.is_(None)
                    )
                )
                res = await db.execute(stmt)
                for t in res.scalars().all():
                    extra = t.extra_data if isinstance(t.extra_data, dict) else {}
                    if not extra and t.result:
                        if isinstance(t.result, dict):
                            extra = t.result
                        elif isinstance(t.result, str):
                            try:
                                extra = json.loads(t.result)
                            except Exception:
                                pass
                    result[t.task_id] = {
                        "progress": t.progress,
                        "status": t.status,
                        "message": t.message,
                        "started_at": extra.get("started_at"),
                        "resolved_slug": extra.get("resolved_slug")
                    }
        except Exception as e:
            logger.error(f"Failed to fetch research status: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    return result


@router.get("/profiles")
async def get_compacted_profiles(current_user: dict = Depends(get_current_user)):
    """Retrieve all compacted company profiles from MongoDB."""
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
    Search compacted profiles in MongoDB.
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
    """Returns the N most recently updated profiles from MongoDB."""
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
    """Retrieve full detail of a compacted company profile by slug from MongoDB."""
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
    
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_SystemSettings).where(SQL_SystemSettings.key_name == "ai_mode")
                row = (await db.execute(stmt)).scalar_one_or_none()
                if row:
                    await db.execute(
                        update(SQL_SystemSettings)
                        .where(SQL_SystemSettings.key_name == "ai_mode")
                        .values(value=mode, updated_at=datetime.utcnow())
                    )
                else:
                    await db.execute(insert(SQL_SystemSettings).values(
                        key_name="ai_mode",
                        value=mode,
                        updated_at=datetime.utcnow()
                    ))
                await db.commit()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save AI mode settings: {e}")
        
    settings.AI_MODE = mode
    return {"status": "success", "ai_mode": mode}


@router.get("/settings/ai-mode")
async def get_ai_mode(current_user: dict = Depends(get_current_user)):
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_SystemSettings).where(SQL_SystemSettings.key_name == "ai_mode")
                row = (await db.execute(stmt)).scalar_one_or_none()
                if row:
                    val = getattr(row, "value", None)
                    if val:
                        return {"ai_mode": str(val)}
        except Exception:
            pass

    return {"ai_mode": settings.AI_MODE}


@router.get("/pipeline")
async def get_pipeline_items(current_user: dict = Depends(get_current_user)):
    """Retrieve items categorized for the CRM Pipeline stages from MySQL."""
    prospects = []
    contacted = []
    proposals = []
    meetings = []
    negotiation = []
    won = []

    if _mysql_available:
        try:
            async for db in get_db_session():
                # leads -> prospects
                stmt_prosp = select(SQL_Company).limit(10)
                res = await db.execute(stmt_prosp)
                prospects = [{
                    "id": str(c.id),
                    "name": c.name or "",
                    "industry": c.industry or "",
                    "matchScore": c.match_score or 0,
                    "contact": c.contact or "",
                    "uei": c.uei or ""
                } for c in res.scalars().all()]

                # contacted leads
                stmt_cont = select(SQL_Lead).where(SQL_Lead.status.in_(["sent", "opened", "clicked", "replied"])).limit(10)
                res = await db.execute(stmt_cont)
                contacted = [{
                    "id": str(l.id),
                    "email": l.email or "",
                    "contactName": l.contact_name or "",
                    "companyName": l.company_name or "",
                    "status": l.status or ""
                } for l in res.scalars().all()]

                # proposals -> reports table
                stmt_prop = select(SQL_Report).limit(10)
                res = await db.execute(stmt_prop)
                proposals = [{
                    "id": str(r.id),
                    "title": r.title or "",
                    "company_name": r.company_name or "",
                    "proposal_type": r.proposal_type or "",
                    "size": r.size or "",
                    "filename": r.filename or ""
                } for r in res.scalars().all()]

                # meetings
                stmt_meet = select(SQL_Meeting).limit(10)
                res = await db.execute(stmt_meet)
                meetings = [{
                    "id": str(m.id),
                    "title": m.title or "",
                    "host": m.host or "",
                    "startTime": _iso(m.start_time)
                } for m in res.scalars().all()]

                # negotiation -> leads with status = replied
                stmt_neg = select(SQL_Lead).where(SQL_Lead.status == "replied").limit(10)
                res = await db.execute(stmt_neg)
                negotiation = [{
                    "id": str(l.id),
                    "email": l.email or "",
                    "contactName": l.contact_name or "",
                    "companyName": l.company_name or ""
                } for l in res.scalars().all()]

                # won -> tenders with has_award = True
                stmt_won = select(SQL_Tender).where(SQL_Tender.has_award == True).limit(10)
                res = await db.execute(stmt_won)
                won = [{
                    "id": str(t.id),
                    "title": t.title or "",
                    "agency": t.agency or "",
                    "value": float(getattr(t, "value", 0) or 0)
                } for t in res.scalars().all()]


        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {
        "leads": prospects,
        "contacted": contacted,
        "proposals": proposals,
        "meetings": meetings,
        "negotiation": negotiation,
        "won": won
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
    """Retrieve Orbit Avanya's own company profile & inventory from MongoDB."""
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
    """Update or save Orbit Avanya's own company profile in MongoDB."""
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
    """Retrieve full details of a specific company from MySQL."""
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is unavailable.")

    try:
        async for db in get_db_session():
            try:
                comp_id = int(uei)
            except ValueError:
                comp_id = -1

            stmt = select(SQL_Company).where(or_(
                SQL_Company.uei == uei,
                SQL_Company.id == comp_id,
                SQL_Company.name.ilike(uei)
            ))
            res = await db.execute(stmt)
            company = res.scalar_one_or_none()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
            return _format_company(company)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
