import base64
import hashlib
import hmac
import os
import re
import secrets
from typing import Dict, List, Tuple
from config.settings import settings

API_BASE_URL = os.getenv("API_BASE_URL") or "http://localhost:5050"

# 1x1 transparent PNG image served by the open-tracking route
TRANSPARENT_PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def new_tracking_id() -> str:
    """Generate a secure 32-char hex string for tracking opens/clicks."""
    return secrets.token_hex(16)


def hash_ip(ip: str) -> str:
    """Hash client IP using SHA-256 for privacy/GDPR compliance."""
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def open_pixel_tag(tracking_id: str) -> str:
    """Generate HTML image tag for open tracking."""
    return f'<img src="{API_BASE_URL}/api/tracking/open/{tracking_id}.png" width="1" height="1" alt="" style="display:none" />'


def click_tracking_url(tracking_id: str) -> str:
    """Generate click tracking redirect URL."""
    return f"{API_BASE_URL}/api/tracking/click/{tracking_id}"


def rewrite_links_for_tracking(html: str) -> Tuple[str, List[Dict[str, str]]]:
    """
    Find all href="http..." links in HTML and rewrite them to redirect through the click tracking endpoint.
    Returns the rewritten HTML and list of created mappings.
    """
    links = []

    def replacer(match):
        url = match.group(1)
        # Skip relative links, anchors, mailto:, etc.
        if not re.match(r"^https?://", url, re.IGNORECASE):
            return match.group(0)

        tracking_id = new_tracking_id()
        links.append({"trackingId": tracking_id, "destinationUrl": url})
        return f'href="{click_tracking_url(tracking_id)}"'

    # Regex to find href attribute values
    rewritten = re.sub(r'href=["\']([^"\']+)["\']', replacer, html)
    return rewritten, links


def unsubscribe_url(lead_id: str, campaign_id: str) -> str:
    """Generate secure unsubscribe link containing a token signature."""
    secret = settings.JWT_SECRET or "unsubscribe-fallback-secret"
    token = hmac.new(
        secret.encode("utf-8"),
        f"{lead_id}:{campaign_id}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()[:24]
    return f"{API_BASE_URL}/api/tracking/unsubscribe/{campaign_id}/{lead_id}?t={token}"


def verify_unsubscribe_token(lead_id: str, campaign_id: str, token: str) -> bool:
    """Verify hmac signature of unsubscribe token."""
    secret = settings.JWT_SECRET or "unsubscribe-fallback-secret"
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{lead_id}:{campaign_id}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()[:24]
    return hmac.compare_digest(expected, token)
