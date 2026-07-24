"""
documents/template_analyzer.py
-------------------------------
Extracts branding assets from user-uploaded .docx templates.
The template is used ONLY as a branding reference — logos, colors,
fonts, header/footer design. A new document is always generated from scratch
using these extracted brand assets.

This prevents the 'fill-in-the-blank' problem where templates get
mangled by content injection.
"""

from __future__ import annotations

import logging
import re
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class BrandProfile:
    """
    Brand profile extracted from a user template or built from defaults.
    Drives document generation without modifying the original template.
    """
    # Fonts
    body_font: str = "Calibri"
    heading_font: str = "Calibri"

    # Colors (hex, no '#')
    accent_color: str = "1F3864"
    muted_color: str = "595959"
    heading_color: str = "1F3864"

    # Page setup
    page_width_inches: float = 8.5
    page_height_inches: float = 11.0
    left_margin_inches: float = 0.75
    right_margin_inches: float = 0.75
    top_margin_inches: float = 0.9
    bottom_margin_inches: float = 0.9

    # Logo (extracted to bytes so it can be embedded in new doc)
    logo_bytes: Optional[bytes] = None
    logo_width_inches: float = 1.2

    # Cover graphic
    cover_graphic_bytes: Optional[bytes] = None

    # Company info extracted from template
    company_name: str = "OrbitAvanya Tech LLP"
    website: str = ""
    address_line1: str = ""
    address_line2: str = ""
    phone: str = ""
    email: str = ""

    # Leadership names/titles found in the template, e.g. [{"name": "...", "title": "..."}]
    leadership: List[Dict[str, str]] = field(default_factory=list)

    # Header/footer text patterns
    header_text: str = ""
    footer_text: str = ""

    # Raw text of the template's first page (everything before the first
    # explicit page/section break, or the whole document if none is found).
    # Used both for first-page preservation and as AI context so the model
    # knows what's already on the cover/registration page and doesn't
    # re-invent or contradict it.
    first_page_text: str = ""

    # Source: 'template' | 'default'
    source: str = "default"

    def to_brand_config_dict(self) -> Dict[str, Any]:
        """Convert to the brand config dict format used by proposal_generator."""
        import tempfile
        import os

        logo_path = ""
        cover_path = ""

        out_dir = Path("downloads") / "extracted"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Save logo bytes to designated file if available
        if self.logo_bytes:
            try:
                target_logo = out_dir / "logo.png"
                target_logo.write_bytes(self.logo_bytes)
                logo_path = str(target_logo.resolve())
            except Exception as e:
                logger.warning(f"Could not save extracted logo: {e}")

        if self.cover_graphic_bytes:
            try:
                target_cover = out_dir / "cover.png"
                target_cover.write_bytes(self.cover_graphic_bytes)
                cover_path = str(target_cover.resolve())
            except Exception as e:
                logger.warning(f"Could not save cover graphic: {e}")

        return {
            "company_name": self.company_name,
            "company_short": self.company_name.split()[0] if self.company_name else "Company",
            "logo_path": logo_path,
            "cover_graphic_path": cover_path,
            "body_font": self.body_font,
            "heading_font": self.heading_font,
            "accent_color": self.accent_color,
            "muted_color": self.muted_color,
            "address_line1": self.address_line1,
            "address_line2": self.address_line2,
            "phone": self.phone,
            "email": self.email,
            "website": self.website,
            "leadership": self.leadership,
            "first_page_text": self.first_page_text,
        }

    def to_company_profile_summary(self) -> str:
        """Plain-language summary of everything we could extract from the
        template, meant to be dropped straight into an AI prompt as context
        so the model knows the company's real contact details / leadership
        instead of inventing or contradicting them."""
        lines = [f"Company name: {self.company_name}" if self.company_name else ""]
        if self.website:
            lines.append(f"Website: {self.website}")
        if self.email:
            lines.append(f"Email: {self.email}")
        if self.phone:
            lines.append(f"Phone: {self.phone}")
        if self.address_line1 or self.address_line2:
            lines.append(f"Address: {', '.join(x for x in [self.address_line1, self.address_line2] if x)}")
        if self.leadership:
            names = "; ".join(f"{p.get('name', '')} ({p.get('title', '')})" for p in self.leadership if p.get("name"))
            if names:
                lines.append(f"Leadership: {names}")
        return "\n".join(l for l in lines if l)


