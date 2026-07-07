"""
website/extractor.py
--------------------
Extracts structured CompanyIntelligence from cleaned website text
using a rule-based (regex + heuristic) approach.

Input: cleaned text blocks, classified sections, contact info, page metadata.
Output: WebsiteData Pydantic model.
"""

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

from utils.helpers import setup_logger
from website.models import WebsiteData

logger = setup_logger(__name__)

# Technology keywords to detect from page text
TECH_KEYWORDS = [
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go", "Rust", "Kotlin", "Swift",
    "React", "Angular", "Vue", "Next.js", "Node.js", "Django", "FastAPI", "Flask", "Spring",
    "AWS", "Azure", "GCP", "Google Cloud", "Kubernetes", "Docker", "Terraform", "Ansible",
    "TensorFlow", "PyTorch", "OpenAI", "Vertex AI", "LangChain",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Snowflake", "Databricks", "Spark",
    "Kafka", "RabbitMQ", "Elasticsearch", "GraphQL", "REST API",
    "ISO 27001", "SOC 2", "GDPR", "HIPAA", "PCI DSS",
]


def get_domain(url: str) -> str:
    """Extract bare domain from URL (no www prefix)."""
    try:
        domain = urlparse(url).netloc
        return domain[4:] if domain.startswith("www.") else domain
    except Exception:
        return ""


