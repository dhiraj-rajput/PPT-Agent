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
from urllib.parse import urlparse

from utils.helpers import setup_logger

from pipeline.website.models import WebsiteData

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Garbage filter — patterns that indicate UI/nav text, not real content
# ---------------------------------------------------------------------------
_GARBAGE_PATTERNS = re.compile(
    r"^(privacy|cookie|terms|disclaimer|all rights|please fill|required field|"
    r"strictly necessary|always active|performance cookies|functional cookies|"
    r"targeting cookies|your privacy|preference centre|press release template|"
    r"copyright|sign up|log in|register|subscribe|download|click here|"
    r"read more|learn more|get started|find out|explore|view all|"
    r"we use|we collect|our website|this site|this page|this document)",
    re.IGNORECASE,
)

_GARBAGE_EXACT = {
    "true", "false", "null", "undefined", "yes", "no",
    "submit", "cancel", "close", "back", "next", "menu",
    "home", "search", "contact", "about", "services", "products",
    "solutions", "platform", "pricing", "blog", "news", "careers",
    "login", "logout", "help", "support", "faq",
}


def _is_garbage(text: str) -> bool:
    """Return True if the text looks like a UI element, not real business content."""
    stripped = text.strip().lower()
    if stripped in _GARBAGE_EXACT:
        return True
    if _GARBAGE_PATTERNS.match(text.strip()):
        return True
    # Single word with no spaces is likely a nav label
    if len(stripped.split()) == 1 and len(stripped) < 10:
        return True
    # Starts with an article/lowercase word — likely mid-sentence fragment
    if re.match(r'^(and|or|but|the|a |an |to |of |in |on |at |by |for |with |from |that |this |which |when |where |how |what |who )', stripped):
        return True
    return False


def _filter_business_items(items: list[str], max_len: int = 120) -> list[str]:
    """Filter a list to keep only real business content items."""
    seen: set = set()
    result: list[str] = []
    for item in items:
        item = item.strip()
        if not item or len(item) > max_len or len(item) < 3:
            continue
        if _is_garbage(item):
            continue
        lower = item.lower()
        if lower not in seen:
            seen.add(lower)
            result.append(item)
    return result


def _is_valid_phone(value: str) -> bool:
    """Return True only for strings that look like real phone numbers."""
    stripped = re.sub(r"[\s\-\(\)\+\.]", "", value)
    # Must have at least 6 consecutive digits
    if not re.search(r"\d{6}", stripped):
        return False
    # Reject year ranges like "2021-2022" or "2021-2025"
    if re.fullmatch(r"(19|20)\d{2}[\-/](19|20)\d{2}", value.strip()):
        return False
    # Reject lone 4-digit years
    if re.fullmatch(r"(19|20)\d{2}", stripped):
        return False
    return True


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
        return domain.removeprefix("www.")
    except Exception:
        return ""


def extract_company_intelligence(
    homepage_url: str,
    company_slug: str,
    page_metadata: dict[str, dict[str, str]],
    combined_clean_text: str,
    combined_raw_text: str,
    classified_sections: dict[str, list[str]],
    aggregated_contacts: dict,
    discovered_pages: dict[str, str],
    social_links: list[str],
    visited_urls: list[str],
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

    # 4. Products & Services — apply garbage filter to remove UI/nav text fragments
    products = _filter_business_items(
        classified_sections.get("Products", []) + classified_sections.get("Technology", []),
        max_len=100,
    )[:15]
    services = _filter_business_items(
        classified_sections.get("Services", []),
        max_len=100,
    )[:15]

    # 5. Technology stack
    technology_stack = _detect_tech_stack(combined_clean_text)

    # 6. Leadership names
    leadership = _extract_leadership(classified_sections)

    # 7. Clients & Partners — apply garbage filter
    clients = _filter_business_items(classified_sections.get("Clients", []), max_len=80)[:15]
    partners = _filter_business_items(classified_sections.get("Partners", []), max_len=80)[:15]
    industries_served = _filter_business_items(classified_sections.get("Industries", []), max_len=80)[:10]

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
        # Validate phone numbers — filter out year ranges and non-phone strings
        phone_numbers=[
            p for p in aggregated_contacts.get("phone_numbers", [])
            if _is_valid_phone(p)
        ],
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
# AI enrichment (governed by AI_MODE / WEBSITE_AGENT_MODE)
# ---------------------------------------------------------------------------

def enrich_website_data_with_ai(website_data, combined_clean_text: str):
    """
    Runs after rule-based extraction. Uses the AI path (with automatic
    rule-based fallback via ai.mode.run_with_fallback) to fill in / improve
    fields the keyword-based extractor struggles with: industry,
    description, business-relevant products/services phrasing, and
    industries served. Never overwrites rule-based fields with empty AI
    output; only fills gaps or adds items the rule-based pass missed.

    Returns the (possibly enriched) website_data object, plus the path used
    ("ai" or "rule_based") for logging/telemetry.
    """
    from pipeline.ai.client import get_ai_client
    from pipeline.ai.mode import run_with_fallback

    def _rule_fn():
        # No-op: keep the rule-based extraction exactly as-is.
        return {}

    def _ai_fn():
        text_sample = (combined_clean_text or "")[:6000]
        messages = [
            {
                "role": "system",
                "content": (
                    "You analyze a company's website text and extract a structured profile. "
                    "Respond ONLY with a JSON object with keys: "
                    "description (1-3 sentence company summary), industry (short label), "
                    "products (array of strings), services (array of strings), "
                    "industries_served (array of strings). "
                    "If the text doesn't support a field, use an empty string or empty array — "
                    "never invent facts not implied by the text."
                ),
            },
            {"role": "user", "content": f"Company: {website_data.company_name or website_data.website_url}\n\nWebsite text:\n{text_sample}"},
        ]
        return get_ai_client().chat_json(messages)

    ai_result, path_used = run_with_fallback("website", ai_fn=_ai_fn, rule_fn=_rule_fn)

    if path_used == "ai" and ai_result:
        if not website_data.description and ai_result.get("description"):
            website_data.description = ai_result["description"]
        if not website_data.industry and ai_result.get("industry"):
            website_data.industry = ai_result["industry"]
        website_data.products = _merge_unique(website_data.products, ai_result.get("products", []))
        website_data.services = _merge_unique(website_data.services, ai_result.get("services", []))
        website_data.industries_served = _merge_unique(website_data.industries_served, ai_result.get("industries_served", []))

    return website_data, path_used


def _merge_unique(existing: list[str], new_items) -> list[str]:
    if not isinstance(new_items, list):
        return existing
    seen = {item.strip().lower() for item in existing}
    merged = list(existing)
    for item in new_items:
        if isinstance(item, str) and item.strip() and item.strip().lower() not in seen:
            merged.append(item.strip())
            seen.add(item.strip().lower())
    return merged


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _infer_industry(text: str, overview_paragraphs: list[str]) -> str:
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


def _extract_locations(classified_sections: dict[str, list[str]]) -> tuple:
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


def _detect_tech_stack(text: str) -> list[str]:
    """Scan text for known technology keywords."""
    found = []
    for tech in TECH_KEYWORDS:
        pattern = r'\b' + re.escape(tech) + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            found.append(tech)
    return found


def _extract_leadership(classified_sections: dict[str, list[str]]) -> list[str]:
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


def identify_role_pages(urls: list[str]) -> dict[str, str]:
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
