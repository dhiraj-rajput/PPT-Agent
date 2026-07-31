"""
app/routes/reports.py
---------------------
Generated PDF reports management and serving using MySQL.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from utils.db_client import get_db_session, get_sync_db_session, _mysql_available
from app.core.auth import get_current_user
from models.sql_models import (
    Report as SQL_Report,
    DraftRequest as SQL_DraftRequest,
    Tender as SQL_Tender,
    EmailLog as SQL_EmailLog,
    Lead as SQL_Lead,
    TaskStatus as SQL_TaskStatus,
)
from sqlalchemy import select, update, insert, delete, func, or_, and_

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR_RFP = PROJECT_ROOT / "output" / "rfp_respond"
LAST_SYNC_TIME = 0.0
SYNC_COOLDOWN = 60.0


def _iso(dt: Any) -> Optional[str]:
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


def sync_reports_with_db():
    """Scan output/pdf folder, parse metadata, and sync with MySQL."""
    if not _mysql_available:
        return

    pdf_dir = PROJECT_ROOT / "output" / "pdf"
    proposals_dir = PROJECT_ROOT / "output" / "proposals"
    rfp_respond_dir = PROJECT_ROOT / "output" / "rfp_respond"

    if not pdf_dir.exists():
        return
        
    synced_filenames = []
    
    try:
        with get_sync_db_session() as db:
            for pdf_path in pdf_dir.glob("*.pdf"):
                filename = pdf_path.name
                synced_filenames.append(filename)
                
                parts = filename.rsplit("_", 1)
                prefix = parts[0] if len(parts) > 1 else filename.replace(".pdf", "")
                solicitation_number = filename.split("_", 1)[0]
                
                lower_filename = filename.lower()
                if "prime" in lower_filename:
                    proposal_type = "Prime RFP Response"
                elif "subcontract" in lower_filename:
                    proposal_type = "Subcontract Response"
                elif "match" in lower_filename:
                    proposal_type = "Product Match Report"
                elif "pitch" in lower_filename:
                    proposal_type = "Pitch Proposal"
                elif "partnership" in lower_filename:
                    proposal_type = "Strategic Partnership Proposal"
                else:
                    proposal_type = "Partnership"
                    
                config_path = proposals_dir / f"{prefix}_config.json"
                if not config_path.exists():
                    config_path = proposals_dir / f"{solicitation_number}_match_config.json"
                    
                company_name = ""
                proposal_title = filename.replace("_", " ").replace(".pdf", "").title()
                proposal_subtitle = ""
                proposal_date = ""
                ref = solicitation_number
                
                if config_path.exists():
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                            brand = cfg.get("brand", {})
                            prop = cfg.get("proposal", {})
                            company_name = prop.get("prepared_for") or brand.get("company_name") or ""
                            proposal_title = prop.get("title") or proposal_title
                            proposal_subtitle = prop.get("subtitle") or ""
                            proposal_date = prop.get("proposal_date") or ""
                            ref = prop.get("engagement_ref") or solicitation_number
                    except Exception as e:
                        print(f"Error parsing config {config_path}: {e}")
                        
                if not company_name or company_name in ("Issuing Agency", "Federal Agency", "Unknown Company"):
                    try:
                        # query draft_requests
                        stmt_dr = select(SQL_DraftRequest).where(or_(
                            SQL_DraftRequest.notice_id == solicitation_number,
                            SQL_DraftRequest.extra_data["solicitation_number"].as_string() == solicitation_number
                        ))
                        existing_draft = db.execute(stmt_dr).scalars().first()
                        if existing_draft and getattr(existing_draft, "extra_data", None):
                            company_name = existing_draft.extra_data.get("tender_title") or existing_draft.extra_data.get("company_name") or ""
                        else:
                            stmt_ten = select(SQL_Tender).where(or_(
                                SQL_Tender.id == solicitation_number,
                                SQL_Tender.solicitation_number == solicitation_number
                            ))
                            existing_tender = db.execute(stmt_ten).scalar_one_or_none()
                            if existing_tender:
                                company_name = str(existing_tender.title or "")
                    except Exception as e:
                        print(f"Error resolving RFP title: {e}")

                if not company_name or company_name in ("Issuing Agency", "Federal Agency", "Unknown Company"):
                    clean_prefix = prefix.replace("_", " ").replace("-", " ").title().strip()
                    if clean_prefix and clean_prefix.lower() not in ("v42", "the"):
                        company_name = clean_prefix
                    elif ref and ref.lower() not in ("v42", "the"):
                        company_name = f"Partner ({ref})"
                    else:
                        company_name = "Target Partner Organization"
                        
                mtime = pdf_path.stat().st_mtime
                if not proposal_date:
                    proposal_date = datetime.fromtimestamp(mtime).strftime("%b %d, %Y")
                    
                file_size_bytes = pdf_path.stat().st_size
                if file_size_bytes >= 1024 * 1024:
                    file_size = f"{file_size_bytes / (1024 * 1024):.1f} MB"
                else:
                    file_size = f"{file_size_bytes / 1024:.0f} KB"
                    
                source = "System"
                if lower_filename.startswith("n0") or lower_filename.startswith("w9") or lower_filename.startswith("fa") or lower_filename.startswith("doc"):
                    source = "SAM.gov"
                elif "rfp" in lower_filename or "auto" in lower_filename:
                    source = "RFP Auto-Respond"
                else:
                    try:
                        stmt_t = select(SQL_Tender).where(SQL_Tender.solicitation_number == solicitation_number)
                        if db.execute(stmt_t).scalars().first():
                            source = "SAM.gov"
                    except Exception:
                        pass

                stmt_rep = select(SQL_Report).where(SQL_Report.filename == filename)
                existing_report = db.execute(stmt_rep).scalar_one_or_none()

                report_extra = {
                    "company_name": company_name,
                    "companyName": company_name,
                    "proposal_type": proposal_type,
                    "proposalType": proposal_type,
                    "solicitation_number": solicitation_number,
                    "title": proposal_title,
                    "subtitle": proposal_subtitle,
                    "date": proposal_date,
                    "size": file_size,
                    "ref": ref,
                    "type": "PDF",
                    "source": source,
                    "mtime": mtime
                }

                if not existing_report:
                    stmt_ins = insert(SQL_Report).values(
                        filename=filename,
                        file_path=str(pdf_path),
                        file_size=file_size_bytes,
                        report_type=proposal_type,
                        status="completed",
                        extra_data=report_extra,
                        created_at=datetime.fromtimestamp(mtime)
                    )
                    db.execute(stmt_ins)
                else:
                    db.execute(
                        update(SQL_Report)
                        .where(SQL_Report.id == existing_report.id)
                        .values(extra_data=report_extra, report_type=proposal_type)
                    )

        db.commit()

        # Also sync RFP Auto-Respond outputs (DOCX/PDF)
        if rfp_respond_dir.exists():
            for rfp_path in list(rfp_respond_dir.glob("rfp_respond_*")):
                filename = rfp_path.name
                if filename in synced_filenames:
                    continue
                synced_filenames.append(filename)
                mtime = rfp_path.stat().st_mtime
                file_size_bytes = rfp_path.stat().st_size
                file_ext = rfp_path.suffix.upper().lstrip('.')
                file_size = f"{round(file_size_bytes / 1024)} KB"
                extra = {
                    "company_name": "RFP Auto-Respond",
                    "companyName": "RFP Auto-Respond",
                    "proposal_type": "RFP Auto-Response",
                    "proposalType": "RFP Auto-Response",
                    "solicitation_number": "",
                    "title": filename,
                    "subtitle": "AI-generated RFP proposal",
                    "date": datetime.fromtimestamp(mtime).strftime("%b %d, %Y"),
                    "size": file_size,
                    "ref": "",
                    "type": file_ext,
                    "source": "RFP Auto-Respond",
                    "mtime": mtime,
                    "rfp_respond": True,
                }
                stmt_r = select(SQL_Report).where(SQL_Report.filename == filename)
                existing_r = db.execute(stmt_r).scalar_one_or_none()
                if not existing_r:
                    db.execute(insert(SQL_Report).values(
                        filename=filename,
                        file_path=str(rfp_path),
                        file_size=file_size_bytes,
                        report_type="RFP Auto-Response",
                        status="Generated",
                        extra_data=extra,
                        created_at=datetime.fromtimestamp(mtime),
                    ))
            db.commit()
    except Exception as e:
        logger.warning(f"Error in sync_reports_with_db: {e}")



def _format_report(r: SQL_Report) -> dict:
    extra = r.extra_data or {} if isinstance(r.extra_data, dict) else {}
    f_size = getattr(r, "file_size", 0) or 0
    c_name = extra.get("company_name") or extra.get("companyName")
    if not c_name or c_name in ("Unknown Company", "Issuing Agency", "Federal Agency"):
        filename = r.filename or ""
        prefix = filename.split("_", 1)[0].replace(".pdf", "").replace("-", " ").title()
        c_name = prefix if prefix and prefix.lower() not in ("v42", "the") else "Target Partner Organization"

    p_type = extra.get("proposal_type") or extra.get("proposalType") or r.report_type or "Partnership Proposal"

    return {
        "id": str(r.id),
        "filename": r.filename or "",
        "company_name": c_name,
        "companyName": c_name,
        "proposal_type": p_type,
        "proposalType": p_type,
        "solicitation_number": extra.get("solicitation_number", ""),
        "title": extra.get("title") or r.filename or "",
        "subtitle": extra.get("subtitle", ""),
        "date": extra.get("date", ""),
        "size": extra.get("size") or f"{round(float(f_size)/1024)} KB",
        "ref": extra.get("ref", ""),
        "type": extra.get("type", "PDF"),
        "source": extra.get("source", "System"),
        "mtime": extra.get("mtime", time.time()),
        "status": str(getattr(r, "status", "done") or "done"),
        "createdAt": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
        "filepath": r.file_path
    }


_format_report_dict = _format_report



@router.get("")
async def get_reports(current_user: dict = Depends(get_current_user)):
    """Retrieve all reports synced with MySQL sorted by date descending."""
    global LAST_SYNC_TIME
    try:
        now = time.time()
        if now - LAST_SYNC_TIME > SYNC_COOLDOWN:
            await asyncio.to_thread(sync_reports_with_db)
            LAST_SYNC_TIME = now

        reports_list = []
        if _mysql_available:
            async for db in get_db_session():
                stmt = select(SQL_Report).order_by(SQL_Report.created_at.desc())
                res = await db.execute(stmt)
                reports_list = [_format_report_dict(r) for r in res.scalars().all()]
        return reports_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{filename}/status")
async def update_report_status(
    filename: str,
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update report workflow status."""
    new_status = payload.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Status is required.")
        
    safe_filename = Path(filename).name
    
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_Report).where(SQL_Report.filename == safe_filename)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if not existing:
                    raise HTTPException(status_code=404, detail="Report record not found.")

                await db.execute(
                    update(SQL_Report)
                    .where(SQL_Report.id == existing.id)
                    .values(status=new_status, updated_at=datetime.utcnow())
                )
                await db.commit()
                return {"ok": True, "filename": safe_filename, "status": new_status}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=500, detail="Database is unavailable.")


