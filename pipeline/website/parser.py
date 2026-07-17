"""
website/parser.py
-----------------
HTML parsing utilities: metadata extraction, link extraction, and contact info extraction.
"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from utils.helpers import setup_logger

logger = setup_logger(__name__)

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_REGEX = re.compile(r'\+?\d{1,4}[-.\s]?\(?\d{1,3}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}')

SOCIAL_DOMAINS = [
    "linkedin.com", "twitter.com", "x.com", "facebook.com",
    "youtube.com", "instagram.com", "github.com"
]


def parse_html_metadata(html_content: str) -> Dict[str, str]:
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


def extract_links(html_content: str) -> List[str]:
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


def extract_contact_info(html_content: str, text_content: str = "") -> Dict[str, List[str]]:
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
                for domain in SOCIAL_DOMAINS:
                    if domain in href.lower():
                        clean = re.sub(r'^[^h]+', '', href).strip()
                        link = clean if clean.startswith(("http://", "https://")) else href.strip()
                        contacts["social_links"].append(link)
                        if "linkedin.com/company" in link.lower() and not contacts["linkedin_url"]:
                            contacts["linkedin_url"] = link

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

        # Deduplicate
        contacts["emails"] = sorted(list(set(contacts["emails"])))
        contacts["phone_numbers"] = sorted(list(set(contacts["phone_numbers"])))
        contacts["social_links"] = sorted(list(set(contacts["social_links"])))

    except Exception as e:
        logger.warning(f"Contact extraction error: {e}")

    return contacts
