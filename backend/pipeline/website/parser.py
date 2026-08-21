"""
website/parser.py
-----------------
HTML parsing utilities: metadata extraction, link extraction, and contact info extraction.
"""

import re
from typing import Any

from bs4 import BeautifulSoup
from utils.helpers import setup_logger

logger = setup_logger(__name__)

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_REGEX = re.compile(r'\+?\d{1,4}[-.\s]?\(?\d{1,3}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}')

SOCIAL_DOMAINS = [
    "linkedin.com", "twitter.com", "x.com", "facebook.com",
    "youtube.com", "instagram.com", "github.com"
]

INVALID_EMAIL_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.wix', '.ico', '.tiff', '.bmp', '.wixpress')

CF_EMAIL_PROTECTION_HREF = re.compile(r'/cdn-cgi/l/email-protection#([0-9a-fA-F]+)')


def _decode_cf_email(encoded_hex: str) -> str:
    """
    Decode a Cloudflare 'email protection' obfuscated string back to a real
    email address. Cloudflare replaces on-page emails with a hex-encoded,
    single-byte-XOR'd string (data-cfemail="..." attribute, or a
    /cdn-cgi/l/email-protection#... href) and reconstructs it client-side
    with JS — which a headless scrape of raw HTML never executes, so these
    emails were previously dropped entirely.
    """
    try:
        raw = bytes.fromhex(encoded_hex.strip())
        if len(raw) < 2:
            return ""
        key = raw[0]
        decoded = bytes(b ^ key for b in raw[1:])
        email = decoded.decode("utf-8", errors="ignore")
        return email if "@" in email else ""
    except Exception:
        return ""


def is_valid_email(email: str) -> bool:
    email_lower = email.strip().lower()
    if any(email_lower.endswith(ext) for ext in INVALID_EMAIL_EXTS):
        return False
    if '@2x' in email_lower or '@3x' in email_lower or 'bootstrap' in email_lower:
        return False
    return True

def ensure_company_contact_fallback(domain: str, contacts: dict):
    """Strictly do not generate synthetic emails — only authentic scraped emails are kept."""


def parse_html_metadata(html_content: str) -> dict[str, str]:
    """Extract title and meta description from an HTML page."""
    metadata = {"title": "", "description": ""}
    if not html_content:
        return metadata
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        if soup.title and soup.title.string:
            metadata["title"] = soup.title.string.strip()
        desc_tag = (
            soup.find("meta", attrs={"name": "description"}) or
            soup.find("meta", attrs={"property": "og:description"}) or
            soup.find("meta", attrs={"name": "twitter:description"})
        )
        if desc_tag:
            content = str(desc_tag.get("content") or "").strip()
            if content:
                metadata["description"] = content
    except Exception:
        pass
    return metadata


def extract_links(html_content: str) -> list[str]:
    """Extract all <a href> targets from HTML."""
    links = []
    if not html_content:
        return links
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup.find_all("a", href=True):
            links.append(tag["href"])
    except Exception:
        pass
    return links


def extract_contact_info(html_content: str, text_content: str = "") -> dict[str, list[str]]:
    """
    Extract emails, phone numbers, and social media links from HTML.

    Returns:
        Dict with keys: 'emails', 'phone_numbers', 'social_links'.
        Also extracts 'linkedin_url' as first found linkedin.com link.
    """
    contacts: dict[str, Any] = {
        "emails": [],
        "phone_numbers": [],
        "social_links": [],
        "linkedin_url": None,
    }
    if not html_content:
        return contacts

    try:
        soup = BeautifulSoup(html_content, "html.parser")

        for tag in soup.find_all("a", href=True):
            href = str(tag["href"]).strip()
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email:
                    contacts["emails"].append(email)
            elif href.startswith("tel:"):
                phone = href.replace("tel:", "").strip()
                if phone:
                    contacts["phone_numbers"].append(phone)
            else:
                cf_match = CF_EMAIL_PROTECTION_HREF.search(href)
                if cf_match:
                    decoded = _decode_cf_email(cf_match.group(1))
                    if decoded:
                        contacts["emails"].append(decoded)
                    continue
                for domain in SOCIAL_DOMAINS:
                    if domain in href.lower():
                        link = href.strip()
                        if link.startswith("//"):
                            link = "https:" + link
                        elif not link.startswith(("http://", "https://")):
                            link = "https://" + link.lstrip("/")
                        contacts["social_links"].append(link)
                        if "linkedin.com/company" in link.lower() and not contacts["linkedin_url"]:
                            contacts["linkedin_url"] = link

        # Cloudflare also renders a <span class="__cf_email__" data-cfemail="...">
        # in place of the visible email text on the page (no <a> tag involved).
        for tag in soup.select("[data-cfemail]"):
            decoded = _decode_cf_email(str(tag.get("data-cfemail", "")))
            if decoded:
                contacts["emails"].append(decoded)

        # Also regex-scan text for emails & phones
        search_text = f"{soup.get_text()} {text_content}"
        for email in EMAIL_REGEX.findall(search_text):
            email_clean = email.strip().strip(".")
            if email_clean:
                contacts["emails"].append(email_clean)

        for phone in PHONE_REGEX.findall(search_text):
            digits = re.sub(r'\D', '', phone)
            if 7 <= len(digits) <= 15:
                contacts["phone_numbers"].append(phone.strip())

        # Clean & filter emails
        valid_emails = [e for e in contacts["emails"] if is_valid_email(e)]
        contacts["emails"] = sorted(list(set(valid_emails)))
        contacts["phone_numbers"] = sorted(list(set(contacts["phone_numbers"])))
        contacts["social_links"] = sorted(list(set(contacts["social_links"])))

    except Exception as e:
        logger.warning(f"Contact extraction error: {e}")

    return contacts
