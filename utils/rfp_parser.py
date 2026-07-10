import os
import re
from pathlib import Path
from typing import Dict, List, Any
import pypdf

# Try importing fitz (PyMuPDF) if available, fall back to pypdf
try:
    import fitz
    USE_MUPDF = True
except ImportError:
    USE_MUPDF = False

from utils.helpers import setup_logger

logger = setup_logger(__name__)

# Keywords for rule-based matching
SECURITY_PATTERNS = {
    "VA Handbook 6500.6": r"6500\.6|handbook\s+6500",
    "Appendix C Compliance": r"appendix\s+c",
    "HIPAA/HITECH": r"hipaa|hitech|health\s+insurance\s+portability",
    "Information Security & Privacy": r"information\s+security|privacy\s+language|privacy\s+act",
    "Personnel Background Investigation": r"background\s+investigation|background\s+check|clearance",
    "Audit Logging & Monitoring": r"audit\s+log|logging|monitoring",
    "FIPS 140 Encryption": r"fips\s*(140|201)|encryption|aes",
    "NIST Guidelines": r"nist|special\s+publication|800-53"
}

TECHNICAL_PATTERNS = {
    "OR Integration System": r"or\s+integration|operating\s+room\s+integration|6515",
    "Surgical Equipment Interfaces": r"surgical|operating\s+room|endoscope|camera|display",
    "API & Software Integration": r"api\s+integration|software\s+interface|web\s+service|connector",
    "Database Management": r"database|sql|postgresql|mongodb|data\s+store",
    "Network & Video Routing": r"video\s+routing|audio|telecom|network|switch|fiber",
    "Role-Based Access Control": r"role\s+based|rbac|access\s+control|permission"
}

LAYOUT_PATTERNS = {
    "Telecom Room": r"telecom|telecommunication|communication\s+closet",
    "Electrical Room": r"electrical|power\s+room|breaker",
    "Floor/Structural Layout": r"floor\s+plan|structural|braced\s+frame|beam|column",
    "5th & 6th Floor Focus": r"5th\s+floor|6th\s+floor|5-6th|fifth|sixth"
}

