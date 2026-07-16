import os
import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime, timezone

from utils.helpers import setup_logger
from utils.db_client import get_collection, get_database

logger = setup_logger(__name__)

class PitchCompiler:
    """
    Teaming Proposal Synthesizer.
    Combines RFP requirements, Prime Contractor (winner) profile, and Orbit Avanya profile
    to formulate a highly detailed structured teaming agreement proposal JSON.
    """

    def __init__(self, project_root: str = str(Path(__file__).resolve().parent.parent)):
        self.project_root = Path(project_root)

    def load_winner_profile(self, winner_name: str) -> Dict[str, Any]:
        """Loads the winning contractor's cached profile from MongoDB."""
        logger.info(f"Loading winning contractor profile for: {winner_name}")
        profile = None

        try:
            col = get_collection("company_profiles")
            # Try matching by name (case-insensitive regex), first word, or company_slug
            first_word = winner_name.split()[0] if winner_name else ""
            profile = col.find_one({"$or": [
                {"company_name": {"$regex": f"^{winner_name}$", "$options": "i"}},
                {"company_name": {"$regex": winner_name, "$options": "i"}},
                {"company_name": {"$regex": f"^{first_word}\\b", "$options": "i"}},
                {"company_slug": winner_name.lower().replace(" ", "_").replace(".", "")}
            ]})
        except Exception as e:
            logger.warning(f"Failed to load winner profile from MongoDB: {e}")

        if not profile:
            # Fallback mock profile if not scraped yet
            logger.info("Winner profile not found in database. Using rule-based fallback profile.")
            profile = {
                "company_name": winner_name,
                "website": "https://guidehouse.com" if "guidehouse" in winner_name.lower() else "N/A",
                "industry": "IT Consulting & Professional Services",
                "description": f"{winner_name} is a global professional services firm delivering advisory, technology, and managed services.",
                "headquarters": "McLean, VA",
                "employee_count": "10,000+ employees",
                "specialties": ["consulting", "advisory", "digital", "technology", "managed services", "defense", "security", "government"],
                "competitors": ["Accenture", "Booz Allen Hamilton", "Deloitte Consulting"],
                "rfp_strengths": ["Strong program management", "Global scale and delivery capability", "Government sector experience"]
            }

        # Remove mongo _id for output
        if "_id" in profile:
            del profile["_id"]
        return profile

    def load_orbit_avanya_profile(self, domain_keyword: str) -> Dict[str, Any]:
        """Loads the best matching Orbit Avanya product profile from MongoDB based on domain keywords."""
        logger.info(f"Searching Orbit Avanya product profile matching domain: '{domain_keyword}'")
        db = get_database()
        orbit_col = db["orbit-avanya"]
        
        # Rule-based mapping from domain keyword to company_slug
        slug = "orbit-avanya-ai-analytics-dashboard" # default
        
        keyword_lower = domain_keyword.lower()
        if any(x in keyword_lower for x in ["health", "hms", "medical", "operating", "clinical", "hospital", "6515"]):
            slug = "orbit-avanya-hms"
        elif any(x in keyword_lower for x in ["education", "lms", "learning", "school", "course"]):
            slug = "orbit-avanya-lms"
        elif any(x in keyword_lower for x in ["financial", "analytics", "predictive", "dashboard", "modeling", "data", "database"]):
            slug = "orbit-avanya-ai-analytics-dashboard"
        elif any(x in keyword_lower for x in ["erp", "operations", "enterprise", "resource"]):
            slug = "orbit-avanya-erp"
        elif any(x in keyword_lower for x in ["support", "helpdesk", "portal", "ticket"]):
            slug = "orbit-avanya-help-desk-portal"
        elif any(x in keyword_lower for x in ["agri", "farm", "crop", "agriculture"]):
            slug = "orbit-avanya-agriculture-portal"
        elif any(x in keyword_lower for x in ["sales", "crm", "lead", "client"]):
            slug = "orbit-avanya-crm"
        elif any(x in keyword_lower for x in ["hr", "hrms", "employee", "payroll", "salary"]):
            slug = "orbit-avanya-hrms"
            
        logger.info(f"Selected Orbit Avanya profile slug: '{slug}'")
        profile = None
        
        try:
            profile = orbit_col.find_one({"company_slug": slug})
        except Exception as e:
            logger.warning(f"Failed to query MongoDB orbit-avanya collection: {e}")

        # Fallback to local JSON if MongoDB fails
        if not profile:
            json_path = self.project_root / "orbit_avanya_detailed_profiles.json"
            if json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        profiles = json.load(f)
                        for p in profiles:
                            if p.get("company_slug") == slug:
                                profile = p
                                break
                except Exception as e:
                    logger.error(f"Failed to read local profiles JSON: {e}")

        if not profile:
            # Minimal hardcoded fallback
            profile = {
                "company_slug": slug,
                "company_name": "Orbit Avanya LLP",
                "industry_domain": "AI & Analytics",
                "product_name": "AI Analytics Dashboard",
                "about_text": "Orbit Avanya LLP delivers AI Analytics Dashboards designed for executive insights and predictive modeling.",
                "technology_stack": {
                    "frontend": ["React", "Next.js"],
                    "backend": ["Python", "FastAPI"],
                    "database": ["PostgreSQL"],
                    "cloud": ["AWS"]
                },
                "key_features": ["Analytics Dashboard", "Workflow Automation", "API Integration", "AI-driven Insights"],
                "security_and_compliance": ["ISO 27001 Ready", "Role Based Security", "Audit Logs"]
            }

        if "_id" in profile:
            del profile["_id"]
        return profile

    def compile_teaming_proposal(self, rfp_data: Dict[str, Any], winner_name: str, workshare_pct: float = 15.0) -> Dict[str, Any]:
        """
        Aligns RFP requirements, Winner profile, and Orbit Avanya profile,
        generating a highly detailed structure with all custom B2B proposal details
        free of any pricing or currency (money) information.
        """
        sol_num = rfp_data.get("solicitation_number", "Unknown")
        rfp_title = rfp_data.get("summary", "").split(" is for ")[-1].split(".")[0] or "Professional IT Support Services"
        
        if not (10.0 <= workshare_pct <= 20.0):
            raise ValueError(f"workshare_pct must be between 10.0 and 20.0, got {workshare_pct}")

        logger.info(f"Compiling teaming proposal for RFP {sol_num} with Winner '{winner_name}'")

        # 1. Load profiles
        winner_profile = self.load_winner_profile(winner_name)
        domain_keyword = rfp_data.get("summary", "") + " " + sol_num
        our_profile = self.load_orbit_avanya_profile(domain_keyword)

        # 2. Align tech stack
        rfp_tech = rfp_data.get("identified_components", {}).get("technical", [])
        tech_alignment = []
        
        tech_rules = {
            "Surgical Equipment Interfaces": {
                "match": "API Integration & React UI",
                "desc": "Orbit Avanya's HMS uses React/Next.js for real-time surgical visual feeds and FastAPI for device telemetry interfaces."
            },
            "API & Software Integration": {
                "match": "FastAPI & REST Connectors",
                "desc": "Provides Python/FastAPI middleware layers to establish secure API interfaces between systems."
            },
            "Network & Video Routing": {
                "match": "AWS MediaStore & WebSockets",
                "desc": "Utilizes AWS cloud routing infrastructure and Next.js WebSockets to stream visual data securely."
            },
            "Database Management": {
                "match": "PostgreSQL & MongoDB Optimization",
                "desc": "Enforces database performance optimization, indexing, and clustering using PostgreSQL and MongoDB."
            },
            "Advanced Data Analytics": {
                "match": "AI-driven Insights & Analytics",
                "desc": "Orbit Avanya's dashboard includes pre-built Python analytics algorithms to build predictive trends."
            }
        }

        for item in rfp_tech:
            if item in tech_rules:
                tech_alignment.append({
                    "rfp_required_capability": item,
                    "our_matched_capability": tech_rules[item]["match"],
                    "how_it_aligns": tech_rules[item]["desc"]
                })
                
        if not tech_alignment:
            tech_alignment.append({
                "rfp_required_capability": "Advanced Data Analytics & ETL",
                "our_matched_capability": "Python, PostgreSQL, and AWS",
                "how_it_aligns": "Our product features a robust Python ETL pipeline and PostgreSQL database optimization module to aggregate data."
            })

        # 3. Align security compliance
        rfp_sec = rfp_data.get("identified_components", {}).get("security", [])
        security_alignment = []

        security_rules = {
            "VA Handbook 6500.6": {
                "match": "ISO 27001 Ready & Audit Logs",
                "desc": "Enforces security controls matching VA handbook specifications including background checks support."
            },
            "Appendix C Compliance": {
                "match": "Role Based Security",
                "desc": "Ensures administrative and technical safeguard language is implemented out-of-the-box."
            },
            "HIPAA/HITECH": {
                "match": "Role Based Security & Audits",
                "desc": "Enforces strict patient privacy boundaries and encryption algorithms compliant with HIPAA."
            },
            "Audit Logging & Monitoring": {
                "match": "Audit Logs",
                "desc": "Maintains tamper-proof system audit logs tracking data modifications and access events."
            },
            "Information Security & Privacy": {
                "match": "ISO 27001 & Role Based Security",
                "desc": "Product meets advanced information security controls, preserving user access boundaries."
            }
        }

        for item in rfp_sec:
            if item in security_rules:
                security_alignment.append({
                    "rfp_security_requirement": item,
                    "our_matched_standard": security_rules[item]["match"],
                    "how_it_aligns": security_rules[item]["desc"]
                })

        # 4. Fit Scoring (Calculated via overlap rules)
        matched_tech_keys = [a["rfp_required_capability"] for a in tech_alignment]
        matched_sec_keys = [a["rfp_security_requirement"] for a in security_alignment]
        keyword_score = 100.0 if len(matched_tech_keys) >= 3 else 80.0
        compliance_score = 100.0 if len(matched_sec_keys) >= 4 else 75.0
        tech_score = 90.0
        overall_fit = (keyword_score * 0.3) + (100.0 * 0.2) + (compliance_score * 0.3) + (tech_score * 0.2)

        fit_scoring = {
            "overall_fit": overall_fit,
            "keyword_match": keyword_score,
            "industry_match": 100.0,
            "compliance_match": compliance_score,
            "technology_matched": matched_tech_keys,
            "compliance_matched": matched_sec_keys,
            "pain_points_addressed": ["database_performance", "access_controls", "visual_telemetry", "audit_logs"],
            "budget_confidence": "HIGH — aligned with standard GSA labor rate categories."
        }

        # 5. Gap Analysis Data
        gap_analysis = {
            "user_experience_needs": [
                "Dashboards need real-time data feeds.",
                "Telemetry screens require modular widgets.",
                "Access must support responsive mobile layouts.",
                "Custom reporting features must be easily configurable."
            ],
            "technical_constraints": [
                "Heavy analytical queries can throttle databases.",
                "Require structured REST API endpoints.",
                "Multiple disparate endpoints need caching middleware.",
                "High availability database configurations are necessary."
            ],
            "security_directives": [
                "Mandatory compliance with VA Handbook 6500.6.",
                "Complete audit logging for all database mutations.",
                "Role-Based Access Controls (RBAC) to block data leaks.",
                "Secure cryptographic protocols for data at rest."
            ]
        }

        # 6. Phased Implementation Strategy
        implementation_strategy = [
            {"phase": "Phase 1", "activity": "Discovery & System Audit", "duration": "2 weeks", "deliverables": "Audit existing database indexes, define API formats"},
            {"phase": "Phase 2", "activity": "Schema Design & Prototyping", "duration": "3 weeks", "deliverables": "PostgreSQL schema design, wireframe visual graphs"},
            {"phase": "Phase 3", "activity": "Core System Development", "duration": "8 weeks", "deliverables": "Develop FastAPI endpoints, React dashboard components"},
            {"phase": "Phase 4", "activity": "Security Hardening", "duration": "4 weeks", "deliverables": "Configure audit logging, role-based controls, FIPS"},
            {"phase": "Phase 5", "activity": "Integration & Testing", "duration": "4 weeks", "deliverables": "Stress-testing databases, mock interface feeds"},
            {"phase": "Phase 6", "activity": "Deployment & Go-Live", "duration": "2 weeks", "deliverables": "Launch containerized backend, support hypercare"}
        ]

        # 7. Commercial Scope (NO MONEY / PRICING DETAILS)
        commercial_proposal = {
            "one_time_costs": [
                {"item": "Phase 1-2: Discovery, Schema Audit & Design", "duration": "5 weeks"},
                {"item": "Phase 3-4: API Gateway, Custom Dashboards & Hardening", "duration": "12 weeks"},
                {"item": "Phase 5: Systems Integration & Verification Testing", "duration": "4 weeks"},
                {"item": "Phase 6: Training, Handover & Deployment Support", "duration": "2 weeks"},
                {"item": "Total Implementation Roadmap Scope", "duration": "23 weeks"}
            ],
            "annual_costs": [
                {"item": "Standard Maintenance & Security Patches", "response": "Next Business Day"},
                {"item": "Dedicated Support Desk (9am - 5pm EST)", "response": "4-Hour SLA Response"},
                {"item": "Maintenance & Minor Customization Pool", "response": "Scheduled Releases"},
                {"item": "Annual Operations Support SLA", "response": "Continuous Coverage"}
            ]
        }

        # 8. Qualification & Next Steps
        why_us = [
            "AI-first architecture across our entire product catalog, enabling next-generation analytics.",
            "Rapid deployment framework with an average 6-week baseline setup.",
            "Modern cloud-native stack including React/Next.js, FastAPI, PostgreSQL, and AWS/Azure.",
            "ISO 27001-ready security posture with robust role-based access control.",
            "Modular solutions allowing future additions without codebase rebuilds."
        ]
        
        next_steps = [
            "Discovery & Technical Audit Workshops with team leaders.",
            "Technical deep-dive on PostgreSQL schemas & API bindings.",
            "Contract signing and baseline repository configurations.",
            "Subcontractor kickoff and development sprint planning."
        ]

        # 9. Self-Assessment matrix
        evaluation_criteria = [
            {"criterion": "Completeness of proposal and overall solution", "where_addressed": "Sections: Proposed Solution, Requirement Mapping Matrix"},
            {"criterion": "Congruence with goals and objectives", "where_addressed": "Sections: Understanding Your Business, Project Context"},
            {"criterion": "Team qualifications, experience and expertise", "where_addressed": "Section: Why Orbit Avanya"},
            {"criterion": "Open, knowledge-sharing communication", "where_addressed": "Section: Why Orbit Avanya / Next Steps"},
            {"criterion": "Features and functions of the core software", "where_addressed": "Sections: Proposed Solution, Technology Stack"},
            {"criterion": "Project and future operations costs", "where_addressed": "Section: Commercial Proposal"}
        ]

        # 10. Synthesize Prime/Sub alignment matrix
        alignment_matrix = [
            {
                "requirement": "Program Management & Integration",
                "prime_role": f"{winner_name} will lead primary system integration, government relations, and overall contract administration.",
                "subcontractor_role": "Provide technical expertise, implementation templates, and product configurations.",
                "workshare_share_split": "85% Prime / 15% Sub"
            },
            {
                "requirement": "Custom Software Development",
                "prime_role": f"Oversee architectural guidelines and validate requirements.",
                "subcontractor_role": "Develop custom REST APIs, Python predictive analytics code, and Next.js visual dashboard UI components.",
                "workshare_share_split": "70% Prime / 30% Sub"
            },
            {
                "requirement": "Database & Security Compliance",
                "prime_role": "Administer production database nodes and overall network infrastructure.",
                "subcontractor_role": "Configure PostgreSQL indices, write audit logger triggers, and audit role-based access configurations.",
                "workshare_share_split": "75% Prime / 25% Sub"
            }
        ]

        # 11. Work breakdown share
        work_breakdown = [
            {
                "task": "Visual Dashboards & Predictive Widgets Development",
                "description": "Construct the Next.js visual dashboard screens and wire up data graphs showing analytics reports.",
                "proposed_share": round(workshare_pct * 0.4, 1)
            },
            {
                "task": "Data Warehousing & ETL Pipeline Setup",
                "description": "Configure the Python data ingestion pipelines and database triggers for logging transactions.",
                "proposed_share": round(workshare_pct * 0.35, 1)
            },
            {
                "task": "Security Enforcement & Compliance Hardening",
                "description": "Hardening the API endpoints using role-based permissions and enabling automated audit logs.",
                "proposed_share": round(workshare_pct * 0.25, 1)
            }
        ]

        # 12. Teaming outreach narrative
        our_product = our_profile.get("product_name")
        is_mock_or_unknown = (
            not sol_num 
            or sol_num.lower() in ("unknown", "none", "n/a")
            or sol_num.lower().startswith("mock")
        )
        if is_mock_or_unknown:
            outreach_text = (
                f"Dear Team at {winner_name},\n\n"
                f"Orbit Avanya LLP is writing to propose a strategic teaming partnership to support your delivery team "
                f"on {rfp_title}. As an agile technology firm specializing in secure visual dashboards and database integrations, "
                f"we offer a pre-built {our_product} product framework that fits the technical requirements of this project.\n\n"
                f"We propose taking on a {workshare_pct}% teaming work share, specifically focusing on building the Next.js "
                f"dashboards, configuring the Python ETL data pipelines, and implementing the security compliance logging layers. "
                f"By teaming with Orbit Avanya, {winner_name} gains access to certified visual analytics developers and pre-tested database "
                f"interfaces, reducing implementation timeframes and mitigating technical execution risk.\n\n"
                f"We look forward to discussing how our {our_product} capabilities can align with your project delivery plans."
            )
        else:
            outreach_text = (
                f"Dear Team at {winner_name},\n\n"
                f"First, congratulations on winning the prime contract award for VA/DHS Solicitation {sol_num} ({rfp_title})!\n\n"
                f"Orbit Avanya LLP is writing to propose a strategic subcontracting partnership to support your delivery team "
                f"on this contract. As an agile technology firm specializing in secure visual dashboards and database integrations, "
                f"we offer a pre-built {our_product} product framework that fits the technical requirements of this project.\n\n"
                f"We propose taking on a {workshare_pct}% subcontracting work share, specifically focusing on building the Next.js "
                f"dashboards, configuring the Python ETL data pipelines, and implementing the security compliance logging layers. "
                f"By teaming with Orbit Avanya, {winner_name} gains access to certified visual analytics developers and pre-tested database "
                f"interfaces, reducing implementation timeframes and mitigating technical execution risk.\n\n"
                f"We look forward to discussing how our {our_product} capabilities can align with your program delivery plans."
            )

        # 13. Extract competitors list (excluding pricing/money) from rfp_data
        raw_competitors = rfp_data.get("competitors") or []
        cleaned_competitors = []
        for comp in raw_competitors:
            cleaned_competitors.append({
                "company_name": comp.get("company_name"),
                "protest_status": comp.get("protest_status") or "None",
                "bid_details": comp.get("bid_details") or "No detailed description extracted."
            })

        proposal = {
            "metadata": {
                "solicitation_number": sol_num,
                "project_title": rfp_title,
                "issuing_agency": rfp_data.get("agency", "Department of Defense"),
                "status": "Awarded",
                "place_of_performance": rfp_data.get("place_of_performance", "N/A"),
                "naics_code": rfp_data.get("naics_code", "N/A"),
                "contacts": rfp_data.get("contacts") or [],
                "award_details": {
                    "contract_number": rfp_data.get("award", {}).get("award_number", "N/A"),
                    "award_date": rfp_data.get("award", {}).get("date", "N/A")
                }
            },
            "prime_contractor": {
                "company_name": winner_profile.get("company_name"),
                "website": winner_profile.get("website"),
                "headquarters": winner_profile.get("headquarters"),
                "description": winner_profile.get("description"),
                "key_strengths": winner_profile.get("rfp_strengths", [])[:3]
            },
            "subcontractor": {
                "company_name": our_profile.get("company_name"),
                "product_name": our_profile.get("product_name"),
                "about_text": our_profile.get("about_text"),
                "industry_domain": our_profile.get("industry_domain"),
                "technology_stack": our_profile.get("technology_stack"),
                "emails": our_profile.get("emails", ["sales@orbitavanya.com"])
            },
            "proposal_settings": {
                "proposed_workshare_pct": workshare_pct,
                "relationship_type": "Subcontracting Partner"
            },
            "pitch_outreach": {
                "subject": f"Subcontracting Partnership Proposal: VA/DHS Solicitation {sol_num} - Orbit Avanya & {winner_name}",
                "narrative": outreach_text
            },
            "gap_analysis": gap_analysis,
            "fit_scoring": fit_scoring,
            "implementation_strategy": implementation_strategy,
            "commercial_proposal": commercial_proposal,
            "why_us": why_us,
            "next_steps": next_steps,
            "evaluation_criteria": evaluation_criteria,
            "competitors": cleaned_competitors,
            "alignment_matrices": {
                "prime_sub_responsibility_matrix": alignment_matrix,
                "technical_capabilities": tech_alignment,
                "security_compliance": security_alignment,
                "subcontractor_work_share_breakdown": work_breakdown
            }
        }

        # Save proposal JSON to E:/MIT WPU/MIT WPU Subjects/7th_Sem/Orbit/PPT-Agent/output/proposals/
        output_dir = self.project_root / "output" / "proposals"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{sol_num}_pitch_data.json"
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(proposal, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Proposal teaming pitch JSON successfully saved to: {output_path}")
        return proposal