def extract_company_intelligence(
    homepage_url: str,
    company_slug: str,
    page_metadata: Dict[str, Dict[str, str]],
    combined_clean_text: str,
    combined_raw_text: str,
    classified_sections: Dict[str, List[str]],
    aggregated_contacts: Dict,
    discovered_pages: Dict[str, str],
    social_links: List[str],
    visited_urls: List[str],
    crawl_duration: float,
) -> WebsiteData:
    """
    Build a structured WebsiteData object from all crawled and classified data.

    Args:
        homepage_url:       The starting URL of the company website.
        company_slug:       Unique slug (derived from domain).
        page_metadata:      Maps URL → {title, description}.
        combined_clean_text: All pages' cleaned text joined.
        combined_raw_text:   All pages' raw text joined.
        classified_sections: Text paragraphs bucketed by section keyword.
        aggregated_contacts: Emails, phones, social links from all pages.
        discovered_pages:    Detected role pages (about, contact, careers, blog).
        social_links:        Deduplicated list of social profile links.
        visited_urls:        All successfully crawled URLs.
        crawl_duration:      Total crawl time in seconds.

    Returns:
        WebsiteData: Populated Pydantic model.
    """
    homepage_meta = page_metadata.get(homepage_url, {})

    # 1. Company name from page title
    company_name = get_domain(homepage_url).split(".")[0].capitalize()
    title = homepage_meta.get("title", "")
    if title:
        parts = re.split(r'[-|•—]', title)
        if parts and len(parts[0].strip()) > 2:
            company_name = parts[0].strip()

    # 2. Description & Industry
    description = ""
    overview_paragraphs = classified_sections.get("Company Overview", [])
    if overview_paragraphs:
        description = "\n".join(overview_paragraphs[:2])
    elif homepage_meta.get("description"):
        description = homepage_meta["description"]

    industry = _infer_industry(combined_clean_text, overview_paragraphs)

    # 3. Headquarters & Locations
    headquarters, locations = _extract_locations(classified_sections)

    # 4. Products & Services
    products = [p for p in classified_sections.get("Products", []) if len(p) < 150][:15]
    services = [p for p in classified_sections.get("Services", []) if len(p) < 150][:15]

    # 5. Technology stack
    technology_stack = _detect_tech_stack(combined_clean_text)

    # 6. Leadership names
    leadership = _extract_leadership(classified_sections)

    # 7. Clients & Partners
    clients = [p for p in classified_sections.get("Clients", []) if len(p) < 100][:15]
    partners = [p for p in classified_sections.get("Partners", []) if len(p) < 100][:15]
    industries_served = [p for p in classified_sections.get("Industries", []) if len(p) < 100][:10]

    # 8. LinkedIn URL — extract from social links
    linkedin_url = next(
        (link for link in (aggregated_contacts.get("social_links", []) + social_links)
         if "linkedin.com/company" in link.lower()),
        None
    )

    return WebsiteData(
        company_slug=company_slug,
        company_name=company_name,
        website_url=homepage_url,
        industry=industry,
        description=description,
        headquarters=headquarters,
        locations=locations[:10],
        products=products,
        services=services,
        industries_served=industries_served,
        leadership=leadership[:10],
        technology_stack=technology_stack,
        clients=clients,
        partners=partners,
        emails=aggregated_contacts.get("emails", []),
        phone_numbers=aggregated_contacts.get("phone_numbers", []),
        social_links=list(set(aggregated_contacts.get("social_links", []) + social_links)),
        linkedin_url=linkedin_url,
        careers_page=discovered_pages.get("careers", ""),
        blog_page=discovered_pages.get("blog", ""),
        about_page=discovered_pages.get("about", ""),
        contact_page=discovered_pages.get("contact", ""),
        raw_text=combined_raw_text[:50_000],   # Store first 50KB
        clean_text=combined_clean_text[:50_000],
        scraped_at=datetime.now(tz=timezone.utc),
        scrape_status="success",
        pages_crawled=len(visited_urls),
        visited_urls=visited_urls,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _infer_industry(text: str, overview_paragraphs: List[str]) -> str:
    """Infer industry from text keywords."""
    combined = (text + " ".join(overview_paragraphs)).lower()
    if any(w in combined for w in ["finance", "fintech", "payment", "banking", "transaction"]):
        return "Financial Services / Fintech"
    if any(w in combined for w in ["health", "medical", "biotech", "patient", "clinical", "hospital"]):
        return "Healthcare / Biotechnology"
    if any(w in combined for w in ["retail", "e-commerce", "shop", "ecommerce", "consumer"]):
        return "Retail / E-commerce"
    if any(w in combined for w in ["education", "edtech", "learning", "school", "course", "training"]):
        return "Education / EdTech"
    if any(w in combined for w in ["consult", "advisory", "agency", "outsourc"]):
        return "Professional Services / Consulting"
    if any(w in combined for w in ["game", "gaming", "entertainment", "stream", "media"]):
        return "Entertainment / Gaming"
    return "Technology"


def _extract_locations(classified_sections: Dict[str, List[str]]) -> tuple:
    """Extract headquarters and location list from classified section text."""
    loc_text = " ".join(
        classified_sections.get("Locations", []) +
        classified_sections.get("Contact", [])
    )
    loc_matches = re.findall(
        r'\b([A-Z][a-zA-Z\s]+,\s*[A-Z]{2,3}|[A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+)\b',
        loc_text,
    )
    # Remove common false positives
    FALSE_POSITIVES = {
        "january", "february", "march", "april", "june", "july", "august",
        "september", "october", "november", "december", "monday", "tuesday",
        "wednesday", "thursday", "friday", "saturday", "sunday",
    }
    locations = sorted({
        loc.strip() for loc in loc_matches
        if loc.strip().lower() not in FALSE_POSITIVES
    })
    headquarters = locations[0] if locations else ""
    return headquarters, locations


def _detect_tech_stack(text: str) -> List[str]:
    """Scan text for known technology keywords."""
    found = []
    for tech in TECH_KEYWORDS:
        pattern = r'\b' + re.escape(tech) + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            found.append(tech)
    return found


def _extract_leadership(classified_sections: Dict[str, List[str]]) -> List[str]:
    """Extract executive names from leadership section text."""
    leadership = []
    role_kws = ["ceo", "cto", "cfo", "founder", "president", "director",
                "vice president", "vp", "executive", "head of"]
    skip_words = {"about", "company", "leadership", "contact", "careers",
                  "products", "services", "team", "board"}

    for p in classified_sections.get("Leadership", []):
        if any(rk in p.lower() for rk in role_kws):
            matches = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', p)
            for name in matches:
                if name not in leadership and name.lower() not in skip_words and len(name) < 30:
                    leadership.append(name)
    return leadership


def identify_role_pages(urls: List[str]) -> Dict[str, str]:
    """Classify page URLs by their business roles (about, contact, careers, blog)."""
    roles = {"careers": "", "blog": "", "about": "", "contact": ""}
    for url in urls:
        path = urlparse(url).path.lower()
        if not roles["careers"] and any(k in path for k in ["career", "job", "join-us", "work-at", "employment"]):
            roles["careers"] = url
        if not roles["blog"] and any(k in path for k in ["blog", "news", "press", "media", "insight", "articles"]):
            roles["blog"] = url
        if not roles["about"] and any(k in path for k in ["about", "company", "who-we-are", "our-story", "history"]):
            roles["about"] = url
        if not roles["contact"] and any(k in path for k in ["contact", "support", "get-in-touch", "reach-us"]):
            roles["contact"] = url
    return roles
