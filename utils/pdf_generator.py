import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.pdfgen import canvas

from utils.helpers import setup_logger

logger = setup_logger(__name__)

# Color Palette (Replicating the DesignLights Consortium styling guidelines)
PRIMARY_COLOR = colors.HexColor("#0f172a")      # Deep Navy Blue
SECONDARY_COLOR = colors.HexColor("#d97706")    # Gold / Amber Highlight Line
CHARCOAL_COLOR = colors.HexColor("#334155")     # Premium Charcoal Body Text
LIGHT_GREY = colors.HexColor("#f8fafc")         # Alternating table rows background
BORDER_GREY = colors.HexColor("#cbd5e1")        # Thin line separators
CALLOUT_BG = colors.HexColor("#fafaf9")         # Warm stone card background
WHITE = colors.HexColor("#ffffff")

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute total pages and draw headers/footers
    replicating the professional formatting guidelines.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        getattr(self, "_startPage")()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(CHARCOAL_COLOR)
        
        # Page 1 is the cover sheet
        if getattr(self, "_pageNumber", 1) > 1:
            # Header block
            self.drawString(54, 750, "CONFIDENTIAL B2B TEAMING PROPOSAL")
            sol_num = getattr(self, "sol_num", "N/A")
            self.drawRightString(558, 750, f"RFP Reference: {sol_num}")
            self.setStrokeColor(BORDER_GREY)
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)
            
            # Footer block
            page_text = f"Page {getattr(self, '_pageNumber', 1)} of {page_count}"
            self.drawRightString(558, 40, page_text)
            self.drawString(54, 40, "Confidential - Prepared by Orbit Avanya LLP for Prime Review Only")
            self.line(54, 52, 558, 52)
            
        self.restoreState()

