"""
utils/pdf_generator.py
-----------------------
Generates B2B teaming proposals and product match reports using the
proposal_generator.py layout engine.

Replaces the ReportLab PDF generator to ensure consistent styling,
layout margins, and cover pages.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

class PDFGenerator:
    """
    Generates teaming proposals and product suitability reports using proposal_generator.py
    conforming to the user's branding template.
    """
    def __init__(self, project_root: str = str(Path(__file__).resolve().parent.parent.parent)):
        self.project_root = Path(project_root)

    def calculate_match_scores(self, rfp_data: Dict[str, Any], profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Dynamic weighted rule engine to score all Orbit Avanya products against the RFP.
        Matches features, domain mappings, compliance regulations, and tech stack components.
        """
        raw_tech = rfp_data.get("alignment_matrices", {}).get("technical_capabilities", [])
        if not raw_tech:
            raw_tech = rfp_data.get("identified_components", {}).get("technical", [])
        rfp_tech = []
        for t in raw_tech:
            if isinstance(t, dict):
                rfp_tech.append(t.get("rfp_required_capability", "").lower())
            elif isinstance(t, str):
                rfp_tech.append(t.lower())

        raw_sec = rfp_data.get("alignment_matrices", {}).get("security_compliance", [])
        if not raw_sec:
            raw_sec = rfp_data.get("identified_components", {}).get("security", [])
        rfp_sec = []
        for s in raw_sec:
            if isinstance(s, dict):
                rfp_sec.append(s.get("rfp_security_requirement", "").lower())
            elif isinstance(s, str):
                rfp_sec.append(s.lower())
            
        rfp_desc = rfp_data.get("summary", "").lower() + " " + rfp_data.get("metadata", {}).get("project_title", "").lower()
        
        ranked_products = []
        for p in profiles:
            p_name = p.get("product_name", "")
            p_domain = p.get("industry_domain", "")
            p_features = [f.lower() for f in p.get("key_features", [])]
            p_compliance = [c.lower() for c in p.get("security_and_compliance", [])]
            
            # 1. Keyword Match (30% weight)
            tech_overlap = 0
            for ft in p_features + [p_name.lower(), p_domain.lower()]:
                if any(x in ft for x in rfp_tech) or ft in rfp_desc:
                    tech_overlap += 1
            keyword_score = min(100.0, 45.0 + tech_overlap * 20.0)
            
            # 2. Industry Match (20% weight)
            industry_score = 50.0
            domain_mappings = {
                "Healthcare": ["health", "hms", "medical", "operating", "clinical", "hospital", "6515", "surgical", "or integration"],
                "Education": ["education", "lms", "learning", "school", "course", "academic"],
                "Business": ["website", "wcms", "portal", "content", "mura", "web", "corporate"],
                "AI & Analytics": ["financial", "analytics", "predictive", "dashboard", "modeling", "data", "database"],
                "Enterprise": ["erp", "operations", "enterprise", "resource"],
                "Support": ["support", "helpdesk", "portal", "ticket"],
                "AgriTech": ["agri", "farm", "crop", "agriculture"]
            }
            target_domain_keywords = domain_mappings.get(p_domain, [])
            if any(x in rfp_desc for x in target_domain_keywords):
                industry_score = 100.0
            
            # 3. Pain-Point Match (15% weight)
            pain_overlap = sum(1 for ft in p_features if any(x in ft for x in ["security", "analytics", "automation", "api", "mobile", "insights"]))
            pain_point_score = min(100.0, 50.0 + pain_overlap * 15.0)
            
            # 4. Compliance Match (15% weight)
            sec_overlap = 0
            for std in p_compliance:
                if any(x in std for x in rfp_sec) or any(x in rfp_desc for x in ["6500.6", "appendix c", "hipaa", "security", "privacy", "audit"]):
                    sec_overlap += 1
            compliance_score = min(100.0, 45.0 + sec_overlap * 20.0)
            
            # 5. Technology Stack Match (20% weight)
            tech_score = 85.0  # Orbit Avanya always uses modern react/python
            
            final_score = int(
                (keyword_score * 0.3) +
                (industry_score * 0.2) +
                (pain_point_score * 0.15) +
                (compliance_score * 0.15) +
                (tech_score * 0.2)
            )
            
            ranked_products.append({
                "product_name": p_name,
                "industry_domain": p_domain,
                "score": final_score,
                "features": p.get("key_features", []),
                "compliance": p.get("security_and_compliance", []),
                "tech_stack": p.get("technology_stack", {}),
                "about": p.get("about_text", "")
            })
            
        return sorted(ranked_products, key=lambda x: x["score"], reverse=True)

    def generate_pdf(self, solicitation_number: str) -> Path:
        """
        Generates the Teaming Proposal Word Document (.docx) via proposal_generator.py,
        and converts it to PDF using LibreOffice if available.
        """
        json_path = self.project_root / "output" / "proposals" / f"{solicitation_number}_pitch_data.json"
        
        if not json_path.exists():
            raise FileNotFoundError(f"Proposal JSON data not found at: {json_path}")
            
        with open(json_path, "r", encoding="utf-8") as f:
            proposal = json.load(f)

        from documents.brand_config import get_brand_config, DEFAULT_CONFIDENTIALITY_TEXT, is_mock_solicitation

        brand = get_brand_config()
        confidentiality_text = DEFAULT_CONFIDENTIALITY_TEXT

        is_mock = is_mock_solicitation(solicitation_number)
        title_text = "Teaming & Collaboration Proposal" if is_mock else "Teaming & Subcontracting Proposal"
        safe_ref_suffix = proposal["prime_contractor"].get("company_name", "PARTNER").upper().replace(" ", "_") if is_mock else solicitation_number.upper()
        
        proposal_meta = {
            "title": title_text,
            "subtitle": proposal["metadata"].get("project_title", "IT Services Engagement"),
            "prepared_for": proposal["prime_contractor"].get("company_name", "Prime Contractor"),
            "prepared_by": "Ranjeet Kumar — Founder & CEO, OrbitAvanya Tech LLP (AvanyaEdge)",
            "engagement_ref": f"OAT-CES-2026-{safe_ref_suffix}-PITCH",
            "proposal_date": proposal["proposal_settings"].get("proposal_date", datetime.now().strftime("%B %d, %Y")),
            "validity": "90 days from proposal date",
            "confidentiality_text": confidentiality_text
        }

        sections_list = []

        # Executive Summary
        exec_blocks = []
        narrative = proposal.get("pitch_outreach", {}).get("narrative", "")
        if narrative:
            for p_text in narrative.split("\n\n"):
                p_text = p_text.strip()
                if p_text:
                    exec_blocks.append({"type": "paragraph", "text": p_text})
        else:
            exec_blocks.append({
                "type": "paragraph",
                "text": "OrbitAvanya Tech LLP is pleased to present this teaming proposal as a subcontractor partner."
            })

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

        # Section 2: Requirement Alignment Matrices
        align_blocks = []
        align_text = (
            "The following tables demonstrate the alignment between the strategic project requirements and our product capabilities."
            if is_mock else
            "The following tables demonstrate the alignment between the RFP solicitation requirements and our product capabilities."
        )
        align_blocks.append({
            "type": "paragraph",
            "text": align_text
        })

        tech_aligns = proposal.get("alignment_matrices", {}).get("technical_capabilities", [])
        if tech_aligns:
            align_title = "Project Capability Matrix" if is_mock else "Technical Capability Matrix"
            align_blocks.append({"type": "subheading", "text": align_title})
            headers = (
                ["Project Requirement", "Our Matched Capability", "How It Aligns"]
                if is_mock else
                ["RFP Required Capability", "Our Matched Capability", "How It Aligns"]
            )
            rows = []
            for item in tech_aligns:
                rows.append([
                    item.get("rfp_required_capability", ""),
                    item.get("our_matched_capability", ""),
                    item.get("how_it_aligns", "")
                ])
            align_blocks.append({
                "type": "table",
                "headers": headers,
                "rows": rows,
                "col_widths": [2.2, 2.3, 2.5]
            })

        sec_aligns = proposal.get("alignment_matrices", {}).get("security_compliance", [])
        if sec_aligns:
            sec_title = "Security & Compliance Focus Area" if is_mock else "Security & Compliance Matrix"
            align_blocks.append({"type": "subheading", "text": sec_title})
            headers = (
                ["Security Requirement", "Our Matched Standard", "How It Aligns"]
                if is_mock else
                ["RFP Security Requirement", "Our Matched Standard", "How It Aligns"]
            )
            rows = []
            for item in sec_aligns:
                rows.append([
                    item.get("rfp_security_requirement", ""),
                    item.get("our_matched_standard", ""),
                    item.get("how_it_aligns", "")
                ])
            align_blocks.append({
                "type": "table",
                "headers": headers,
                "rows": rows,
                "col_widths": [2.2, 2.3, 2.5]
            })

        sections_list.append({
            "title": "Requirement Alignment",
            "page_break_before": False,
            "blocks": align_blocks
        })

        # Section 3: Work Share Breakdown
        share_blocks = []
        share_text = (
            f"OrbitAvanya Tech LLP proposes a work share allocation of {proposal['proposal_settings'].get('proposed_workshare_pct', 15.0)}% of the total project scope. The breakdown is structured as follows:"
            if is_mock else
            f"OrbitAvanya Tech LLP proposes a work share allocation of {proposal['proposal_settings'].get('proposed_workshare_pct', 15.0)}% of the total contract value. The breakdown is structured as follows:"
        )
        share_blocks.append({
            "type": "paragraph",
            "text": share_text
        })

        work_share = proposal.get("alignment_matrices", {}).get("subcontractor_work_share_breakdown", [])
        if work_share:
            headers = ["Proposed Task Area", "Scope Percentage"]
            rows = []
            for item in work_share:
                rows.append([item.get("task", ""), f"{item.get('proposed_share', '')}%"])
            share_blocks.append({
                "type": "table",
                "headers": headers,
                "rows": rows,
                "col_widths": [4.5, 2.2]
            })

        sections_list.append({
            "title": "Proposed Work Share",
            "page_break_before": False,
            "blocks": share_blocks
        })

        # Section 4: Outreach & Contacts
        outreach_blocks = []
        outreach_blocks.append({"type": "subheading", "text": "Strategic Contact Point"})
        outreach_blocks.append({
            "type": "paragraph",
            "text": f"Subject: {proposal.get('pitch_outreach', {}).get('subject', 'Teaming Partnership Inquiry')}"
        })
        outreach_blocks.append({
            "type": "paragraph",
            "text": f"Email Text:\n{proposal.get('pitch_outreach', {}).get('outreach_email', '') or proposal.get('pitch_outreach', {}).get('narrative', '')}"
        })

        sections_list.append({
            "title": "Strategic Outreach",
            "page_break_before": False,
            "blocks": outreach_blocks
        })

        cfg = {
            "brand": brand,
            "proposal": proposal_meta,
            "toc": {"heading": "Content"},
            "sections": sections_list
        }

        # Save config
        config_path = self.project_root / "output" / "proposals" / f"{solicitation_number}_pitch_config.json"
        with open(config_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)

        # Generate docx
        from scripts import proposal_generator
        output_base = self.project_root / "output" / "pdf" / f"{solicitation_number}_pitch_proposal"
        docx_path = str(output_base) + ".docx"
        proposal_generator.generate(cfg, docx_path)
        logger.info(f"DOCX pitch proposal saved: {docx_path}")

        # Convert to PDF
        try:
            pdf_path = proposal_generator.convert_to_pdf(docx_path)
            return Path(pdf_path)
        except Exception as e:
            logger.warning(f"LibreOffice PDF conversion failed: {e}. Fallback to docx.")
            return Path(docx_path)

    def generate_product_match_report(self, solicitation_number: str) -> Path:
        """
        Generates the 5-page Product Suitability and Match Report Word Document (.docx)
        via proposal_generator.py, and converts it to PDF using LibreOffice if available.
        """
        json_path = self.project_root / "output" / "proposals" / f"{solicitation_number}_pitch_data.json"
        
        if not json_path.exists():
            raise FileNotFoundError(f"Proposal JSON data not found at: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            proposal = json.load(f)

        profiles_json_path = self.project_root / "private" / "orbit_avanya_detailed_profiles.json"
        if not profiles_json_path.exists():
            raise FileNotFoundError(f"Product profiles JSON not found at: {profiles_json_path}")
            
        with open(profiles_json_path, "r", encoding="utf-8") as f:
            profiles = json.load(f)

        # Run dynamic scoring rule-engine
        ranked_products = self.calculate_match_scores(proposal, profiles)
        top_product = ranked_products[0]

        brand = {
            "company_name": "OrbitAvanya Tech LLP",
            "company_short": "OrbitAvanya",
            "logo_path": "assets/logo.png",
            "cover_graphic_path": "assets/cover_graphic.png",
            "body_font": "Fira Sans Light",
            "heading_font": "Fira Sans SemiBold",
            "accent_color": "1F3864",
            "muted_color": "595959",
            "address_line1": "13352 Kettle Camp Rd",
            "address_line2": "Frisco, Texas 75035",
            "phone": "+917021950643",
            "website": "www.orbitavanyatech.com"
        }

        confidentiality_text = (
            "This document contains confidential information of OrbitAvanya Tech LLP and its affiliates and/or licensors "
            "(“OrbitAvanya”), which may include trade secrets, proprietary methodology, and business information. "
            "The recipient acknowledges that this information has been developed by OrbitAvanya as valuable trade secrets "
            "and shall remain its exclusive property, to be disclosed only to persons who have a need to know. "
            "The recipient agrees not to copy or reproduce any information supplied herein without prior written permission "
            "from an authorized representative of OrbitAvanya.\n\n"
            "Reciprocally, OrbitAvanya acknowledges that information shared by the recipient during proposal review "
            "and any subsequent engagement constitutes confidential information of the recipient, and agrees to protect "
            "it to the same standard and to use it solely for the purposes of the engagement contemplated herein."
        )

        is_mock = (
            not solicitation_number 
            or solicitation_number.lower() in ("unknown", "none", "n/a")
            or solicitation_number.lower().startswith("mock")
        )
        subtitle_text = f"Automated Capability Evaluation for {proposal['prime_contractor'].get('company_name', 'Teaming Engagement')}" if is_mock else f"Automated Capability Evaluation for {solicitation_number}"
        safe_ref_suffix = proposal["prime_contractor"].get("company_name", "PARTNER").upper().replace(" ", "_") if is_mock else solicitation_number.upper()

        proposal_meta = {
            "title": "Product Suitability & Match Report",
            "subtitle": subtitle_text,
            "prepared_for": proposal["prime_contractor"].get("company_name", "Prime Contractor"),
            "prepared_by": "Ranjeet Kumar — Founder & CEO, OrbitAvanya Tech LLP (AvanyaEdge)",
            "engagement_ref": f"OAT-CES-2026-{safe_ref_suffix}-MATCH",
            "proposal_date": datetime.now().strftime("%B %d, %Y"),
            "validity": "90 days from proposal date",
            "confidentiality_text": confidentiality_text
        }

        sections_list = []

        # Executive Suitability Summary
        eval_blocks = []
        eval_text = (
            "OrbitAvanya Tech LLP has evaluated our product catalog against the functional, technical, and compliance requirements extracted from the target project."
            if is_mock else
            "OrbitAvanya Tech LLP has evaluated our product catalog against the functional, technical, and compliance requirements extracted from the solicitation."
        )
        eval_blocks.append({
            "type": "paragraph",
            "text": eval_text
        })
        eval_blocks.append({"type": "subheading", "text": "Top Matched Offering"})
        eval_blocks.append({
            "type": "paragraph",
            "text": f"The top-ranked matched product is {top_product['product_name']} within the {top_product['industry_domain']} industry domain, scoring a suitability rank of {top_product['score']}%."
        })

        sections_list.append({
            "title": "Evaluation Summary",
            "page_break_before": True,
            "blocks": eval_blocks
        })

        # Suitability Leaderboard
        lead_blocks = []
        lead_text = (
            "The table below lists our product catalog sorted by suitability match score against the project requirements:"
            if is_mock else
            "The table below lists our product catalog sorted by suitability match score against the RFP requirements:"
        )
        lead_blocks.append({
            "type": "paragraph",
            "text": lead_text
        })

        headers = ["Product Offering", "Industry Domain", "Suitability Score"]
        rows = []
        for item in ranked_products:
            rows.append([item["product_name"], item["industry_domain"], f"{item['score']}%"])
        
        lead_blocks.append({
            "type": "table",
            "headers": headers,
            "rows": rows,
            "col_widths": [3.0, 2.5, 1.5]
        })

        sections_list.append({
            "title": "Product Match Leaderboard",
            "page_break_before": False,
            "blocks": lead_blocks
        })

        # Top Product Profiles
        profile_blocks = []
        profile_blocks.append({
            "type": "paragraph",
            "text": "Below are the detailed profiles for the top matched product offerings evaluated for this engagement:"
        })

        for item in ranked_products[:4]:
            profile_blocks.append({"type": "subheading", "text": f"{item['product_name']} ({item['industry_domain']} - Score: {item['score']}%)"})
            profile_blocks.append({"type": "paragraph", "text": item["about"]})
            profile_blocks.append({"type": "bullets", "items": item["features"][:5]})
            
        sections_list.append({
            "title": "Top Product Profiles",
            "page_break_before": False,
            "blocks": profile_blocks
        })

        cfg = {
            "brand": brand,
            "proposal": proposal_meta,
            "toc": {"heading": "Content"},
            "sections": sections_list
        }

        # Save config
        config_path = self.project_root / "output" / "proposals" / f"{solicitation_number}_match_config.json"
        with open(config_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)

        # Generate docx
        from scripts import proposal_generator
        output_base = self.project_root / "output" / "pdf" / f"{solicitation_number}_product_match_report"
        docx_path = str(output_base) + ".docx"
        proposal_generator.generate(cfg, docx_path)
        logger.info(f"DOCX product match report saved: {docx_path}")

        # Convert to PDF
        try:
            pdf_path = proposal_generator.convert_to_pdf(docx_path)
            return Path(pdf_path)
        except Exception as e:
            logger.warning(f"LibreOffice PDF conversion failed: {e}. Fallback to docx.")
            return Path(docx_path)