class TemplateAnalyzer:
    """
    Analyzes a user-uploaded .docx template to extract brand assets.
    Does NOT modify the template.
    """

    def __init__(self, template_path: str | Path):
        self.template_path = Path(template_path)
        self._doc = None

    def _load_doc(self):
        """Lazy-load the template document."""
        if self._doc is None:
            from docx import Document
            self._doc = Document(str(self.template_path))
        return self._doc

    def analyze(self) -> BrandProfile:
        """
        Extract all branding information from the template.
        Returns a BrandProfile with all available brand data.
        """
        profile = BrandProfile(source="template")

        if not self.template_path.exists():
            logger.warning(f"Template not found: {self.template_path}. Using defaults.")
            profile.source = "default"
            return profile

        try:
            doc = self._load_doc()

            self._extract_fonts(doc, profile)
            self._extract_colors(doc, profile)
            self._extract_margins(doc, profile)
            self._extract_logo(doc, profile)
            self._extract_header_footer(doc, profile)
            self._extract_contact_details(doc, profile)
            self._extract_leadership(doc, profile)
            self._extract_first_page_text(doc, profile)

            logger.info(
                f"[TemplateAnalyzer] Extracted brand from '{self.template_path.name}': "
                f"font={profile.body_font}, accent=#{profile.accent_color}"
            )
        except Exception as e:
            logger.error(f"[TemplateAnalyzer] Failed to analyze template: {e}")
            profile.source = "default_fallback"

        return profile

    def _extract_fonts(self, doc, profile: BrandProfile):
        """Extract primary font from the template's paragraph styles."""
        try:
            font_counts: Dict[str, int] = {}
            for para in doc.paragraphs[:50]:  # Sample first 50 paragraphs
                for run in para.runs:
                    fn = run.font.name
                    if fn and not fn.startswith("+"):
                        font_counts[fn] = font_counts.get(fn, 0) + 1

            if font_counts:
                # Most common font = body font
                body = max(font_counts, key=lambda k: font_counts[k])
                profile.body_font = body

            # Check heading styles for heading font
            for para in doc.paragraphs:
                if para.style and "heading" in para.style.name.lower():
                    for run in para.runs:
                        if run.font.name and not run.font.name.startswith("+"):
                            profile.heading_font = run.font.name
                            break
                    break

            if not profile.heading_font or profile.heading_font == "Calibri":
                profile.heading_font = profile.body_font
        except Exception as e:
            logger.debug(f"Font extraction error: {e}")

    def _extract_colors(self, doc, profile: BrandProfile):
        """Extract accent color from heading styles or bold text."""
        try:
            for para in doc.paragraphs[:100]:
                if para.style and "heading" in para.style.name.lower():
                    for run in para.runs:
                        if run.font.color and run.font.color.type is not None:
                            try:
                                rgb = run.font.color.rgb
                                if rgb:
                                    hex_color = str(rgb)
                                    # Avoid very light or white colors
                                    if hex_color not in ('FFFFFF', 'ffffff', '000000'):
                                        profile.accent_color = hex_color
                                        profile.heading_color = hex_color
                                        return
                            except Exception:
                                pass
        except Exception as e:
            logger.debug(f"Color extraction error: {e}")

    def _extract_margins(self, doc, profile: BrandProfile):
        """Extract page margins from the template's section settings."""
        try:
            from docx.shared import Inches
            section = doc.sections[0]
            emu_per_inch = 914400

            if section.left_margin:
                profile.left_margin_inches = round(section.left_margin / emu_per_inch, 2)
            if section.right_margin:
                profile.right_margin_inches = round(section.right_margin / emu_per_inch, 2)
            if section.top_margin:
                profile.top_margin_inches = round(section.top_margin / emu_per_inch, 2)
            if section.bottom_margin:
                profile.bottom_margin_inches = round(section.bottom_margin / emu_per_inch, 2)
            if section.page_width:
                profile.page_width_inches = round(section.page_width / emu_per_inch, 2)
            if section.page_height:
                profile.page_height_inches = round(section.page_height / emu_per_inch, 2)
        except Exception as e:
            logger.debug(f"Margin extraction error: {e}")

    def _extract_logo(self, doc, profile: BrandProfile):
        """Extract logo image from the template header."""
        try:
            for section in doc.sections:
                for header in (section.header, section.first_page_header):
                    if header is None:
                        continue
                    for para in header.paragraphs:
                        for run in para.runs:
                            for shape in run._r.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip'):
                                embed = shape.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                                if embed:
                                    try:
                                        img_part = doc.part.related_parts.get(embed)
                                        if img_part:
                                            profile.logo_bytes = img_part.blob
                                            logger.info("[TemplateAnalyzer] Extracted logo from header.")
                                            return
                                    except Exception:
                                        pass
        except Exception as e:
            logger.debug(f"Logo extraction error: {e}")

    def _extract_header_footer(self, doc, profile: BrandProfile):
        """Extract text content from template header and footer."""
        try:
            section = doc.sections[0]
            if section.header:
                texts = [p.text.strip() for p in section.header.paragraphs if p.text.strip()]
                profile.header_text = " | ".join(texts)
            if section.footer:
                texts = [p.text.strip() for p in section.footer.paragraphs if p.text.strip()]
                profile.footer_text = " | ".join(texts)
                # Try to extract company name, website from footer
                for text in texts:
                    if 'www.' in text or '.com' in text:
                        profile.website = text.strip()
        except Exception as e:
            logger.debug(f"Header/footer extraction error: {e}")


    _EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
    _PHONE_RE = re.compile(r"(\+?\d[\d\-\.\(\) ]{7,}\d)")
    _WEBSITE_RE = re.compile(r"(?:https?://)?(?:www\.)?[A-Za-z0-9\-]+\.[A-Za-z]{2,}(?:/\S*)?")
    _LEADERSHIP_TITLE_RE = re.compile(
        r"\b(Chief Executive Officer|CEO|Chief Operating Officer|COO|Chief Technology Officer|CTO|"
        r"Chief Financial Officer|CFO|President|Founder|Co-Founder|Managing Director|Director|"
        r"Vice President|VP|Owner|Principal|Partner)\b",
        re.IGNORECASE,
    )

    def _all_text_paragraphs(self, doc) -> List[str]:
        """Collect paragraph text from the body plus every header/footer,
        since contact/leadership details commonly live in either place."""
        texts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        for section in doc.sections:
            for part in (section.header, section.footer, section.first_page_header, section.first_page_footer):
                if part is None:
                    continue
                texts.extend(p.text for p in part.paragraphs if p.text and p.text.strip())
        return texts

    def _extract_contact_details(self, doc, profile: BrandProfile):
        """Extract email/phone/website from anywhere in the template (body,
        headers, footers) using regexes, so the AI has real contact details
        to reference instead of inventing them."""
        try:
            all_text = "\n".join(self._all_text_paragraphs(doc))

            email_match = self._EMAIL_RE.search(all_text)
            if email_match:
                profile.email = email_match.group(0)

            if not profile.website:
                for candidate in self._WEBSITE_RE.finditer(all_text):
                    val = candidate.group(0)
                    # Skip false positives that are actually the email domain
                    if profile.email and val in profile.email:
                        continue
                    if "www." in val.lower() or val.lower().endswith((".com", ".org", ".net", ".io", ".co")):
                        profile.website = val
                        break

            if not profile.phone:
                phone_match = self._PHONE_RE.search(all_text)
                if phone_match:
                    candidate = phone_match.group(1).strip()
                    # Guard against matching things like ZIP+4 or plain long numbers
                    digit_count = sum(c.isdigit() for c in candidate)
                    if 7 <= digit_count <= 15:
                        profile.phone = candidate
        except Exception as e:
            logger.debug(f"Contact detail extraction error: {e}")

    def _extract_leadership(self, doc, profile: BrandProfile):
        """Heuristically find 'Name — Title' / 'Title: Name' patterns that
        reference common leadership titles (CEO, President, Founder, ...)."""
        try:
            leadership: List[Dict[str, str]] = []
            seen = set()
            for text in self._all_text_paragraphs(doc):
                title_match = self._LEADERSHIP_TITLE_RE.search(text)
                if not title_match:
                    continue
                title = title_match.group(0)

                # "Name — Title" / "Name, Title" / "Title: Name" / "Name (Title)"
                name = ""
                for sep in ("—", "-", ",", "(", ":"):
                    if sep not in text:
                        continue
                    left, _, right = text.partition(sep)
                    for candidate_raw in (left, right):
                        candidate = candidate_raw.strip(" ()").strip()
                        # Skip whichever side contains the matched title text itself
                        if title.lower() in candidate.lower():
                            continue
                        words = candidate.split()
                        # A plausible person name: 2-4 capitalized words, no digits
                        if 1 < len(words) <= 4 and all(w[:1].isupper() for w in words if w) and not any(c.isdigit() for c in candidate):
                            name = candidate
                            break
                    if name:
                        break

                if name and (name, title) not in seen:
                    seen.add((name, title))
                    leadership.append({"name": name, "title": title})

            profile.leadership = leadership[:5]
        except Exception as e:
            logger.debug(f"Leadership extraction error: {e}")

    def _extract_first_page_text(self, doc, profile: BrandProfile):
        """Capture the raw text of everything before the first explicit page
        break (or the whole document if no page break is found), so it can be
        both preserved verbatim and summarized as AI context."""
        try:
            from documents.bidforge.first_page_preserver import iter_first_page_paragraph_texts
            texts = list(iter_first_page_paragraph_texts(doc))
            profile.first_page_text = "\n".join(t for t in texts if t.strip())
        except Exception as e:
            logger.debug(f"First-page text extraction error: {e}")


