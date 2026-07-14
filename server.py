import os
import json
import uvicorn
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from utils.db_client import get_collection, close_connection

app = FastAPI(title="PPT-Agent Backend API", version="1.0")

# Enable CORS for frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def sync_reports_with_mongo():
    """Scan output/pdf folder, parse metadata using config files, and sync with MongoDB."""
    pdf_dir = Path("output/pdf")
    proposals_dir = Path("output/proposals")
    reports_col = get_collection("reports")
    
    if not pdf_dir.exists():
        return []
        
    synced_filenames = []
    
    for pdf_path in pdf_dir.glob("*.pdf"):
        filename = pdf_path.name
        synced_filenames.append(filename)
        
        # Attempt to find corresponding proposal config JSON
        # Filenames look like: N00164-26-R-0001_prime_proposal.pdf
        # Config names look like: N00164-26-R-0001_prime_config.json
        parts = filename.rsplit("_", 1)
        prefix = parts[0] if len(parts) > 1 else filename.replace(".pdf", "")
        
        config_path = proposals_dir / f"{prefix}_config.json"
        
        # Fallback to match_config if direct config is missing
        if not config_path.exists():
            rfp_id = filename.split("_", 1)[0]
            config_path = proposals_dir / f"{rfp_id}_match_config.json"
            
        company_name = "Unknown Company"
        proposal_title = filename.replace("_", " ").replace(".pdf", "").title()
        proposal_subtitle = ""
        proposal_date = ""
        ref = ""
        
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    brand = cfg.get("brand", {})
                    prop = cfg.get("proposal", {})
                    # prepared_for is the client target company
                    company_name = prop.get("prepared_for") or brand.get("company_name") or "Unknown Company"
                    proposal_title = prop.get("title") or proposal_title
                    proposal_subtitle = prop.get("subtitle") or ""
                    proposal_date = prop.get("proposal_date") or ""
                    ref = prop.get("engagement_ref") or ""
            except Exception as e:
                print(f"Error parsing config {config_path}: {e}")
                
        # If date is missing in config, use file modification time
        if not proposal_date:
            mtime = pdf_path.stat().st_mtime
            proposal_date = datetime.fromtimestamp(mtime).strftime("%b %d, %Y")
            
        file_size_bytes = pdf_path.stat().st_size
        if file_size_bytes >= 1024 * 1024:
            file_size = f"{file_size_bytes / (1024 * 1024):.1f} MB"
        else:
            file_size = f"{file_size_bytes / 1024:.0f} KB"
            
        report_record = {
            "filename": filename,
            "company_name": company_name,
            "title": proposal_title,
            "subtitle": proposal_subtitle,
            "date": proposal_date,
            "size": file_size,
            "ref": ref,
            "type": "PDF",
            "filepath": str(pdf_path.resolve())
        }
        
        # Store in MongoDB
        reports_col.update_one(
            {"filename": filename},
            {"$set": report_record},
            upsert=True
        )
        
    # Clean up any records in MongoDB whose physical files no longer exist
    all_stored = list(reports_col.find({}, {"filename": 1}))
    for record in all_stored:
        if record["filename"] not in synced_filenames:
            reports_col.delete_one({"filename": record["filename"]})

@app.get("/api/reports")
def get_reports():
    """Retrieve all reports synced with MongoDB."""
    try:
        sync_reports_with_mongo()
        reports_col = get_collection("reports")
        reports = list(reports_col.find({}, {"_id": 0}))
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/reports/view/{filename}")
def view_report(filename: str):
    """Serve a PDF report inline in the browser."""
    pdf_path = Path("output/pdf") / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(pdf_path, media_type="application/pdf")

@app.get("/api/reports/download/{filename}")
def download_report(filename: str):
    """Force download of a PDF report."""
    pdf_path = Path("output/pdf") / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)

@app.on_event("shutdown")
def shutdown_db_client():
    close_connection()

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