def make_canvas(sol_num: str):
    class CustomNumberedCanvas(NumberedCanvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.sol_num = sol_num
    return CustomNumberedCanvas

class PDFGenerator:
    """
    Generates a highly detailed, professional, human-designed 10+ page subcontracting
    proposal matching the structural format of Orbit_Avanya_DLC_Detailed_Proposal.pdf.
    Also compiles the 5-page Product Match Report PDF.
    """
    def __init__(self, project_root: str = "E:/MIT WPU/MIT WPU Subjects/7th_Sem/Orbit/PPT-Agent"):
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
            p_tech_stack = p.get("technology_stack", {})
            
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
            
            # 5. Budget Fit (10% weight)
            budget_score = 85.0
            
            # 6. Technology Match (10% weight)
            stack_overlap = 0
            for layer, tech_list in p_tech_stack.items():
                for t in tech_list:
                    if t.lower() in rfp_desc:
                        stack_overlap += 1
            tech_stack_score = min(100.0, 60.0 + stack_overlap * 10.0)
            
            # Compute weighted overall score
            overall_score = (
                (keyword_score * 0.3) +
                (industry_score * 0.2) +
                (pain_point_score * 0.15) +
                (compliance_score * 0.15) +
                (budget_score * 0.10) +
                (tech_stack_score * 0.10)
            )
            
            ranked_products.append({
                "product_name": p_name,
                "industry_domain": p_domain,
                "overall_score": overall_score,
                "keyword_score": keyword_score,
                "industry_score": industry_score,
                "pain_point_score": pain_point_score,
                "compliance_score": compliance_score,
                "budget_score": budget_score,
                "tech_stack_score": tech_stack_score,
                "features": p_features,
                "compliance_standards": p_compliance,
                "about_text": p.get("about_text", "")
            })
            
        ranked_products.sort(key=lambda x: x["overall_score"], reverse=True)
        return ranked_products

    def generate_pdf(self, solicitation_number: str) -> Path:
        json_path = self.project_root / "output" / "proposals" / f"{solicitation_number}_pitch_data.json"
        pdf_path = self.project_root / "output" / "pdf" / f"{solicitation_number}_pitch_proposal.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not json_path.exists():
            raise FileNotFoundError(f"Proposal JSON data not found at: {json_path}")
            
        logger.info(f"Generating detailed PDF proposal for: {solicitation_number}")
        
        with open(json_path, "r", encoding="utf-8") as f:
            proposal = json.load(f)

        # Document margins set to 0.75" on sides, 1.0" top/bottom
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=72,
            bottomMargin=72
        )
        
        styles = getSampleStyleSheet()
        
        # Typography / Styles (Upgraded for premium human-designed layout feel)
        cover_pre_style = ParagraphStyle(
            "CoverPre", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=10, leading=12, textColor=SECONDARY_COLOR, spaceAfter=6
        )
        cover_title_style = ParagraphStyle(
            "CoverTitle", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=30, leading=36, textColor=PRIMARY_COLOR, spaceAfter=12
        )
        cover_sub_style = ParagraphStyle(
            "CoverSub", parent=styles["Normal"], fontName="Helvetica",
            fontSize=11, leading=16, textColor=CHARCOAL_COLOR, spaceAfter=30
        )
        h1_style = ParagraphStyle(
            "Heading1", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, textColor=PRIMARY_COLOR, spaceBefore=24, spaceAfter=4,
            keepWithNext=True
        )
        h2_style = ParagraphStyle(
            "Heading2", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=12.5, leading=16, textColor=SECONDARY_COLOR, spaceBefore=14, spaceAfter=6,
            keepWithNext=True
        )
        body_style = ParagraphStyle(
            "Body", parent=styles["Normal"], fontName="Helvetica",
            fontSize=10, leading=15.5, textColor=CHARCOAL_COLOR, spaceAfter=10
        )
        th_style = ParagraphStyle(
            "TableHeader", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=9.5, leading=12, textColor=WHITE
        )
        td_style = ParagraphStyle(
            "TableCell", parent=styles["Normal"], fontName="Helvetica",
            fontSize=9, leading=13.5, textColor=CHARCOAL_COLOR
        )
        td_bold_style = ParagraphStyle(
            "TableCellBold", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=9, leading=13.5, textColor=PRIMARY_COLOR
        )

        story = []

        def add_gold_divider():
            story.append(Spacer(1, 4))
            tbl = Table([[""]], colWidths=[504])
            tbl.setStyle(TableStyle([
                ('LINEABOVE', (0,0), (-1,-1), 1.5, SECONDARY_COLOR),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 12))

        # ------------------------------------------------------------------
        # PAGE 1: COVER SHEET (Redesigned for Premium borderless list layout)
        # ------------------------------------------------------------------
        story.append(Spacer(1, 1.0 * inch))
        story.append(Paragraph("CONFIDENTIAL PARTNERSHIP PROPOSAL", cover_pre_style))
        story.append(Paragraph("Subcontract Teaming & Technology Proposal", cover_title_style))
        
        # Gold divider underneath title
        cover_divider = Table([[""]], colWidths=[504])
        cover_divider.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,-1), 2.5, SECONDARY_COLOR),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(cover_divider)
        story.append(Spacer(1, 20))
        
        story.append(Paragraph(
            f"Strategic technology integration proposal to support the execution of solicitation {solicitation_number}.",
            cover_sub_style
        ))
        
        # Meta snapshot left-aligned borderless grid (mimicking DLC Cover page)
        meta_data = [
            [Paragraph("Prepared For:", td_bold_style), Paragraph(proposal["prime_contractor"]["company_name"], td_style)],
            [Paragraph("Prepared By:", td_bold_style), Paragraph(proposal["subcontractor"]["company_name"], td_style)],
            [Paragraph("Target RFP / Project:", td_bold_style), Paragraph(proposal["metadata"]["project_title"], td_style)],
            [Paragraph("Issuing Agency:", td_bold_style), Paragraph(proposal["metadata"]["issuing_agency"], td_style)],
            [Paragraph("Submission Date:", td_bold_style), Paragraph(datetime.now().strftime("%d %B %Y"), td_style)],
            [Paragraph("Reference Number:", td_bold_style), Paragraph(f"OA-{solicitation_number}-2026-001", td_style)]
        ]
        meta_table = Table(meta_data, colWidths=[120, 384])
        meta_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(meta_table)
        
        story.append(Spacer(1, 1.8 * inch))
        
        # Lower third border line and confidentiality disclaimer
        disclaimer_divider = Table([[""]], colWidths=[504])
        disclaimer_divider.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(disclaimer_divider)
        story.append(Spacer(1, 10))
        
        story.append(Paragraph(
            "<b>Confidentiality Statement:</b> This proposal contains confidential and proprietary information prepared "
            "exclusively for the prime contractor evaluation committee. It may not be reproduced or disclosed to third parties "
            "without written consent from Orbit Avanya LLP.", td_style
        ))
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 2: LETTER TO EVALUATION COMMITTEE
        # ------------------------------------------------------------------
        story.append(Paragraph("Letter to the Evaluation Committee", h1_style))
        add_gold_divider()
        
        p1 = (
            f"Dear Teaming Partner Evaluation Committee at <b>{proposal['prime_contractor']['company_name']}</b>,<br/><br/>"
            f"Thank you for the opportunity to respond and offer a strategic partnership for solicitation <b>{solicitation_number}</b> "
            f"({proposal['metadata']['project_title']}). We recognize that executing this contract requires high-performance technology, "
            f"secure database integration, and compliance configurations that must fit seamlessly into the prime contractor's delivery framework. "
            f"Orbit Avanya LLP operates at the intersection of enterprise software delivery and federal cybersecurity directives, making us an ideal subcontracting partner."
        )
        story.append(Paragraph(p1, body_style))
        
        p2 = (
            f"After a detailed review of the solicitation objectives, we propose a technology alignment built around our "
            f"<b>{proposal['subcontractor']['product_name']}</b> platform. We propose taking on a **{proposal['proposal_settings']['proposed_workshare_pct']}%** "
            f"subcontracting work share, specifically focusing on custom dashboards development, database performance optimization, API systems integration, "
            f"and compliance enforcement. This partnership allows you to leverage pre-tested visual analytics and secure schemas out-of-the-box, "
            f"significantly mitigating delivery timelines and program execution risk."
        )
        story.append(Paragraph(p2, body_style))
        
        p3 = "Sincerely,"
        story.append(Paragraph(p3, body_style))
        story.append(Spacer(1, 30))
        
        # Signature block with clean signing lines
        sig_data = [
            [
                Paragraph("_______________________<br/><b>Chief Executive Officer</b><br/>Orbit Avanya LLP", td_style),
                Paragraph("_______________________<br/><b>Head of Delivery</b><br/>Orbit Avanya LLP", td_style),
                Paragraph("_______________________<br/><b>Principal Architect</b><br/>Orbit Avanya LLP", td_style)
            ]
        ]
        sig_table = Table(sig_data, colWidths=[168, 168, 168])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(sig_table)
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 3: UNDERSTANDING YOUR BUSINESS
        # ------------------------------------------------------------------
        story.append(Paragraph("Understanding Your Business & Context", h1_style))
        add_gold_divider()
        story.append(Paragraph("Organization Snapshot", h2_style))
        
        # Borderless side-grid table matching modern design guidelines
        snap_data = [
            [Paragraph("Parameter", th_style), Paragraph("Value / Configuration", th_style)],
            [Paragraph("Issuing Agency", td_bold_style), Paragraph(proposal["metadata"]["issuing_agency"], td_style)],
            [Paragraph("Target Prime Contractor", td_bold_style), Paragraph(proposal["prime_contractor"]["company_name"], td_style)],
            [Paragraph("Product Domain Focus", td_bold_style), Paragraph(proposal["subcontractor"]["industry_domain"], td_style)],
            [Paragraph("Proposed Solution Stack", td_bold_style), Paragraph(proposal["subcontractor"]["product_name"], td_style)],
            [Paragraph("Key Subcontractor Scope", td_bold_style), Paragraph("Visual dashboard telemetry, Postgres/Mongo clustering, and secure API gateways", td_style)]
        ]
        snap_table = Table(snap_data, colWidths=[150, 354])
        snap_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(snap_table)
        story.append(Spacer(1, 15))
        
        story.append(Paragraph("Project Objectives & Context", h2_style))
        ctx_text = (
            f"The issuing agency requires software integration, database design, and visual telemetry support. "
            f"The primary goal of this teaming proposal is to ensure that the prime contractor ({proposal['prime_contractor']['company_name']}) "
            f"can absorb specialized development requirements in database clustering and dashboard reporting without diverting "
            f"their main program management talent. By establishing a clear technical division of labor, the team is positioned "
            f"to qualification-match the agency's evaluation criteria."
        )
        story.append(Paragraph(ctx_text, body_style))
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 4: CURRENT STATE ASSESSMENT
        # ------------------------------------------------------------------
        story.append(Paragraph("Current State & Technical Assessment", h1_style))
        add_gold_divider()
        
        story.append(Paragraph("Proposed Logical Architecture Flow", h2_style))
        arch_flow = "<b>System Users</b> &rarr; <b>Prime System UI</b> &rarr; <b>Orbit Avanya API Gateway</b> &rarr; <b>Database Clusters (PostgreSQL/MongoDB)</b>"
        flow_table = Table([[Paragraph(arch_flow, td_style)]], colWidths=[504])
        flow_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), CALLOUT_BG),
            ('BOX', (0,0), (-1,-1), 1, BORDER_GREY),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        story.append(flow_table)
        story.append(Spacer(1, 15))
        
        # 3-Column Issues Assessment Grid (Replicating DLC single box columns)
        story.append(Paragraph("Technical Gap Analysis", h2_style))
        
        gaps = proposal["gap_analysis"]
        col1_text = "<b>User Experience Needs</b><br/>" + "".join([f"• {item}<br/>" for item in gaps["user_experience_needs"]])
        col2_text = "<b>Technical Constraints</b><br/>" + "".join([f"• {item}<br/>" for item in gaps["technical_constraints"]])
        col3_text = "<b>Security Directives</b><br/>" + "".join([f"• {item}<br/>" for item in gaps["security_directives"]])
        
        gap_data = [[Paragraph(col1_text, td_style), Paragraph(col2_text, td_style), Paragraph(col3_text, td_style)]]
        gap_table = Table(gap_data, colWidths=[168, 168, 168])
        gap_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), LIGHT_GREY),
            ('BOX', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(gap_table)
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 5: PROPOSED SOLUTION & TECHNOLOGY
        # ------------------------------------------------------------------
        story.append(Paragraph("Proposed Solution & Technology Stack", h1_style))
        add_gold_divider()
        
        fit_score = proposal["fit_scoring"]
        sol_pre = (
            f"Recommended Core Platform: <b>{proposal['subcontractor']['product_name']} ({proposal['subcontractor']['industry_domain']})</b> "
            f"[Catalog Match Score: <b>{fit_score['overall_fit']:.1f}%</b>]"
        )
        story.append(Paragraph(sol_pre, h2_style))
        
        about_text = proposal["subcontractor"].get("about_text", "")
        story.append(Paragraph(about_text, body_style))
        
        story.append(Paragraph("<b>Key Software Modules Included:</b>", body_style))
        for feat in proposal["subcontractor"]["technology_stack"].get("ai", []) + ["Role-Based Security", "Audit Logs", "Analytics UI"]:
            story.append(Paragraph(f"• {feat} Configured Core Module", body_style))
            
        story.append(Spacer(1, 10))
        story.append(Paragraph("Logical Technology Stack Mapping", h2_style))
        
        stack = proposal["subcontractor"]["technology_stack"]
        stack_data = [
            [Paragraph("Layer", th_style), Paragraph("Technology Components", th_style)],
            [Paragraph("Frontend Layer", td_bold_style), Paragraph(", ".join(stack.get("frontend", ["React"])), td_style)],
            [Paragraph("Backend Layer", td_bold_style), Paragraph(", ".join(stack.get("backend", ["Python", "FastAPI"])), td_style)],
            [Paragraph("Database Storage", td_bold_style), Paragraph(", ".join(stack.get("database", ["PostgreSQL"])), td_style)],
            [Paragraph("Cloud & Infrastructure", td_bold_style), Paragraph(", ".join(stack.get("cloud", ["AWS"])), td_style)]
        ]
        stack_table = Table(stack_data, colWidths=[150, 354])
        stack_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), SECONDARY_COLOR),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(stack_table)
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 6: REQUIREMENT MAPPING MATRIX
        # ------------------------------------------------------------------
        story.append(Paragraph("Requirement Mapping Matrix", h1_style))
        add_gold_divider()
        story.append(Paragraph(
            "Mapping of targeted RFP performance specifications and security standards to Orbit Avanya's technology solutions:",
            body_style
        ))
        
        req_rows = [[
            Paragraph("RFP Required Specification", th_style),
            Paragraph("Orbit Avanya Module / Standard", th_style),
            Paragraph("Implementation & Compliance Action", th_style)
        ]]
        
        for item in proposal["alignment_matrices"]["technical_capabilities"]:
            req_rows.append([
                Paragraph(item["rfp_required_capability"], td_bold_style),
                Paragraph(item["our_matched_capability"], td_style),
                Paragraph(item["how_it_aligns"], td_style)
            ])
            
        for item in proposal["alignment_matrices"]["security_compliance"]:
            req_rows.append([
                Paragraph(item["rfp_security_requirement"], td_bold_style),
                Paragraph(item["our_matched_standard"], td_style),
                Paragraph(item["how_it_aligns"], td_style)
            ])
            
        req_table = Table(req_rows, colWidths=[130, 130, 244])
        req_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(req_table)
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 7: PRODUCT-FIT SCORING (RULE ENGINE)
        # ------------------------------------------------------------------
        story.append(Paragraph("Product-Fit Scoring (Rule Engine Output)", h1_style))
        add_gold_divider()
        
        story.append(Paragraph(
            "The following scores were generated by the Orbit Avanya weighted-matching rule engine "
            "(RFP Keyword 30% / Industry Domain 20% / Pain-Point 15% / Compliance 15% / Technology Stack 20%) "
            "run directly against the parsed solicitation text corpus.", body_style
        ))
        
        # Upgraded card scores fonts (24pt) for premium visual representation
        box_style_val = ParagraphStyle("BoxVal", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=PRIMARY_COLOR, alignment=1)
        box_style_lbl = ParagraphStyle("BoxLbl", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=CHARCOAL_COLOR, alignment=1)
        
        box_data = [
            [
                Paragraph(f"{fit_score['overall_fit']:.1f}%", box_style_val),
                Paragraph(f"{fit_score['keyword_match']:.1f}%", box_style_val),
                Paragraph(f"{fit_score['industry_match']:.1f}%", box_style_val),
                Paragraph(f"{fit_score['compliance_match']:.1f}%", box_style_val)
            ],
            [
                Paragraph("Overall Fit", box_style_lbl),
                Paragraph("Keyword Match", box_style_lbl),
                Paragraph("Industry Match", box_style_lbl),
                Paragraph("Compliance Match", box_style_lbl)
            ]
        ]
        box_table = Table(box_data, colWidths=[126, 126, 126, 126])
        box_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), CALLOUT_BG),
            ('BOX', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('GRID', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('TOPPADDING', (0,0), (-1,0), 12),
            ('BOTTOMPADDING', (0,0), (-1,0), 4),
            ('TOPPADDING', (0,1), (-1,1), 4),
            ('BOTTOMPADDING', (0,1), (-1,1), 12),
        ]))
        story.append(box_table)
        story.append(Spacer(1, 20))
        
        story.append(Paragraph("Matching Evidence Details", h2_style))
        story.append(Paragraph(f"<b>Technology keywords matched:</b> {', '.join(fit_score['technology_matched']).lower() or 'none'}", body_style))
        story.append(Paragraph(f"<b>Compliance standards matched:</b> {', '.join(fit_score['compliance_matched']) or 'none'}", body_style))
        story.append(Paragraph(f"<b>Pain points addressed:</b> {', '.join(fit_score['pain_points_addressed'])}", body_style))
        story.append(Paragraph(f"<b>Budget confidence:</b> {fit_score['budget_confidence']}", body_style))
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 8: IMPLEMENTATION STRATEGY
        # ------------------------------------------------------------------
        story.append(Paragraph("Implementation Strategy & Timeline", h1_style))
        add_gold_divider()
        
        story.append(Paragraph(
            "Below is our phased technical implementation plan, structured to fit within standard "
            "6-9 months government delivery windows:", body_style
        ))
        
        impl_rows = [[Paragraph("Phase", th_style), Paragraph("Activity Description", th_style), Paragraph("Duration", th_style), Paragraph("Key Deliverables & Notes", th_style)]]
        for phase in proposal["implementation_strategy"]:
            impl_rows.append([
                Paragraph(phase["phase"], td_bold_style),
                Paragraph(phase["activity"], td_style),
                Paragraph(phase["duration"], td_style),
                Paragraph(phase["deliverables"], td_style)
            ])
            
        impl_table = Table(impl_rows, colWidths=[60, 160, 80, 204])
        impl_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(impl_table)
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 9: RESOURCE ALLOCATION & WORK SCOPE (NO MONEY)
        # ------------------------------------------------------------------
        story.append(Paragraph("Resource Allocation & Work Scope Assessment", h1_style))
        add_gold_divider()
        
        # Upgraded cards for impact indicators
        story.append(Paragraph("Teaming Effort Impact Indicators", h2_style))
        impact_data = [
            [
                Paragraph("30%", box_style_val),
                Paragraph("15%", box_style_val),
                Paragraph("~50%", box_style_val)
            ],
            [
                Paragraph("Faster systems integration and deployment", box_style_lbl),
                Paragraph("Reduced customized scripting overhead", box_style_lbl),
                Paragraph("Mitigated program execution risk", box_style_lbl)
            ]
        ]
        impact_table = Table(impact_data, colWidths=[168, 168, 168])
        impact_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), CALLOUT_BG),
            ('BOX', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('GRID', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('TOPPADDING', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 4),
            ('TOPPADDING', (0,1), (-1,1), 4),
            ('BOTTOMPADDING', (0,1), (-1,1), 10),
        ]))
        story.append(impact_table)
        story.append(Spacer(1, 15))
        
        story.append(Paragraph("One-Time Roadmap Phase Durations", h2_style))
        
        comm = proposal["commercial_proposal"]
        cost_rows = [[Paragraph("Teaming Work Package / Scope Description", th_style), Paragraph("Duration / Effort", th_style)]]
        for idx, item in enumerate(comm["one_time_costs"]):
            if idx == len(comm["one_time_costs"]) - 1:
                cost_rows.append([
                    Paragraph(f"<b>{item['item']}</b>", td_bold_style),
                    Paragraph(f"<b>{item['duration']}</b>", td_bold_style)
                ])
            else:
                cost_rows.append([
                    Paragraph(item["item"], td_style),
                    Paragraph(item["duration"], td_style)
                ])
                
        cost_table = Table(cost_rows, colWidths=[354, 150])
        cost_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, LIGHT_GREY]),
            ('BACKGROUND', (0,-1), (-1,-1), CALLOUT_BG),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(cost_table)
        story.append(Spacer(1, 15))
        
        # Annual support
        story.append(Paragraph("Annual Support SLA Specifications", h2_style))
        ops_rows = [[Paragraph("Support Service Scope", th_style), Paragraph("Service Level Agreement (SLA)", th_style)]]
        for idx, item in enumerate(comm["annual_costs"]):
            if idx == len(comm["annual_costs"]) - 1:
                ops_rows.append([
                    Paragraph(f"<b>{item['item']}</b>", td_bold_style),
                    Paragraph(item["response"], td_bold_style)
                ])
            else:
                ops_rows.append([
                    Paragraph(item["item"], td_style),
                    Paragraph(item["response"], td_style)
                ])
                
        ops_table = Table(ops_rows, colWidths=[354, 150])
        ops_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), SECONDARY_COLOR),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, LIGHT_GREY]),
            ('BACKGROUND', (0,-1), (-1,-1), CALLOUT_BG),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(ops_table)
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # NEW PAGE: RFP EVALUATION CRITERIA SELF-ASSESSMENT
        # ------------------------------------------------------------------
        story.append(Paragraph("RFP Evaluation Criteria & Self-Assessment", h1_style))
        add_gold_divider()
        story.append(Paragraph(
            "Our self-assessment against the primary evaluation criteria, mapping where each "
            "requirement is addressed inside this teaming response:", body_style
        ))
        
        eval_rows = [[
            Paragraph("RFP Bid Evaluation Criterion", th_style),
            Paragraph("Where Addressed / Teaming Response Mapping", th_style)
        ]]
        
        for item in proposal["evaluation_criteria"]:
            eval_rows.append([
                Paragraph(item["criterion"], td_bold_style),
                Paragraph(item["where_addressed"], td_style)
            ])
            
        eval_table = Table(eval_rows, colWidths=[200, 304])
        eval_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(eval_table)
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 10: WHY ORBIT AVANYA & CONTACTS
        # ------------------------------------------------------------------
        story.append(Paragraph("Why Orbit Avanya & Next Steps", h1_style))
        add_gold_divider()
        
        why_text = "<b>Why Teaming with Us Makes Sense:</b><br/>" + "".join([f"• {item}<br/>" for item in proposal["why_us"]])
        next_text = "<b>Partnership Kickoff Next Steps:</b><br/>" + "".join([f"{idx}. {item}<br/>" for idx, item in enumerate(proposal["next_steps"], 1)])
        
        why_data = [[Paragraph(why_text, td_style), Paragraph(next_text, td_style)]]
        why_table = Table(why_data, colWidths=[244, 244])
        why_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), LIGHT_GREY),
            ('BOX', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('TOPPADDING', (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(why_table)
        story.append(Spacer(1, 15))
        
        story.append(Paragraph("Teaming Contact Information", h2_style))
        contact_data = [
            [Paragraph("Organization Point of Contact", th_style), Paragraph("Orbit Avanya LLP Contacts", th_style)],
            [
                Paragraph(
                    f"<b>{proposal['prime_contractor']['company_name']}</b><br/>"
                    f"Business Development Group<br/>"
                    f"Headquarters: {proposal['prime_contractor']['headquarters'] or 'N/A'}<br/>"
                    f"Website: {proposal['prime_contractor']['website'] or 'N/A'}", td_style
                ),
                Paragraph(
                    "<b>Orbit Avanya LLP</b><br/>"
                    "Pune, Maharashtra, India<br/>"
                    "Email: sales@orbitavanya.com<br/>"
                    "Partnerships: partnerships@orbitavanya.com<br/>"
                    "Support: support@orbitavanya.com", td_style
                )
            ]
        ]
        contact_table = Table(contact_data, colWidths=[244, 244])
        contact_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(contact_table)

        # Build Document
        doc.build(story, canvasmaker=make_canvas(solicitation_number))
        logger.info(f"Detailed proposal PDF successfully written to: {pdf_path}")
        return pdf_path

    def generate_product_match_report(self, solicitation_number: str) -> Path:
        """
        Generates a 5-page Product Match Report PDF scoring and ranking all 15 catalog products,
        replicating the structure of Orbit_Avanya_Product_Match_Report_DLC.pdf.
        """
        json_path = self.project_root / "output" / "proposals" / f"{solicitation_number}_pitch_data.json"
        pdf_path = self.project_root / "output" / "pdf" / f"{solicitation_number}_product_match_report.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        if not json_path.exists():
            raise FileNotFoundError(f"Proposal JSON data not found at: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            proposal = json.load(f)

        # Load all 15 product profiles from local JSON
        profiles_json_path = self.project_root / "orbit_avanya_detailed_profiles.json"
        if not profiles_json_path.exists():
            raise FileNotFoundError(f"Product profiles JSON not found at: {profiles_json_path}")
            
        with open(profiles_json_path, "r", encoding="utf-8") as f:
            profiles = json.load(f)

        # Run dynamic scoring rule-engine
        ranked_products = self.calculate_match_scores(proposal, profiles)
        top_product = ranked_products[0]

        # Setup document
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=72,
            bottomMargin=72
        )
        
        styles = getSampleStyleSheet()
        
        cover_pre_style = ParagraphStyle(
            "CoverPreMatch", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=10, leading=12, textColor=SECONDARY_COLOR, spaceAfter=6
        )
        cover_title_style = ParagraphStyle(
            "CoverTitleMatch", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=30, leading=36, textColor=PRIMARY_COLOR, spaceAfter=12
        )
        cover_sub_style = ParagraphStyle(
            "CoverSubMatch", parent=styles["Normal"], fontName="Helvetica",
            fontSize=11, leading=16, textColor=CHARCOAL_COLOR, spaceAfter=30
        )
        h1_style = ParagraphStyle(
            "Heading1Match", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, textColor=PRIMARY_COLOR, spaceBefore=22, spaceAfter=4,
            keepWithNext=True
        )
        h2_style = ParagraphStyle(
            "Heading2Match", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=12.5, leading=16, textColor=SECONDARY_COLOR, spaceBefore=14, spaceAfter=6,
            keepWithNext=True
        )
        body_style = ParagraphStyle(
            "BodyMatch", parent=styles["Normal"], fontName="Helvetica",
            fontSize=10, leading=15.5, textColor=CHARCOAL_COLOR, spaceAfter=10
        )
        th_style = ParagraphStyle(
            "TableHeaderMatch", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=9.5, leading=12, textColor=WHITE
        )
        td_style = ParagraphStyle(
            "TableCellMatch", parent=styles["Normal"], fontName="Helvetica",
            fontSize=9, leading=13.5, textColor=CHARCOAL_COLOR
        )
        td_bold_style = ParagraphStyle(
            "TableCellBoldMatch", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=9, leading=13.5, textColor=PRIMARY_COLOR
        )
        
        story = []

        def add_gold_divider():
            story.append(Spacer(1, 4))
            tbl = Table([[""]], colWidths=[504])
            tbl.setStyle(TableStyle([
                ('LINEABOVE', (0,0), (-1,-1), 1.5, SECONDARY_COLOR),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 12))

        # ------------------------------------------------------------------
        # PAGE 1: TITLE & TOP MATCH CARD
        # ------------------------------------------------------------------
        story.append(Spacer(1, 0.8 * inch))
        story.append(Paragraph("Product Match Report", cover_title_style))
        story.append(Paragraph(f"Orbit Avanya LLP Product Catalog vs. {proposal['metadata']['project_title']}", cover_sub_style))
        add_gold_divider()

        # Metadata Card
        meta_data = [
            [Paragraph("Prepared For:", td_bold_style), Paragraph("Internal Bid Team, Orbit Avanya LLP", td_style)],
            [Paragraph("Target RFP / Project:", td_bold_style), Paragraph(proposal["metadata"]["project_title"], td_style)],
            [Paragraph("Reference Number:", td_bold_style), Paragraph(f"OA-{solicitation_number}-2026-001", td_style)]
        ]
        meta_table = Table(meta_data, colWidths=[120, 384])
        meta_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 20))

        story.append(Paragraph("Top Match", h2_style))
        
        # Center card displaying Top Match score and product
        score_val_style = ParagraphStyle("ScoreVal", fontName="Helvetica-Bold", fontSize=32, leading=38, textColor=PRIMARY_COLOR, alignment=1)
        score_lbl_style = ParagraphStyle("ScoreLbl", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=CHARCOAL_COLOR, alignment=1)
        
        card_data = [
            [Paragraph(f"{top_product['overall_score']:.1f}%", score_val_style)],
            [Paragraph(f"<b>{top_product['product_name']}</b> ({top_product['industry_domain']} domain)", score_lbl_style)]
        ]
        card_table = Table(card_data, colWidths=[504])
        card_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), CALLOUT_BG),
            ('BOX', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('TOPPADDING', (0,0), (-1,-1), 16),
            ('BOTTOMPADDING', (0,0), (-1,-1), 16),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        story.append(card_table)
        story.append(Spacer(1, 15))

        desc_p1 = (
            "This report scores every product in the Orbit Avanya catalog against the targeted RFP using the weighted matching "
            "model defined in the Orbit Avanya Bid Intelligence Rule Engine (RFP Keyword 30%, Industry Domain 20%, Pain-Point 15%, "
            "Compliance 15%, Budget 10%, Technology 10%). Products are ranked below; only the top matches should be referenced in the B2B proposal."
        )
        story.append(Paragraph(desc_p1, body_style))
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 2: FULL RANKING TABLE
        # ------------------------------------------------------------------
        story.append(Paragraph("Full Ranking — All Catalog Products", h1_style))
        add_gold_divider()

        rank_rows = [[
            Paragraph("Rank", th_style),
            Paragraph("Product Name", th_style),
            Paragraph("Domain Focus", th_style),
            Paragraph("Overall Score", th_style),
            Paragraph("Fit Designation", th_style)
        ]]

        for idx, item in enumerate(ranked_products, 1):
            fit_text = "Recommended" if item["overall_score"] >= 80.0 else ("Complementary" if item["overall_score"] >= 60.0 else "Not a fit")
            rank_rows.append([
                Paragraph(str(idx), td_bold_style),
                Paragraph(item["product_name"], td_style),
                Paragraph(item["industry_domain"], td_style),
                Paragraph(f"{item['overall_score']:.1f}%", td_style),
                Paragraph(fit_text, td_bold_style)
            ])

        rank_table = Table(rank_rows, colWidths=[40, 164, 100, 100, 100])
        rank_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER_GREY),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(rank_table)
        story.append(Spacer(1, 15))

        story.append(Paragraph(
            "<b>Recommended (>=80%):</b> lead with this product in the proposal. "
            "<b>Complementary (60-79%):</b> position as an add-on module or future phase. "
            "<b>Not a fit (<60%):</b> omit from the teaming response.", td_style
        ))
        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGES 3 & 4: SCORING DETAIL — TOP MATCHES
        # ------------------------------------------------------------------
        story.append(Paragraph("Scoring Detail — Top Matches", h1_style))
        add_gold_divider()

        # Detailed cards for Top 3 matches
        for idx in range(min(3, len(ranked_products))):
            prod = ranked_products[idx]
            story.append(Paragraph(f"<b>{idx+1}. {prod['product_name']} &mdash; {prod['overall_score']:.1f}% overall</b>", h2_style))
            
            def make_bar(score):
                hashes = int(score / 5)
                dashes = 20 - hashes
                return f"{'#' * hashes}{'-' * dashes}"

            fact_rows = [
                [Paragraph("Factor", th_style), Paragraph("Weight", th_style), Paragraph("Factor Score", th_style), Paragraph("Bar Representation Chart", th_style)],
                [Paragraph("Keyword Match", td_style), Paragraph("30%", td_style), Paragraph(f"{prod['keyword_score']:.1f}%", td_style), Paragraph(make_bar(prod['keyword_score']), td_bold_style)],
                [Paragraph("Industry Match", td_style), Paragraph("20%", td_style), Paragraph(f"{prod['industry_score']:.1f}%", td_style), Paragraph(make_bar(prod['industry_score']), td_bold_style)],
                [Paragraph("Pain-Point Match", td_style), Paragraph("15%", td_style), Paragraph(f"{prod['pain_point_score']:.1f}%", td_style), Paragraph(make_bar(prod['pain_point_score']), td_bold_style)],
                [Paragraph("Compliance Match", td_style), Paragraph("15%", td_style), Paragraph(f"{prod['compliance_score']:.1f}%", td_style), Paragraph(make_bar(prod['compliance_score']), td_bold_style)],
                [Paragraph("Budget Fit", td_style), Paragraph("10%", td_style), Paragraph(f"{prod['budget_score']:.1f}%", td_style), Paragraph(make_bar(prod['budget_score']), td_bold_style)],
                [Paragraph("Technology Match", td_style), Paragraph("10%", td_style), Paragraph(f"{prod['tech_stack_score']:.1f}%", td_style), Paragraph(make_bar(prod['tech_stack_score']), td_bold_style)]
            ]
            fact_table = Table(fact_rows, colWidths=[130, 64, 90, 220])
            fact_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
                ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER_GREY),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                ('LEFTPADDING', (0,0), (-1,-1), 8),
                ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ]))
            story.append(fact_table)
            story.append(Spacer(1, 10))

            why_matches = (
                f"<b>Why it matches:</b> Technical features overlap with RFP-mentioned capabilities ({', '.join(prod['features'][:4])}). "
                f"Security compliance alignment checks out on {', '.join(prod['compliance_standards'][:3])}. "
                f"Target domain of {prod['industry_domain']} aligns with solicitation profile directives."
            )
            story.append(Paragraph(why_matches, body_style))
            story.append(Spacer(1, 15))
            
            if idx == 1:
                story.append(PageBreak()) # Clean page break after 2nd matches detail

        story.append(PageBreak())

        # ------------------------------------------------------------------
        # PAGE 5: RECOMMENDATION SUMMARY
        # ------------------------------------------------------------------
        story.append(Paragraph("Recommendation Summary", h1_style))
        add_gold_divider()

        summary_p1 = (
            f"Lead the teaming proposal with <b>{ranked_products[0]['product_name']}</b> as the core platform "
            f"({ranked_products[0]['industry_domain']} focus) matching the target RFP requirements. Position "
            f"<b>{ranked_products[1]['product_name']}</b> as an optional Phase 2 add-on module to support secondary "
            f"data analysis, and <b>{ranked_products[2]['product_name']}</b> as a supporting portal to manage portal inquiries. "
            f"All other products ranked below 60% are designated as not-a-fit for this specific solicitation and should be excluded from the proposal."
        )
        story.append(Paragraph(summary_p1, body_style))

        # Build Match PDF
        doc.build(story, canvasmaker=make_canvas(solicitation_number))
        logger.info(f"Product Match Report PDF successfully written to: {pdf_path}")
        return pdf_path

if __name__ == "__main__":
    import sys
    sol = sys.argv[1] if len(sys.argv) > 1 else "N00178-26-R-3001"
    gen = PDFGenerator()
    gen.generate_pdf(sol)
