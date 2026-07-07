"""
website/cleaner.py
------------------
HTML cleaning utilities using trafilatura (primary) and readability-lxml (fallback).
Extracts main readable body text from raw HTML pages.
"""

from bs4 import BeautifulSoup
from utils.helpers import setup_logger

logger = setup_logger(__name__)


def _clean_whitespace(text: str) -> str:
    """Normalize whitespace in text."""
    import re
    if not text:
        return ""
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()


def clean_html_with_trafilatura(html_content: str) -> str:
    """
    Extract the main readable body text using Trafilatura.
    Strips navigation, headers, footers, sidebars, ads, cookie banners.
    """
    if not html_content:
        return ""
    try:
        import trafilatura
        extracted = trafilatura.extract(
            html_content,
            include_links=False,
            include_images=False,
            include_tables=True,
            no_fallback=False,
        )
        if extracted:
            return _clean_whitespace(extracted)
    except Exception as e:
        logger.warning(f"Trafilatura extraction failed: {e}")
    return ""


def clean_html_with_readability(html_content: str) -> str:
    """
    Fallback HTML cleaner using readability-lxml + BeautifulSoup.
    """
    if not html_content:
        return ""
    try:
        from readability import Document
        doc = Document(html_content)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "html.parser")
        text = soup.get_text(separator="\n")
        return _clean_whitespace(text)
    except Exception as e:
        logger.warning(f"Readability fallback failed: {e}")
    return ""


def clean_html_with_bs4(html_content: str) -> str:
    """
    Simple BS4-based text extraction as a second fallback.
    Removes script/style/nav elements and returns visible text.
    """
    if not html_content:
        return ""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
        return _clean_whitespace(text)
    except Exception:
        return ""


def clean_html_content(html_content: str) -> str:
    """
    Primary interface for page cleaning.
    Tries trafilatura → readability → BeautifulSoup in order.
    """
    text = clean_html_with_trafilatura(html_content)
    if not text or len(text.strip()) < 100:
        logger.debug("Trafilatura output too short — trying readability fallback")
        text = clean_html_with_readability(html_content)
    if not text or len(text.strip()) < 50:
        logger.debug("Readability output too short — trying BS4 fallback")
        text = clean_html_with_bs4(html_content)
    return text


def extract_raw_text(html_content: str) -> str:
    """
    Extract all raw visible text from HTML by stripping style/script tags.
    """
    return clean_html_with_bs4(html_content)
