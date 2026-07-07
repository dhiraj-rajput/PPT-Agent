"""
website/classifier.py
---------------------
Classify cleaned page text into named business sections using keyword scoring.
Used downstream by the extractor to assign meaning to raw text blocks.
"""

from typing import Dict, List
import re

SECTION_KEYWORDS: Dict[str, List[str]] = {
    "Company Overview": [
        "about", "overview", "who we are", "what we do", "mission", "vision", "our story",
        "history", "founded", "profile", "about us", "background", "purpose", "value"
    ],
    "Products": [
        "product", "software", "hardware", "feature", "platform", "solution", "tool", "saas",
        "pricing", "subscription", "offering", "release", "app", "application"
    ],
    "Services": [
        "service", "consulting", "support", "training", "implementation", "maintenance",
        "custom development", "professional service", "advisor", "managed service", "enablement"
    ],
    "Industries": [
        "industry", "sector", "vertical", "finance", "healthcare", "education", "retail",
        "government", "manufacturing", "automotive", "telecom", "energy", "real estate", "market"
    ],
    "Leadership": [
        "leadership", "management", "executive", "board", "director", "founder", "ceo", "cto",
        "cfo", "team", "president", "vp", "officer", "people", "advisor"
    ],
    "Locations": [
        "location", "headquarter", "office", "address", "branch", "global office",
        "where we are", "map", "contact info"
    ],
    "Contact": [
        "contact", "get in touch", "support", "email us", "call us", "phone",
        "inquiry", "sales", "request info", "reach us"
    ],
    "Technology": [
        "technology", "tech stack", "infrastructure", "architecture", "security", "integration",
        "api", "developer", "open source", "compliance", "data security", "framework"
    ],
    "Partners": [
        "partner", "alliance", "ecosystem", "reseller", "integrator", "channel partner",
        "collaborator", "network", "channel"
    ],
    "Clients": [
        "client", "customer", "case study", "testimonial", "success story", "trusted by",
        "our user", "patron", "reference"
    ],
    "Careers": [
        "career", "job", "work with us", "hiring", "open role", "position", "culture",
        "internship", "employment", "join us"
    ],
    "Blogs": [
        "blog", "news", "press release", "article", "newsletter", "update", "media", "insight",
        "publication", "announcement"
    ],
}


def classify_text_by_sections(clean_text: str) -> Dict[str, List[str]]:
    """
    Classify lines/paragraphs of clean text into distinct business sections.
    Uses keyword matching and context tracking to assign meaning.

    Args:
        clean_text: Main body text from all crawled pages.

    Returns:
        Dict mapping section name → list of matching paragraphs.
    """
    classified_data: Dict[str, List[str]] = {sec: [] for sec in SECTION_KEYWORDS}
    if not clean_text:
        return classified_data

    paragraphs = [p.strip() for p in clean_text.split("\n") if p.strip()]
    current_section = "Company Overview"

    for p in paragraphs:
        p_lower = p.lower()
        is_header = False

        # Check short paragraphs as potential section headers
        if len(p) < 60:
            for section, keywords in SECTION_KEYWORDS.items():
                for kw in keywords:
                    if p_lower == kw or p_lower.startswith(kw + " ") or p_lower.endswith(" " + kw):
                        current_section = section
                        is_header = True
                        break
                if is_header:
                    break

        if not is_header:
            best_section = current_section
            max_score = 0
            for section, keywords in SECTION_KEYWORDS.items():
                score = sum(
                    len(re.findall(r'\b' + re.escape(kw) + r'\b', p_lower))
                    for kw in keywords
                )
                if score > max_score:
                    max_score = score
                    best_section = section
            if max_score >= 2:
                current_section = best_section

        if p not in classified_data[current_section]:
            classified_data[current_section].append(p)

    return classified_data