def analyze_template(template_path: str | Path) -> BrandProfile:
    """Convenience function to analyze a template and return its BrandProfile."""
    return TemplateAnalyzer(template_path).analyze()


def get_default_brand_profile() -> BrandProfile:
    """Return the default OrbitAvanya brand profile."""
    from documents.brand_config import get_brand_config, PROJECT_ROOT
    cfg = get_brand_config()

    profile = BrandProfile(source="default")
    profile.body_font = cfg.get("body_font", "Calibri")
    profile.heading_font = cfg.get("heading_font", "Calibri")
    profile.accent_color = cfg.get("accent_color", "1F3864")
    profile.muted_color = cfg.get("muted_color", "595959")
    profile.company_name = cfg.get("company_name", "OrbitAvanya Tech LLP")
    profile.website = cfg.get("website", "")
    profile.address_line1 = cfg.get("address_line1", "")
    profile.address_line2 = cfg.get("address_line2", "")
    profile.phone = cfg.get("phone", "")

    # Load logo bytes from disk
    logo_path = cfg.get("logo_path", "")
    if logo_path and Path(logo_path).exists():
        try:
            profile.logo_bytes = Path(logo_path).read_bytes()
        except Exception:
            pass

    cover_path = cfg.get("cover_graphic_path", "")
    if cover_path and Path(cover_path).exists():
        try:
            profile.cover_graphic_bytes = Path(cover_path).read_bytes()
        except Exception:
            pass

    return profile
