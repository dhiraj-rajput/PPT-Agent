"""
app/routes/reports.py
---------------------
Generated PDF reports management and serving using Motor async client.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from utils.db_client import get_async_collection, get_collection
from app.core.auth import get_current_user

router = APIRouter(prefix="/reports", tags=["reports"])

import time
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LAST_SYNC_TIME = 0.0
SYNC_COOLDOWN = 60.0


def sync_reports_with_mongo():
    """Scan output/pdf folder, parse metadata using config files, and sync with MongoDB (sync thread worker)."""
    pdf_dir = PROJECT_ROOT / "output" / "pdf"
    proposals_dir = PROJECT_ROOT / "output" / "proposals"
    reports_col = get_collection("reports")
    
    if not pdf_dir.exists():
        return []
        
    synced_filenames = []
    
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
            
        company_name = "Unknown Company"
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
                    company_name = prop.get("prepared_for") or brand.get("company_name") or "Unknown Company"
                    proposal_title = prop.get("title") or proposal_title
                    proposal_subtitle = prop.get("subtitle") or ""
                    proposal_date = prop.get("proposal_date") or ""
                    ref = prop.get("engagement_ref") or solicitation_number
            except Exception as e:
                print(f"Error parsing config {config_path}: {e}")
                
        if proposal_type == "Prime RFP Response" or company_name in ("Issuing Agency", "Federal Agency", "Unknown Company"):
            try:
                drafts_col = get_collection("draft_requests")
                existing_draft = drafts_col.find_one(
                    {
                        "$or": [
                            {"notice_id": solicitation_number},
                            {"solicitation_number": solicitation_number}
                        ]
                    }
                )
                if existing_draft and existing_draft.get("tender_title"):
                    company_name = existing_draft.get("tender_title")
                else:
                    tenders_col = get_collection("tenders")
                    existing_tender = tenders_col.find_one(
                        {
                            "$or": [
                                {"id": solicitation_number},
                                {"solicitation_number": solicitation_number}
                            ]
                        }
                    )
                    if existing_tender and existing_tender.get("title"):
                        company_name = existing_tender.get("title")
            except Exception as e:
                print(f"Error resolving RFP title: {e}")
                
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
                tenders_col = get_collection("tenders")
                if tenders_col.find_one({"solicitationNumber": solicitation_number}):
                    source = "SAM.gov"
            except Exception:
                pass

        existing_report = reports_col.find_one({"filename": filename})
        existing_status = existing_report.get("status", "Generated") if existing_report else "Generated"

        report_record = {
            "filename": filename,
            "company_name": company_name,
            "proposal_type": proposal_type,
            "solicitation_number": solicitation_number,
            "title": proposal_title,
            "subtitle": proposal_subtitle,
            "date": proposal_date,
            "size": file_size,
            "ref": ref,
            "type": "PDF",
            "source": source,
            "mtime": mtime,
            "status": existing_status,
            "createdAt": datetime.fromtimestamp(mtime),
            "filepath": str(pdf_path.resolve())
        }
        
        reports_col.update_one(
            {"filename": filename},
            {"$set": report_record},
            upsert=True
        )
        
    all_stored = list(reports_col.find({}, {"filename": 1}))
    for record in all_stored:
        if record["filename"] not in synced_filenames:
            reports_col.delete_one({"filename": record["filename"]})


@router.get("")
async def get_reports(current_user: dict = Depends(get_current_user)):
    """Retrieve all reports synced with MongoDB sorted by date descending."""
    global LAST_SYNC_TIME
    try:
        now = time.time()
        if now - LAST_SYNC_TIME > SYNC_COOLDOWN:
            await asyncio.to_thread(sync_reports_with_mongo)
            LAST_SYNC_TIME = now
        reports_col = get_async_collection("reports")
        reports = await reports_col.find({}, {"_id": 0}).sort("mtime", -1).to_list(length=1000)
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{filename}/status")
async def update_report_status(
    filename: str,
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update report workflow status (Generated, Draft, Sent, Submitted, Downloaded)."""
    new_status = payload.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Status is required.")
        
    safe_filename = Path(filename).name
    col = get_async_collection("reports")
    res = await col.update_one(
        {"filename": safe_filename},
        {"$set": {"status": new_status, "updatedAt": datetime.utcnow()}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Report record not found.")
        
    return {"ok": True, "filename": safe_filename, "status": new_status}


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
    from pydantic import BaseModel
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

    # Update report status to Sent in reports collection
    reports_col = get_async_collection("reports")
    await reports_col.update_one(
        {"filename": safe_filename},
        {"$set": {"status": "Sent", "sentTo": body.to_email, "sentAt": datetime.utcnow()}}
    )

    # Log in email_campaigns / outreach_events for Email Campaign integration
    email_logs_col = get_async_collection("email_logs")
    outreach_doc = {
        "user_id": str(current_user["_id"]),
        "to_email": body.to_email,
        "company_name": body.company_name or "Recipient",
        "subject": body.subject,
        "body_snippet": body.body[:200],
        "attachment_filename": safe_filename,
        "type": "proposal_email",
        "status": "sent",
        "timestamp": datetime.utcnow()
    }
    await email_logs_col.insert_one(outreach_doc)

    # Sync lead status to contacted in CRM pipeline
    leads_col = get_async_collection("leads")
    await leads_col.update_one(
        {"email": body.to_email},
        {"$set": {
            "status": "sent",
            "last_contacted": datetime.utcnow(),
            "companyName": body.company_name or "Recipient",
            "last_proposal": safe_filename
        }},
        upsert=True
    )

    return {"ok": True, "message": f"Proposal email sent successfully to {body.to_email} and logged to campaign!"}


@router.get("/view/{filename}")
async def view_report(filename: str, current_user: dict = Depends(get_current_user)):
    """Serve a PDF report inline in the browser."""
    safe_filename = Path(filename).name
    
    col = get_async_collection("task_statuses")
    task = await col.find_one({"filename": safe_filename})
    if task:
        user_id = str(current_user["_id"])
        if task.get("userId") and str(task.get("userId")) != user_id:
            raise HTTPException(status_code=403, detail="Access denied: You do not own this file.")

    pdf_path = Path("output/pdf") / safe_filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(pdf_path, media_type="application/pdf")


@router.get("/download/{filename}")
async def download_report(filename: str, current_user: dict = Depends(get_current_user)):
    """Force download of a PDF report."""
    safe_filename = Path(filename).name
    
    col = get_async_collection("task_statuses")
    task = await col.find_one({"filename": safe_filename})
    if task:
        user_id = str(current_user["_id"])
        if task.get("userId") and str(task.get("userId")) != user_id:
            raise HTTPException(status_code=403, detail="Access denied: You do not own this file.")

    pdf_path = Path("output/pdf") / safe_filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")

    # Update report status to Downloaded if not already sent/submitted
    reports_col = get_async_collection("reports")
    existing = await reports_col.find_one({"filename": safe_filename})
    if existing and existing.get("status") not in ("Sent", "Submitted"):
        await reports_col.update_one({"filename": safe_filename}, {"$set": {"status": "Downloaded"}})

    return FileResponse(pdf_path, media_type="application/pdf", filename=safe_filename)

