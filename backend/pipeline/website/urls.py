"""
website/urls.py
---------------
URL utilities: normalization, internal link detection, priority scoring,
and ignore-list filtering for the website crawler.

Ported from prasanna/company-extractor and adapted for this project's structure.
"""

import re
from urllib.parse import urlparse, urljoin, parse_qsl, urlencode

from utils.helpers import setup_logger

logger = setup_logger(__name__)

PRIORITY_KEYWORDS = [
    "about", "company", "product", "service", "solution",
    "leadership", "management", "team", "contact", "career",
    "technology", "partner", "client", "blog", "who-we-are",
    "what-we-do", "about-us", "contact-us", "info", "people",
    "staff", "platform", "pricing", "customer"
]

IGNORE_KEYWORDS = [
    "privacy", "terms", "login", "signin", "signup", "register",
    "cart", "checkout", "cookies", "media", "image", "video",
    "pdf", "download", "wp-content", "tag", "category", "archive",
    "rss", "feed", "xml", "sitemap", "support", "help", "faq",
    "javascript:void(0)", "tel:", "mailto:"
]

TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "gclid", "fbclid", "ref", "affiliate", "campaign"
}


def get_domain(url: str) -> str:
    """Extract the bare domain (no www prefix) from a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def is_internal_link(url: str, base_url: str) -> bool:
    """Return True if the URL belongs to the same domain as base_url."""
    return get_domain(url) == get_domain(base_url)


def normalize_url(url: str, base_url: str) -> str:
    """
    Clean and normalize a URL into a canonical absolute form.
    Resolves relative URLs, strips tracking parameters and trailing slashes.
    """
    try:
        if not url or url.strip().startswith(("javascript:", "#", "mailto:", "tel:")):
            return ""

        absolute_url = urljoin(base_url, url.strip())
        parsed = urlparse(absolute_url)

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/") or "/"

        clean_params = [
            (k, v) for k, v in parse_qsl(parsed.query)
            if k.lower() not in TRACKING_QUERY_KEYS
        ]
        clean_params.sort()

        normalized = f"{scheme}://{netloc}{path}"
        if clean_params:
            normalized += "?" + urlencode(clean_params)
        return normalized
    except Exception:
        return ""


def should_ignore_url(url: str) -> bool:
    """Return True if the URL should be skipped (non-HTML file, tracking page, etc.)."""
    if not url:
        return True

    path = urlparse(url).path.lower()

    if re.search(
        r'\.(png|jpg|jpeg|gif|pdf|zip|gz|mp4|avi|mp3|wav|xml|css|js|ico|txt|doc|docx|xls|xlsx|ppt|pptx|svg|webp)$',
        path
    ):
        return True

    for kw in IGNORE_KEYWORDS:
        if kw in path or kw in url.lower():
            return True

    return False


def get_url_priority(url: str) -> int:
    """
    Score a URL's crawl priority (higher = more important).
    Homepage = 10, priority pages = 5, others = 1.
    """
    if not url:
        return 0

    path = urlparse(url).path.lower().strip("/")
    if not path:
        return 10  # Homepage

    for kw in PRIORITY_KEYWORDS:
        if kw in path:
            return 5

    return 1
