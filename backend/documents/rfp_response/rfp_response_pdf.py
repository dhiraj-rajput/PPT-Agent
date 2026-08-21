"""
utils/rfp_response_pdf.py
--------------------------
Generates DOCX proposals using the proposal_generator.py layout engine,
and renders them to PDF using LibreOffice.

Replaces ReportLab PDF generation to perfectly match the Word document structure
and branding template requirements.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def generate_rfp_response_pdf(
    solicitation_number: str,
    mode: str,
    sections: dict[str, Any],
    agency_name: str = "Issuing Agency",
    proposal_title: str = "Technical & Management Proposal",
    winner_name: str | None = None,
    project_root: str | None = None,
) -> str:
    """
    Generates a DOCX using proposal_generator.py and then converts it to PDF via LibreOffice.
    """
    root_path = Path(project_root) if project_root else Path(__file__).resolve().parent.parent.parent
    from documents.brand_config import (
        DEFAULT_CONFIDENTIALITY_TEXT,
        get_brand_config,
        is_mock_solicitation,
    )

    is_mock = is_mock_solicitation(solicitation_number)

    # 1. Construct the config dictionary (cfg)
    brand = get_brand_config()
    confidentiality_text = DEFAULT_CONFIDENTIALITY_TEXT
    
    # Format current date
    proposal_date = datetime.now().strftime("%B %d, %Y")
    
    if mode == "subcontract":
        doc_title = "Teaming & Collaboration Proposal" if is_mock else "Teaming Proposal"
    elif mode == "partnership":
        doc_title = "Partnership Proposal"
    else:
        doc_title = "Technical Proposal" if is_mock else "RFP Response Proposal"

    safe_ref_suffix = (winner_name or "PARTNER").upper().replace(" ", "_") if is_mock else solicitation_number.upper()
    proposal = {
        "title": doc_title,
        "subtitle": proposal_title,
        "prepared_for": winner_name if mode == "subcontract" or mode == "partnership" else agency_name,
        "prepared_by": "Ranjeet Kumar — Founder & CEO, OrbitAvanya Tech LLP (AvanyaEdge)",
        "engagement_ref": f"OAT-CES-2026-{safe_ref_suffix}-FULL",
        "proposal_date": proposal_date,
        "validity": "90 days from proposal date",
        "confidentiality_text": confidentiality_text
    }
    
    # Let's map sections
    sections_list = []
    
    # Section 1: Executive Summary
    exec_blocks = []
    exec_summary_text = sections.get("executive_summary", "")
    for p_text in exec_summary_text.split("\n\n"):
        p_text = p_text.strip()
        if p_text:
            exec_blocks.append({"type": "paragraph", "text": p_text})
            
    key_highlights = sections.get("key_highlights", [])
    if key_highlights:
        exec_blocks.append({"type": "subheading", "text": "Key Highlights"})
        exec_blocks.append({"type": "bullets", "items": key_highlights})
        
    exec_blocks.append({
        "type": "signature",
        "name": "Ranjeet Kumar Singh",
        "title": "Founder & CEO",
        "company": "OrbitAvanya Tech LLP (AvanyaEdge)"
    })
    
    sections_list.append({
        "title": "Executive Summary",
        "page_break_before": True,
        "blocks": exec_blocks
    })
    
    # Section 2: Engagement Summary / Strategic Context
    strat_blocks = []
    strat_intro = sections.get("strategic_context_intro", "")
    if strat_intro:
        strat_blocks.append({"type": "paragraph", "text": strat_intro})
        
    findings = sections.get("findings", [])
    for i, finding in enumerate(findings, 1):
        f_title = finding.get("title", f"Finding {i}")
        f_body = finding.get("body", "")
        f_bullets = finding.get("bullets", [])
        
        strat_blocks.append({"type": "subheading", "text": f"Finding {i} · {f_title}"})
        if f_body:
            strat_blocks.append({"type": "paragraph", "text": f_body})
        if f_bullets:
            strat_blocks.append({"type": "bullets", "items": f_bullets})
            
    sections_list.append({
        "title": "Strategic Context",
        "page_break_before": False,
        "blocks": strat_blocks
    })
    
    # Section 3: Scope of Work
    scope_blocks = []
    scope_intro = sections.get("scope_intro", "")
    if scope_intro:
        scope_blocks.append({"type": "paragraph", "text": scope_intro})
        
    deliverables = sections.get("deliverables", [])
    if deliverables:
        scope_blocks.append({"type": "subheading", "text": "Deliverables"})
        scope_blocks.append({"type": "bullets", "items": deliverables})
        
    tech_alignments = sections.get("technical_alignment", [])
    if tech_alignments:
        align_title = "Project Requirements Alignment" if is_mock else "Technical Requirements Alignment"
        scope_blocks.append({"type": "subheading", "text": align_title})
        headers = (
            ["Project Requirement", "Our Solution", "Alignment"]
            if is_mock else
            ["RFP Requirement", "Our Solution", "Alignment"]
        ) if mode != "partnership" else ["Partner Gap / Need", "OrbitAvanya Solution", "Synergy"]
        rows = []
        for a in tech_alignments:
            rows.append([
                a.get("requirement", ""),
                a.get("solution", ""),
                a.get("alignment", "✓ Full")
            ])
        scope_blocks.append({
            "type": "table",
            "headers": headers,
            "rows": rows,
            "col_widths": [2.3, 2.9, 1.5]
        })
        
    sections_list.append({
        "title": "Scope of Work",
        "page_break_before": False,
        "blocks": scope_blocks
    })
    
    # Section 4: Our Proposed Solution
    sol_blocks = []
    proposed_sol = sections.get("proposed_solution", "")
    if proposed_sol:
        for p_text in proposed_sol.split("\n\n"):
            p_text = p_text.strip()
            if p_text:
                sol_blocks.append({"type": "paragraph", "text": p_text})
                
    capabilities = sections.get("capabilities", [])
    if capabilities:
        sol_blocks.append({"type": "subheading", "text": "Core Capabilities"})
        headers = ["Capability", "Description"]
        rows = []
        for c in capabilities:
            rows.append([c.get("name", ""), c.get("description", "")])
        sol_blocks.append({
            "type": "table",
            "headers": headers,
            "rows": rows,
            "col_widths": [2.5, 4.2]
        })
        
    tech_stack = sections.get("tech_stack", [])
    if tech_stack:
        sol_blocks.append({"type": "subheading", "text": "Technology Stack"})
        sol_blocks.append({"type": "bullets", "items": tech_stack})
        
    sections_list.append({
        "title": "Our Proposed Solution",
        "page_break_before": False,
        "blocks": sol_blocks
    })
    
    # Section 5: Implementation Timeline
    time_blocks = []
    timeline_intro = sections.get("timeline_intro", "")
    if timeline_intro:
        time_blocks.append({"type": "paragraph", "text": timeline_intro})
        
    phases = sections.get("phases", [])
    if phases:
        time_blocks.append({"type": "subheading", "text": "Engagement Timeline"})
        headers = ["Phase", "Duration", "Focus Area", "Deliverables"]
        rows = []
        for p in phases:
            rows.append([
                p.get("phase", ""),
                p.get("duration", ""),
                p.get("focus", ""),
                p.get("deliverables", "")
            ])
        time_blocks.append({
            "type": "table",
            "headers": headers,
            "rows": rows,
            "col_widths": [1.0, 1.1, 2.2, 2.4]
        })
        
    total_duration = sections.get("total_duration", "8–10 Weeks")
    time_blocks.append({"type": "paragraph", "text": f"Total Estimated Duration: {total_duration}"})
    
    sections_list.append({
        "title": "Implementation Timeline" if mode != "partnership" else "Partnership Roadmap",
        "page_break_before": False,
        "blocks": time_blocks
    })
    
    # Section 6: Your Investment
    invest_blocks = []
    invest_intro = sections.get("investment_intro", "")
    if invest_intro:
        invest_blocks.append({"type": "paragraph", "text": invest_intro})
        
    pricing = sections.get("pricing", [])
    if pricing:
        headers = ["Item / Deliverable", "Unit", "Qty", "Unit Price", "Total"]
        rows = []
        for p in pricing:
            rows.append([
                p.get("item", ""),
                p.get("unit", "Fixed"),
                str(p.get("qty", "1")),
                p.get("unit_price", "—"),
                p.get("total", "—")
            ])
        invest_blocks.append({
            "type": "table",
            "headers": headers,
            "rows": rows,
            "col_widths": [2.8, 0.9, 0.65, 1.15, 1.2]
        })
        
    sla_terms = sections.get("sla_terms", [])
    if sla_terms:
        invest_blocks.append({"type": "subheading", "text": "Service Level Agreement & Terms"})
        invest_blocks.append({"type": "bullets", "items": sla_terms})
        
    workshare = sections.get("workshare_pct")
    if workshare and mode == "subcontract":
        invest_blocks.append({"type": "spacer"})
        workshare_desc = (
            f"Proposed Work Share: OrbitAvanya Tech LLP proposes to assume {workshare}% of the total project scope as our teaming work share."
            if is_mock else
            f"Proposed Work Share: OrbitAvanya Tech LLP proposes to assume {workshare}% of the total contract value as our subcontract work share."
        )
        invest_blocks.append({
            "type": "paragraph",
            "text": workshare_desc
        })
        
    sections_list.append({
        "title": "Your Investment",
        "page_break_before": False,
        "blocks": invest_blocks
    })
    
    # Section 7: Company Profile
    profile_blocks = []
    profile_blocks.append({
        "type": "paragraph",
        "text": (
            "OrbitAvanya Tech LLP (AvanyaEdge) is a technology services firm specializing in enterprise software "
            "development, digital transformation, e-governance platforms, and AI/ML solutions. Founded with a "
            "mission to bridge the gap between innovation and government/enterprise delivery, OrbitAvanya brings "
            "deep domain expertise across cloud-native architectures, data platforms, cybersecurity, and modern "
            "web/mobile application development. Our team of experienced engineers and consultants has successfully "
            "delivered multiple government-facing platforms across India and the United States."
        )
    })
    profile_blocks.append({
        "type": "table",
        "headers": ["Profile Detail", "Value"],
        "rows": [
            ["Company Name", "OrbitAvanya Tech LLP"],
            ["Type", "Limited Liability Partnership (LLP)"],
            ["Headquarters", "Frisco, Texas 75035, USA"],
            ["India Office", "Pune, Maharashtra, India"],
            ["Website", "www.orbitavanyatech.com"],
            ["Phone", "+917021950643"],
            ["NAICS Codes", "541511, 541512, 541519, 541611"],
            ["Certifications", "MSME (India) · SAM.gov Registered"]
        ],
        "col_widths": [2.4, 4.3]
    })
    
    sections_list.append({
        "title": "Company Profile",
        "page_break_before": True,
        "blocks": profile_blocks
    })
    
    # Section 8: Appendix
    app_blocks = []
    past_perf = sections.get("past_performance", [])
    if past_perf:
        app_blocks.append({"type": "subheading", "text": "Appendix A — Past Performance"})
        headers = ["Project", "Client", "Period", "Relevance"]
        rows = []
        for pp in past_perf:
            rows.append([
                pp.get("project", ""),
                pp.get("client", ""),
                pp.get("period", ""),
                pp.get("relevance", "")
            ])
        app_blocks.append({
            "type": "table",
            "headers": headers,
            "rows": rows,
            "col_widths": [2.2, 1.8, 1.0, 2.0]
        })
        
    app_blocks.append({"type": "subheading", "text": "Appendix B — Team & Leadership"})
    app_blocks.append({
        "type": "paragraph",
        "text": (
            "OrbitAvanya Tech LLP's leadership team comprises professionals with extensive backgrounds in "
            "enterprise software delivery, cloud architecture, AI/ML systems, and government program management. "
            "Full team profiles and resumes are available upon request."
        )
    })
    
    sections_list.append({
        "title": "Appendix",
        "page_break_before": False,
        "blocks": app_blocks
    })
    
    cfg = {
        "brand": brand,
        "proposal": proposal,
        "toc": {"heading": "Content"},
        "sections": sections_list
    }
    
    # 2. Save config to output/proposals/
    proposals_dir = root_path / "output" / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    config_path = proposals_dir / f"{solicitation_number}_{mode}_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    logger.info(f"[RFPResponsePDF] Configuration saved to: {config_path}")
    
    # 3. Generate docx document via proposal_generator
    import importlib
    try:
        from backend.scripts import proposal_generator
    except ImportError:
        proposal_generator = importlib.import_module("scripts.proposal_generator")
    
    if mode == "prime":
        suffix = "prime_proposal"
    elif mode == "subcontract":
        suffix = "subcontract_proposal"
    else:
        suffix = "partnership_proposal"
    output_base = root_path / "output" / "pdf" / f"{solicitation_number}_{suffix}"
    output_base.parent.mkdir(parents=True, exist_ok=True)
    
    docx_path = str(output_base) + ".docx"
    pdf_path = str(output_base) + ".pdf"
    
    proposal_generator.generate(cfg, docx_path)
    logger.info(f"[RFPResponsePDF] Word document created at: {docx_path}")
    
    # 4. Convert to PDF using Word COM on Windows or LibreOffice fallback
    converted = False
    
    if sys.platform == "win32":
        try:
            import comtypes.client
            logger.info("[RFPResponsePDF] Attempting Word COM conversion to PDF...")
            word = comtypes.client.CreateObject('Word.Application')
            word.Visible = False
            word.DisplayAlerts = 0 # Suppress popups
            try:
                doc = word.Documents.Open(os.path.abspath(docx_path))
                doc.SaveAs(os.path.abspath(pdf_path), FileFormat=17) # 17 is wdFormatPDF
                doc.Close()
                logger.info(f"[RFPResponsePDF] PDF created via Word COM: {pdf_path}")
                converted = True
            finally:
                word.Quit()
        except Exception as e:
            logger.warning(f"[RFPResponsePDF] Word COM conversion failed: {e}. Trying LibreOffice...")
    if not converted:
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            mac_soffice = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
            common_paths = [
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                mac_soffice,
                "/usr/bin/soffice",
                "/usr/bin/libreoffice",
            ]
            for p in common_paths:
                if os.path.exists(p):
                    soffice = p
                    break
        if soffice:
            try:
                logger.info(f"[RFPResponsePDF] Attempting LibreOffice conversion to PDF using {soffice}...")
                outdir = str(output_base.parent)
                subprocess.run(
                    [soffice, "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path],
                    check=True, capture_output=True,
                )
                generated_pdf = output_base.parent / (output_base.stem + ".pdf")
                if generated_pdf.exists() and str(generated_pdf.resolve()) != os.path.abspath(pdf_path):
                    shutil.move(str(generated_pdf), os.path.abspath(pdf_path))
                logger.info(f"[RFPResponsePDF] PDF created via LibreOffice: {pdf_path}")
                converted = True
            except Exception as e:
                logger.error(f"[RFPResponsePDF] LibreOffice conversion failed: {e}")

    if converted:
        # Clean up docx file as requested ("instead of docx convert them after creating to the pdf")
        try:
            os.unlink(docx_path)
            logger.info(f"[RFPResponsePDF] Cleaned up temporary DOCX file: {docx_path}")
        except Exception as e:
            logger.warning(f"[RFPResponsePDF] Could not delete temporary DOCX: {e}")
        return pdf_path
    else:
        logger.warning("[RFPResponsePDF] All PDF conversion methods failed. Returning DOCX path.")
        return docx_path
