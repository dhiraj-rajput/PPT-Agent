"""
app/routes/people.py
-------------------------
People / Contacts CRM endpoints: search, filtering, manual entry, and
strict CSV import. Uses MySQL (people table) — see models.sql_models.Person.

CSV import enforces exact column matching: the file must contain all 18 DB
columns (no aliases, no extras, no missing columns).
"""

from __future__ import annotations

import codecs
import csv
import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from models.sql_models import Person as SQL_Person
from pydantic import BaseModel
from sqlalchemy import and_, func, insert, or_, select
from utils.db_client import _mysql_available, get_db_session

from app.core.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/people", tags=["people"])

VALID_STATUSES = {"Pending", "Processing", "Completed", "Failed", "Duplicate"}
VALID_SOURCES = {"Apollo", "LinkedIn", "CSV Import", "Excel Import", "Manual Entry"}

REQUIRED_COLUMNS = [
    "source", "status", "organization_name",
    "first_name", "last_name", "full_name",
    "title", "function_name", "seniority",
    "email", "email_status", "email_confidence",
    "phone", "linkedin_url",
    "city", "state", "country",
    "job_start_date",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(dt: Any) -> str | None:
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


def _parse_date(val: Any):
    """Best-effort parse of a date coming from a form, CSV, or Excel cell."""
    if not val:
        return None
    if isinstance(val, (datetime, date)):
        return val
    val = str(val).strip()
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _format_person(p: SQL_Person) -> dict:
    if not p:
        return {}
    return {
        "id": str(p.id),
        "source": p.source or "Manual Entry",
        "status": p.status or "Pending",
        "organization_name": p.organization_name or "",
        "first_name": p.first_name or "",
        "last_name": p.last_name or "",
        "full_name": p.full_name or "",
        "title": p.title or "",
        "function_name": p.function_name or "",
        "seniority": p.seniority or "",
        "email": p.email or "",
        "email_status": p.email_status or "",
        "email_confidence": float(p.email_confidence) if p.email_confidence is not None else None,
        "phone": p.phone or "",
        "linkedin_url": p.linkedin_url or "",
        "city": p.city or "",
        "state": p.state or "",
        "country": p.country or "",
        "job_start_date": _iso(p.job_start_date),
        "createdAt": _iso(p.created_at),
        "updatedAt": _iso(p.updated_at),
    }


class PersonCreateBody(BaseModel):
    source: str | None = "Manual Entry"
    status: str | None = "Pending"
    organization_name: str | None = ""
    first_name: str | None = ""
    last_name: str | None = ""
    full_name: str | None = ""
    title: str | None = ""
    function_name: str | None = ""
    seniority: str | None = ""
    email: str | None = ""
    email_status: str | None = ""
    email_confidence: float | None = None
    phone: str | None = ""
    linkedin_url: str | None = ""
    city: str | None = ""
    state: str | None = ""
    country: str | None = ""
    job_start_date: str | None = ""


# ---------------------------------------------------------------------------
# List / Search / Filter / Paginate
# ---------------------------------------------------------------------------

@router.get("")
async def get_people(
    query: str | None = None,
    status: str | None = None,
    source: str | None = None,
    country: str | None = None,
    seniority: str | None = None,
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Query people from MySQL with unified search, filters, and pagination."""
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is not connected.")

    try:
        filter_conditions = []

        if query and query.strip():
            q = query.strip()
            filter_conditions.append(or_(
                SQL_Person.full_name.ilike(f"%{q}%"),
                SQL_Person.first_name.ilike(f"%{q}%"),
                SQL_Person.last_name.ilike(f"%{q}%"),
                SQL_Person.email.ilike(f"%{q}%"),
                SQL_Person.organization_name.ilike(f"%{q}%"),
                SQL_Person.title.ilike(f"%{q}%"),
                SQL_Person.phone.ilike(f"%{q}%"),
            ))

        if status and status != "All":
            filter_conditions.append(SQL_Person.status == status)
        if source and source != "All":
            filter_conditions.append(SQL_Person.source == source)
        if country and country != "All":
            filter_conditions.append(SQL_Person.country == country)
        if seniority and seniority != "All":
            filter_conditions.append(SQL_Person.seniority == seniority)

        stmt = select(SQL_Person)
        if filter_conditions:
            stmt = stmt.where(and_(*filter_conditions))
        stmt = stmt.order_by(SQL_Person.created_at.desc())

        results: list[SQL_Person] = []
        total = 0
        source_options: list[str] = []
        country_options: list[str] = []

        async for db in get_db_session():
            count_stmt = select(func.count()).select_from(SQL_Person)
            if filter_conditions:
                count_stmt = count_stmt.where(and_(*filter_conditions))
            total = (await db.execute(count_stmt)).scalar() or 0

            skip = (page - 1) * limit
            res = await db.execute(stmt.offset(skip).limit(limit))
            results = res.scalars().all()

            src_res = await db.execute(select(SQL_Person.source).distinct())
            source_options = sorted([s for s in src_res.scalars().all() if s])

            country_res = await db.execute(select(SQL_Person.country).distinct())
            country_options = sorted([c for c in country_res.scalars().all() if c])

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "people": [_format_person(p) for p in results],
            "source_options": source_options,
            "country_options": country_options,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Manual add (single record)
# ---------------------------------------------------------------------------

@router.post("")
async def add_person(
    person_data: PersonCreateBody,
    current_user: dict = Depends(get_current_user),
):
    """Add a single person record manually to MySQL."""
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is unavailable.")

    full_name = (person_data.full_name or "").strip()
    if not full_name:
        full_name = f"{(person_data.first_name or '').strip()} {(person_data.last_name or '').strip()}".strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Full name (or first/last name) is required")

    try:
        async for db in get_db_session():
            stmt_ins = insert(SQL_Person).values(
                source=person_data.source or "Manual Entry",
                status=person_data.status or "Pending",
                organization_name=person_data.organization_name or "",
                first_name=person_data.first_name or "",
                last_name=person_data.last_name or "",
                full_name=full_name,
                title=person_data.title or "",
                function_name=person_data.function_name or "",
                seniority=person_data.seniority or "",
                email=person_data.email or "",
                email_status=person_data.email_status or "",
                email_confidence=person_data.email_confidence,
                phone=person_data.phone or "",
                linkedin_url=person_data.linkedin_url or "",
                city=person_data.city or "",
                state=person_data.state or "",
                country=person_data.country or "",
                job_start_date=_parse_date(person_data.job_start_date),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            await db.execute(stmt_ins)
            await db.commit()
            return {"status": "success", "message": "Person added successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


# ---------------------------------------------------------------------------
# CSV file import (flexible alias mapping)
# ---------------------------------------------------------------------------

# Alias map: db_field -> list of accepted CSV header variants (lowercase, stripped)
COL_ALIASES: dict[str, list] = {
    "full_name":        ["full name", "full_name", "name"],
    "first_name":       ["first name", "first_name", "firstname"],
    "last_name":        ["last name", "last_name", "lastname", "surname"],
    "organization_name":["organization", "organization name", "organization_name", "company", "company name", "company_name"],
    "title":            ["title", "job title", "job_title", "position"],
    "function_name":    ["function", "function_name", "department"],
    "seniority":        ["seniority", "level"],
    "email":            ["email", "email address", "email_address"],
    "email_status":     ["email status", "email_status"],
    "email_confidence": ["email confidence", "email_confidence", "confidence"],
    "phone":            ["phone", "phone number", "phone_number", "mobile"],
    "linkedin_url":     ["linkedin", "linkedin url", "linkedin_url"],
    "city":             ["city"],
    "state":            ["state", "province"],
    "country":          ["country"],
    "job_start_date":   ["job start date", "job_start_date", "start date", "start_date"],
    "source":           ["source"],
    "status":           ["status"],
}


def _build_header_map(fieldnames) -> dict[str, str]:
    """Map raw CSV header -> db field name using COL_ALIASES (case-insensitive)."""
    mapping: dict[str, str] = {}
    for h in (fieldnames or []):
        lower = h.strip().lower()
        for field, aliases in COL_ALIASES.items():
            if lower in aliases:
                mapping[h] = field
                break
    return mapping


def _get_field(row: dict[str, Any], field: str) -> str:
    val = row.get(field)
    return str(val).strip() if val not in (None, "") else ""


# ---------------------------------------------------------------------------
# JSON import  (client-parsed CSV rows after preview-table review)
# ---------------------------------------------------------------------------

@router.post("/import/json")
async def import_people_json(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Accept an array of person dicts (already validated client-side from the
    CSV preview table) and bulk-insert them into MySQL.  Each row is validated
    against PersonCreateBody before insertion; invalid rows are skipped.
    """
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is unavailable.")

    rows = payload.get("rows") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="'rows' must be a non-empty list.")

    imported_count = 0
    skipped = 0
    CHUNK = 500
    chunk: list[dict] = []

    try:
        async for db in get_db_session():
            for item in rows:
                try:
                    v = PersonCreateBody(**{k: (item.get(k) or "") for k in REQUIRED_COLUMNS})
                except Exception:
                    skipped += 1
                    continue

                full_name = (v.full_name or "").strip()
                if not full_name:
                    full_name = f"{(v.first_name or '').strip()} {(v.last_name or '').strip()}".strip()
                if not full_name:
                    skipped += 1
                    continue

                chunk.append({
                    "source": v.source or "CSV Import",
                    "status": v.status if v.status in VALID_STATUSES else "Pending",
                    "organization_name": v.organization_name or "",
                    "first_name": v.first_name or "",
                    "last_name": v.last_name or "",
                    "full_name": full_name,
                    "title": v.title or "",
                    "function_name": v.function_name or "",
                    "seniority": v.seniority or "",
                    "email": v.email or "",
                    "email_status": v.email_status or "",
                    "email_confidence": v.email_confidence,
                    "phone": v.phone or "",
                    "linkedin_url": v.linkedin_url or "",
                    "city": v.city or "",
                    "state": v.state or "",
                    "country": v.country or "",
                    "job_start_date": _parse_date(v.job_start_date),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                })

                if len(chunk) >= CHUNK:
                    await db.execute(insert(SQL_Person).values(chunk))
                    await db.commit()
                    imported_count += len(chunk)
                    chunk = []

            if chunk:
                await db.execute(insert(SQL_Person).values(chunk))
                await db.commit()
                imported_count += len(chunk)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {e}")

    return {"status": "success", "count": imported_count, "skipped": skipped}


def _row_to_person_dict(row: dict[str, Any]) -> dict | None:
    """Map a normalised CSV row (keys are DB field names) to a Person insert dict."""
    full_name = _get_field(row, "full_name")
    first_name = _get_field(row, "first_name")
    last_name = _get_field(row, "last_name")
    if not full_name:
        full_name = f"{first_name} {last_name}".strip()
    if not full_name and not _get_field(row, "email"):
        return None  # skip rows with no name and no email

    status_val = _get_field(row, "status") or "Pending"
    if status_val not in VALID_STATUSES:
        status_val = "Pending"

    conf_raw = _get_field(row, "email_confidence")
    try:
        confidence = round(float(conf_raw), 2) if conf_raw else None
    except ValueError:
        confidence = None

    return {
        "source": _get_field(row, "source") or "CSV Import",
        "status": status_val,
        "organization_name": _get_field(row, "organization_name"),
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "title": _get_field(row, "title"),
        "function_name": _get_field(row, "function_name"),
        "seniority": _get_field(row, "seniority"),
        "email": _get_field(row, "email"),
        "email_status": _get_field(row, "email_status"),
        "email_confidence": confidence,
        "phone": _get_field(row, "phone"),
        "linkedin_url": _get_field(row, "linkedin_url"),
        "city": _get_field(row, "city"),
        "state": _get_field(row, "state"),
        "country": _get_field(row, "country"),
        "job_start_date": _parse_date(_get_field(row, "job_start_date")),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }




async def _flush_chunk(chunk: list[dict]) -> int:
    if not chunk:
        return 0
    async for db in get_db_session():
        await db.execute(insert(SQL_Person).values(chunk))
        await db.commit()
        return len(chunk)
    return 0


async def _process_csv_stream(text_stream) -> int:
    """
    Parse and insert a CSV stream using flexible alias-based column mapping.
    Only requires that each row has at least a name (first/last/full) or an email.
    Unrecognised columns are silently ignored.
    """
    reader = csv.DictReader(text_stream)

    # Force header read
    if reader.fieldnames is None:
        try:
            next(reader)
        except StopIteration:
            return 0
        if reader.fieldnames is None:
            raise HTTPException(status_code=400, detail="CSV file is empty or has no header row.")

    header_map = _build_header_map(reader.fieldnames)  # raw header -> db field
    mapped = set(header_map.values())
    has_name = bool(mapped & {"full_name", "first_name", "last_name"})
    has_email = "email" in mapped
    if not has_name and not has_email:
        raise HTTPException(
            status_code=400,
            detail=(
                'Could not recognise any name or email column. '
                'Please include at least "First Name", "Last Name", "Full Name", or "Email".'
            )
        )

    imported_count = 0
    chunk: list[dict] = []
    CHUNK = 500

    for raw_row in reader:
        if not isinstance(raw_row, dict):
            continue
        # Normalise: map raw CSV headers to db field names
        norm: dict[str, Any] = {}
        for raw_h, val in raw_row.items():
            db_field = header_map.get(raw_h)
            if db_field:
                norm[db_field] = val
        doc = _row_to_person_dict(norm)
        if not doc:
            continue
        chunk.append(doc)
        if len(chunk) >= CHUNK:
            imported_count += await _flush_chunk(chunk)
            chunk = []

    if chunk:
        imported_count += await _flush_chunk(chunk)

    return imported_count


@router.post("/import/file")
async def import_people_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Import people from a CSV file upload into MySQL.
    The CSV must contain exactly the 18 DB columns listed in REQUIRED_COLUMNS —
    no aliases, no extra columns, no missing columns. Returns a clear 400 error
    describing any mismatch before touching the database.
    """
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted. Please upload a .csv file.")

    try:
        text_stream = codecs.iterdecode(file.file, "utf-8", errors="replace")
        imported_count = await _process_csv_stream(text_stream)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"People file import failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"File processing failed: {e!s}")
    finally:
        await file.close()

    return {"status": "success", "count": imported_count}


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/{person_id}")
async def get_person_detail(
    person_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve full details of a specific person from MySQL."""
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is unavailable.")

    try:
        pid = int(person_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid person id")

    try:
        async for db in get_db_session():
            stmt = select(SQL_Person).where(SQL_Person.id == pid)
            res = await db.execute(stmt)
            person = res.scalar_one_or_none()
            if not person:
                raise HTTPException(status_code=404, detail="Person not found")
            return _format_person(person)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Update (PATCH)
# ---------------------------------------------------------------------------

@router.patch("/{person_id}")
async def update_person(
    person_id: str,
    updates: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Partially update a person record. Only the fields present in the request
    body are changed; unmentioned fields are left intact.
    """
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is unavailable.")

    try:
        pid = int(person_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid person id")

    # Whitelist of updatable columns (no id / created_at)
    ALLOWED = {
        "source", "status", "organization_name",
        "first_name", "last_name", "full_name",
        "title", "function_name", "seniority",
        "email", "email_status", "email_confidence",
        "phone", "linkedin_url",
        "city", "state", "country",
        "job_start_date",
    }

    patch_values: dict = {}
    for key, val in updates.items():
        if key not in ALLOWED:
            continue
        if key == "job_start_date":
            patch_values[key] = _parse_date(val)
        elif key == "email_confidence":
            try:
                patch_values[key] = round(float(val), 2) if val not in (None, "", "None") else None
            except (ValueError, TypeError):
                patch_values[key] = None
        else:
            patch_values[key] = str(val).strip() if val is not None else ""

    if not patch_values:
        raise HTTPException(status_code=400, detail="No valid fields provided to update.")

    patch_values["updated_at"] = datetime.utcnow()

    # Auto-rebuild full_name if first/last changed but full_name not explicitly set
    if ("first_name" in patch_values or "last_name" in patch_values) and "full_name" not in patch_values:
        patch_values["full_name"] = None  # resolved after fetch below

    try:
        from sqlalchemy import update as sql_update
        async for db in get_db_session():
            res = await db.execute(select(SQL_Person).where(SQL_Person.id == pid))
            person = res.scalar_one_or_none()
            if not person:
                raise HTTPException(status_code=404, detail="Person not found")

            # Rebuild full_name from names if needed
            if patch_values.get("full_name") is None and (
                "first_name" in patch_values or "last_name" in patch_values
            ):
                fn = patch_values.get("first_name", person.first_name or "")
                ln = patch_values.get("last_name", person.last_name or "")
                patch_values["full_name"] = f"{fn} {ln}".strip() or person.full_name or ""

            await db.execute(
                sql_update(SQL_Person).where(SQL_Person.id == pid).values(**patch_values)
            )
            await db.commit()
            return {"status": "success", "message": "Person updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/{person_id}")
async def delete_person(
    person_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Permanently delete a single person record from MySQL."""
    if not _mysql_available:
        raise HTTPException(status_code=500, detail="MySQL database is unavailable.")

    try:
        pid = int(person_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid person id")

    try:
        from sqlalchemy import delete as sql_delete
        async for db in get_db_session():
            res = await db.execute(select(SQL_Person).where(SQL_Person.id == pid))
            if not res.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="Person not found")
            await db.execute(sql_delete(SQL_Person).where(SQL_Person.id == pid))
            await db.commit()
            return {"status": "success", "message": "Person deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