class RFPParser:
    """
    Extracts text from RFP PDF files and parses requirements using rule-based/pattern-based matching.
    """

    def __init__(self, solicitation_number: str, project_root: str = "E:/MIT WPU/MIT WPU Subjects/7th_Sem/Orbit/PPT-Agent"):
        self.solicitation_number = solicitation_number
        self.project_root = Path(project_root)
        self.rfp_docs_dir = self.project_root / "downloads" / "opportunities" / solicitation_number / "rfp_docs"

    def extract_text_from_pdfs(self) -> Dict[str, str]:
        """Reads all PDF documents in the solicitation directory and extracts their text."""
        extracted_text = {}
        if not self.rfp_docs_dir.exists():
            logger.warning(f"RFP docs directory not found: {self.rfp_docs_dir}")
            return extracted_text

        pdf_files = list(self.rfp_docs_dir.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files in {self.rfp_docs_dir}")

        for pdf_path in pdf_files:
            filename = pdf_path.name
            logger.info(f"Extracting text from: {filename}")
            text = ""
            
            if USE_MUPDF:
                try:
                    doc = fitz.open(pdf_path)
                    text_pages = [str(page.get_text()) for page in doc]
                    text = "\n\n".join(text_pages)
                    doc.close()
                except Exception as e:
                    logger.error(f"PyMuPDF failed to extract {filename}: {e}. Falling back to pypdf.")
                    
            if not text:
                try:
                    reader = pypdf.PdfReader(pdf_path)
                    text_pages = []
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_pages.append(page_text)
                    text = "\n\n".join(text_pages)
                except Exception as e:
                    logger.error(f"pypdf failed to extract {filename}: {e}")

            extracted_text[filename] = text
        return extracted_text

    def parse_requirements(self, doc_texts: Dict[str, str]) -> Dict[str, Any]:
        """Scans extracted text for patterns and classifies findings into a structured dict."""
        parsed_data = {
            "solicitation_number": self.solicitation_number,
            "security_requirements": [],
            "technical_requirements": [],
            "facility_requirements": [],
            "identified_components": {
                "security": [],
                "technical": [],
                "layout": []
            },
            "summary": ""
        }

        # Combine text for holistic matching
        combined_text = "\n\n".join(doc_texts.values())
        combined_text_lower = combined_text.lower()

        # 1. Match Security Requirements
        for name, pattern in SECURITY_PATTERNS.items():
            if re.search(pattern, combined_text_lower):
                parsed_data["identified_components"]["security"].append(name)
                # Formulate a structured rule
                parsed_data["security_requirements"].append({
                    "standard": name,
                    "requirement_desc": f"Ensure compliance with {name} as specified in solicitation guidelines.",
                    "status": "Required"
                })

        # 2. Match Technical Requirements
        for name, pattern in TECHNICAL_PATTERNS.items():
            if re.search(pattern, combined_text_lower):
                parsed_data["identified_components"]["technical"].append(name)
                parsed_data["technical_requirements"].append({
                    "capability": name,
                    "requirement_desc": f"Implementation requires core competency in {name}.",
                    "status": "Required"
                })

        # 3. Match Layout/Facility requirements
        for name, pattern in LAYOUT_PATTERNS.items():
            if re.search(pattern, combined_text_lower):
                parsed_data["identified_components"]["layout"].append(name)
                parsed_data["facility_requirements"].append({
                    "feature": name,
                    "requirement_desc": f"Project involves coordinate alignment with {name}.",
                    "status": "Required"
                })

        # 4. Generate structured heuristics based on document specifics
        if "Attachment+A+-+VA+SECURITY+LANGUAGE.pdf" in doc_texts:
            parsed_data["security_requirements"].append({
                "standard": "VA Security Handbook 6500.6 Appendix C",
                "requirement_desc": "Contractor personnel must pass background investigations and complete annual security awareness training. Data must reside securely in certified facilities.",
                "status": "Required"
            })

        # Heuristic layout extraction from drawing text files
        rooms_found = []
        for filename, text in doc_texts.items():
            if "Arch" in filename or "Structural" in filename:
                # Scan for room numbers/labels
                matches = re.findall(r"\b(5B\d{2}[A-Z]?|5D\d{2}[A-Z]?|5E\d{2}[A-Z]?|Operating Room|TELECOM|ELECTRICAL)\b", text, re.IGNORECASE)
                if matches:
                    rooms_found.extend(list(set(matches)))
        
        if rooms_found:
            dedup_rooms = sorted(list(set(rooms_found)))[:10]  # Cap at 10 items
            parsed_data["facility_requirements"].append({
                "feature": "Identified Rooms & Areas",
                "requirement_desc": f"Design maps and floor layouts specify integration zones in: {', '.join(dedup_rooms)}.",
                "status": "Information"
            })

        # 5. Build summary narrative
        tech_list = parsed_data["identified_components"]["technical"]
        sec_list = parsed_data["identified_components"]["security"]
        
        # Dynamically determine the RFP subject domain based on keywords in extracted text
        all_text = " ".join(doc_texts.values()).lower()
        
        subject_title = "an Enterprise Systems & Integration Project"
        if "surgical" in all_text or "operating room" in all_text or "hospital" in all_text or "clinical" in all_text or "6515" in all_text:
            subject_title = "an OR Integration System (operating room integration)"
        elif "financial" in all_text or "predictive" in all_text or "modeling" in all_text or "fema" in all_text or "disaster" in all_text:
            subject_title = "an Enterprise Financial Analysis & Predictive Modeling System"
        elif "learning" in all_text or "lms" in all_text or "student" in all_text or "course" in all_text:
            subject_title = "a Learning Management System (LMS)"
        elif "support" in all_text or "helpdesk" in all_text or "ticket" in all_text:
            subject_title = "a Help Desk & Support Portal"
        elif "website" in all_text or "wcms" in all_text or "content management" in all_text:
            subject_title = "a Corporate Website & Content Management Solution"
            
        summary = f"Solicitation {self.solicitation_number} is for {subject_title}. "
        if tech_list:
            summary += f"Technical requirements highlight: {', '.join(tech_list)}. "
        if sec_list:
            summary += f"Security compliance mandates: {', '.join(sec_list)}."
            
        parsed_data["summary"] = summary.strip()
        
        return parsed_data

def run_parser_test():
    """Diagnostic function to test the parser locally."""
    parser = RFPParser("36C24626Q0420")
    texts = parser.extract_text_from_pdfs()
    print("Files read:", list(texts.keys()))
    results = parser.parse_requirements(texts)
    import json
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    run_parser_test()
