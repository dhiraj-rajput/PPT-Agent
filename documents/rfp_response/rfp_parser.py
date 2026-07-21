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

# OCR (only needed for scanned/image-only pages — soft dependency)
try:
    import pytesseract  # type: ignore
    from PIL import Image
    import io as _io
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

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

    def __init__(self, solicitation_number: str, project_root: str = str(Path(__file__).resolve().parent.parent.parent)):
        self.solicitation_number = solicitation_number
        self.project_root = Path(project_root)
        self.rfp_docs_dir = self.project_root / "downloads" / "opportunities" / solicitation_number / "rfp_docs"

    def extract_text_from_pdfs(self) -> Dict[str, str]:
        """
        Reads ALL RFP documents (PDFs, Images, Word docs, Text) in the solicitation
        directory and extracts their text using the unified OCR pipeline.
        """
        extracted_text = {}
        if not self.rfp_docs_dir.exists():
            logger.warning(f"RFP docs directory not found: {self.rfp_docs_dir}")
            return extracted_text

        # Support PDFs, Images, Word docs, HTML, Text
        valid_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".docx", ".doc", ".txt", ".html"}
        doc_files = [f for f in self.rfp_docs_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_extensions]
        logger.info(f"Found {len(doc_files)} RFP document files in {self.rfp_docs_dir}")

        from pipeline.ocr.ocr_manager import get_ocr_manager
        ocr_mgr = get_ocr_manager()

        for doc_path in doc_files:
            filename = doc_path.name
            logger.info(f"Extracting text from: {filename}")
            try:
                ocr_result = ocr_mgr.extract(doc_path)
                text = ocr_result.get("text", "")
                if not text.strip() and doc_path.suffix.lower() == ".pdf":
                    # Fallback to single PDF extractor if OCR manager returned empty
                    text = self._extract_text_from_single_pdf(doc_path)
                extracted_text[filename] = text
            except Exception as e:
                logger.error(f"Failed to extract text from {filename}: {e}")
                if doc_path.suffix.lower() == ".pdf":
                    extracted_text[filename] = self._extract_text_from_single_pdf(doc_path)

        return extracted_text

    def _extract_text_from_single_pdf(self, pdf_path: Path) -> str:
        """Extract text page-by-page, OCR'ing any page whose text layer is
        too thin to be a real extraction (scanned page, image-only page)."""
        from config.settings import settings
        ocr_enabled = getattr(settings, "OCR_ENABLED", True) and _OCR_AVAILABLE and USE_MUPDF
        min_chars = getattr(settings, "OCR_MIN_CHARS_PER_PAGE", 40)

        page_texts: List[str] = []
        ocr_page_count = 0

        if USE_MUPDF:
            try:
                doc: Any = fitz.open(pdf_path)
                for page_index, page in enumerate(doc):
                    page_text = str(page.get_text()) or ""
                    if len(page_text.strip()) < min_chars:
                        if ocr_enabled:
                            ocr_text = self._ocr_page(page)
                            if ocr_text.strip():
                                ocr_page_count += 1
                                page_text = ocr_text
                    page_texts.append(page_text)
                doc.close()
                if ocr_page_count:
                    logger.info(f"[RFPParser] OCR'd {ocr_page_count} scanned/image page(s) in {pdf_path.name}")
                return "\n\n".join(page_texts)
            except Exception as e:
                logger.error(f"PyMuPDF failed to extract {pdf_path.name}: {e}. Falling back to pypdf.")

        # pypdf fallback (no per-page OCR available here — pypdf has no rasterizer)
        try:
            reader = pypdf.PdfReader(pdf_path)
            for page in reader.pages:
                pt = page.extract_text()
                if pt:
                    page_texts.append(pt)
            return "\n\n".join(page_texts)
        except Exception as e:
            logger.error(f"pypdf failed to extract {pdf_path.name}: {e}")
            return ""

    @staticmethod
    def _ocr_page(fitz_page, dpi: int = 200) -> str:
        """Rasterize a single PyMuPDF page and run Tesseract OCR on it."""
        try:
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            pix = fitz_page.get_pixmap(matrix=matrix)
            img = Image.open(_io.BytesIO(pix.tobytes("png")))
            return pytesseract.image_to_string(img)
        except Exception as e:
            logger.warning(f"[RFPParser] OCR failed for a page: {e}")
            return ""

    def parse_requirements(self, doc_texts: Dict[str, str]) -> Dict[str, Any]:
        """
        Parses extracted RFP text into a structured requirements dict.
        Governed by the global AI_MODE toggle (RFP_PARSER_MODE override):
        tries AI comprehension first (understands intent/context, not just
        keyword matches), automatically falls back to the deterministic
        regex-pattern parser on failure or 429 rate-limit.
        """
        from pipeline.ai.mode import run_with_fallback

        parsed_data, path_used = run_with_fallback(
            "rfp_parser",
            ai_fn=lambda: self._parse_requirements_ai(doc_texts),
            rule_fn=lambda: self._parse_requirements_rules(doc_texts),
        )
        parsed_data["parsed_via"] = path_used
        logger.info(f"[RFPParser] Requirements parsed via '{path_used}' path.")
        return parsed_data

    def _parse_requirements_ai(self, doc_texts: Dict[str, str]) -> Dict[str, Any]:
        """
        Uses the LLM to actually read and understand the RFP text (rather
        than pattern-match against a fixed keyword list), producing the
        same structured shape as the rule-based parser so downstream code
        (rfp_response_generator, pdf rendering) doesn't need to change.
        """
        from pipeline.ai.client import get_ai_client

        combined_text = "\n\n".join(doc_texts.values())
        # Ollama Cloud context is generous but not unlimited — trim conservatively.
        text_sample = combined_text[:24000]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a government-contracting RFP analyst. Read the solicitation text and "
                    "extract a structured requirements summary. Respond ONLY with a JSON object with keys: "
                    "metadata (object: issuing_agency, project_title, naics_code, deadline, set_aside), "
                    "security_requirements (array of {standard, requirement_desc, status}), "
                    "technical_requirements (array of {capability, requirement_desc, status}), "
                    "facility_requirements (array of {feature, requirement_desc, status}), "
                    "summary (2-4 sentence plain-English summary of what is being solicited). "
                    "status should be one of 'Required', 'Optional', 'Information'. "
                    "Base everything strictly on the provided text — do not invent requirements."
                ),
            },
            {"role": "user", "content": f"Solicitation {self.solicitation_number} text:\n\n{text_sample}"},
        ]
        ai_result = get_ai_client().chat_json(messages)

        security = ai_result.get("security_requirements", []) or []
        technical = ai_result.get("technical_requirements", []) or []
        facility = ai_result.get("facility_requirements", []) or []
        metadata = {
            "solicitation_number": self.solicitation_number,
            "issuing_agency": "Federal Agency",
            "project_title": "Enterprise Software Engagement",
            "naics_code": "541511",
            "deadline": "N/A",
            "set_aside": "N/A",
        }
        metadata.update({k: v for k, v in (ai_result.get("metadata") or {}).items() if v})

        return {
            "solicitation_number": self.solicitation_number,
            "metadata": metadata,
            "security_requirements": security,
            "technical_requirements": technical,
            "facility_requirements": facility,
            "identified_components": {
                "security": [r.get("standard", "") for r in security if r.get("standard")],
                "technical": [r.get("capability", "") for r in technical if r.get("capability")],
                "layout": [r.get("feature", "") for r in facility if r.get("feature")],
            },
            "summary": ai_result.get("summary", ""),
        }

    def _parse_requirements_rules(self, doc_texts: Dict[str, str]) -> Dict[str, Any]:
        """Scans extracted text for patterns and classifies findings into a structured dict."""
        parsed_data = {
            "solicitation_number": self.solicitation_number,
            "metadata": {
                "solicitation_number": self.solicitation_number,
                "issuing_agency": "Federal Agency",
                "project_title": "Enterprise Software Engagement",
                "naics_code": "541511",
                "deadline": "N/A",
                "set_aside": "N/A"
            },
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
        
        # Populate metadata dynamically
        agency = "Federal Agency"
        if "veteran" in all_text or "department of veterans" in all_text:
            agency = "Department of Veterans Affairs"
        elif "homeland" in all_text or "dhs" in all_text:
            agency = "Department of Homeland Security"
        elif "defense" in all_text or "navy" in all_text or "dod" in all_text or "military" in all_text:
            agency = "Department of Defense"
            
        parsed_data["metadata"]["issuing_agency"] = agency
        parsed_data["metadata"]["project_title"] = subject_title
        
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