class SendReportEmailBody(BaseModel):
    filename: str
    to_email: str
    subject: str
    body: str
    company_name: Optional[str] = None


@router.post("/send-email")
async def send_report_email(
    body: SendReportEmailBody,
    current_user: dict = Depends(get_current_user)
):
    """Send proposal PDF report via email and record note in Email Campaign & CRM logs."""
    safe_filename = Path(body.filename).name
    pdf_path = Path("output/pdf") / safe_filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"Report file '{safe_filename}' not found.")

    attachments_list = [{
        "path": str(pdf_path.resolve()),
        "filename": safe_filename
    }]

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

    # Update report status to Sent in MySQL reports table
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt_rep = select(SQL_Report).where(SQL_Report.filename == safe_filename)
                existing = (await db.execute(stmt_rep)).scalar_one_or_none()
                if existing:
                    await db.execute(
                        update(SQL_Report)
                        .where(SQL_Report.id == existing.id)
                        .values(status="Sent", updated_at=datetime.utcnow())
                    )

                # Log to email_logs
                stmt_lead = select(SQL_Lead).where(SQL_Lead.email == body.to_email)
                lead = (await db.execute(stmt_lead)).scalar_one_or_none()
                lead_id = lead.id if lead else None

                db.add(SQL_EmailLog(
                    campaign_id=None,
                    lead_id=lead_id,
                    email=body.to_email,
                    subject=body.subject,
                    status="sent",
                    sent_at=datetime.utcnow(),
                    created_at=datetime.utcnow()
                ))

                # Sync lead status to sent in CRM pipeline
                if lead:
                    await db.execute(
                        update(SQL_Lead)
                        .where(SQL_Lead.id == lead.id)
                        .values(
                            status="sent",
                            updated_at=datetime.utcnow()
                        )
                    )
                else:
                    db.add(SQL_Lead(
                        email=body.to_email,
                        status="sent",
                        company_name=body.company_name or "Recipient",
                        contact_name="Recipient",
                        created_by=int(current_user["id"]),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    ))
                await db.commit()
        except Exception as e:
            logger.error(f"Failed logging sent report email: {e}")

    return {"ok": True, "message": f"Proposal email sent successfully to {body.to_email} and logged to campaign!"}


@router.get("/view/{filename}")
async def view_report(filename: str, current_user: dict = Depends(get_current_user)):
    """Serve a PDF report inline in the browser."""
    safe_filename = Path(filename).name
    
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_TaskStatus).where(SQL_TaskStatus.extra_data["filename"].as_string() == safe_filename)
                task = (await db.execute(stmt)).scalars().first()
                if task and getattr(task, "extra_data", None):
                    extra = task.extra_data if isinstance(task.extra_data, dict) else {}
                    user_id = str(current_user["id"])
                    if extra.get("userId") and str(extra.get("userId")) != user_id:
                        raise HTTPException(status_code=403, detail="Access denied: You do not own this file.")
        except HTTPException:
            raise
        except Exception:
            pass

    # Try pdf dir first, then rfp_respond dir
    pdf_path = Path("output/pdf") / safe_filename
    if not pdf_path.exists():
        rfp_path = OUTPUT_DIR_RFP / safe_filename
        if rfp_path.exists():
            pdf_path = rfp_path
        else:
            raise HTTPException(status_code=404, detail="Report file not found")

    suffix = pdf_path.suffix.lower()
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if suffix == ".docx"
        else "application/pdf" if suffix == ".pdf" else "application/octet-stream"
    )
    return FileResponse(pdf_path, media_type=media_type)


@router.get("/download/{filename}")
async def download_report(filename: str, current_user: dict = Depends(get_current_user)):
    """Force download of a PDF report."""
    safe_filename = Path(filename).name
    
    if _mysql_available:
        try:
            async for db in get_db_session():
                stmt = select(SQL_TaskStatus).where(SQL_TaskStatus.extra_data["filename"].as_string() == safe_filename)
                task = (await db.execute(stmt)).scalars().first()
                if task and getattr(task, "extra_data", None):
                    extra = task.extra_data if isinstance(task.extra_data, dict) else {}
                    user_id = str(current_user["id"])
                    if extra.get("userId") and str(extra.get("userId")) != user_id:
                        raise HTTPException(status_code=403, detail="Access denied: You do not own this file.")


                stmt_rep = select(SQL_Report).where(SQL_Report.filename == safe_filename)
                existing = (await db.execute(stmt_rep)).scalar_one_or_none()
                if existing and existing.status not in ("Sent", "Submitted"):
                    await db.execute(
                        update(SQL_Report)
                        .where(SQL_Report.id == existing.id)
                        .values(status="Downloaded", updated_at=datetime.utcnow())
                    )
                    await db.commit()
        except HTTPException:
            raise
        except Exception:
            pass

    pdf_path = Path("output/pdf") / safe_filename
    if not pdf_path.exists():
        rfp_path = OUTPUT_DIR_RFP / safe_filename
        if rfp_path.exists():
            pdf_path = rfp_path
        else:
            raise HTTPException(status_code=404, detail="Report file not found")

    suffix = pdf_path.suffix.lower()
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if suffix == ".docx"
        else "application/pdf" if suffix == ".pdf" else "application/octet-stream"
    )
    return FileResponse(pdf_path, media_type=media_type, filename=safe_filename)
