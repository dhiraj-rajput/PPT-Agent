"""
documents/brand_config.py
--------------------------
Centralized branding configuration and shared document constants.
Eliminates duplicated brand dicts and confidentiality text across all generators.
Now includes: asset validation, font availability detection, pathlib-based paths.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Font fallback chain for cross-OS compatibility
# We try fonts in order; first available font on the system wins.
FONT_FALLBACK_CHAIN: List[str] = [
    "Fira Sans",
    "Calibri",
    "Arial",
    "Helvetica",
    "Liberation Sans",
    "DejaVu Sans",
]

_detected_font: Optional[str] = None


def detect_available_font(preferred_fonts: Optional[List[str]] = None) -> str:
    """
    Detect the first available font from the preferred list.
    Falls back through FONT_FALLBACK_CHAIN if none are available.
    """
    global _detected_font
    if _detected_font is not None and not preferred_fonts:
        return _detected_font

    fonts_to_try = list(preferred_fonts or []) + FONT_FALLBACK_CHAIN

    try:
        try:
            import matplotlib.font_manager as fm  # type: ignore
            available = {f.name for f in fm.fontManager.ttflist}
            for font in fonts_to_try:
                if font in available:
                    if not preferred_fonts:
                        _detected_font = font
                    return font
        except ImportError:
            pass

        # No matplotlib - use system-level checks
        import subprocess
        import sys
        if sys.platform == "win32":
            import os
            fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for font in fonts_to_try:
                font_lower = font.lower().replace(" ", "")
                for f in fonts_dir.glob("*.ttf"):
                    if font_lower in f.stem.lower():
                        if not preferred_fonts:
                            _detected_font = font
                        return font
        elif sys.platform in ("darwin", "linux"):
            try:
                result = subprocess.run(["fc-list"], capture_output=True, text=True, timeout=5)
                for font in fonts_to_try:
                    if font.lower() in result.stdout.lower():
                        if not preferred_fonts:
                            _detected_font = font
                        return font
            except (FileNotFoundError, OSError):
                pass
    except Exception as e:
        logger.debug(f"Font detection error (non-critical): {e}")

    # Last resort: Calibri is bundled with Office, Arial is universal
    _detected_font = "Calibri"
    return _detected_font


def _resolve_asset(path_str: str) -> str:
    """
    Resolve an asset path to absolute. Returns empty string if the asset
    file doesn't exist, with a warning log.
    """
    if not path_str:
        return ""
    p = Path(path_str)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p = p.resolve()
    if not p.exists():
        logger.warning(
            f"Brand asset not found: {p}. "
            f"Document generation will continue without this asset."
        )
        return ""  # Return empty so downstream code can skip gracefully
    return str(p)


DEFAULT_BRAND: Dict[str, Any] = {
    "company_name": "OrbitAvanya Tech LLP",
    "company_short": "OrbitAvanya",
    "logo_path": str((PROJECT_ROOT / "assets" / "logo.png").resolve()),
    "cover_graphic_path": str((PROJECT_ROOT / "assets" / "cover_graphic.png").resolve()),
    "body_font": "Fira Sans Light",
    "heading_font": "Fira Sans SemiBold",
    "accent_color": "1F3864",
    "muted_color": "595959",
    "address_line1": "13352 Kettle Camp Rd",
    "address_line2": "Frisco, Texas 75035",
    "phone": "+917021950643",
    "website": "www.orbitavanyatech.com",
}

DEFAULT_CONFIDENTIALITY_TEXT: str = (
    "This document contains proprietary and confidential information of OrbitAvanya Tech LLP "
    "and the recipient organization. It is submitted for the sole purpose of evaluating a potential "
    "business arrangement or technical contract engagement. No portion of this document may be "
    "reproduced, stored in a retrieval system, or transmitted in any form or by any means without "
    "prior written authorization from OrbitAvanya Tech LLP."
)


def get_brand_config(overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Returns a fresh copy of DEFAULT_BRAND with optional key overrides applied.
    Resolution order (lowest to highest priority):
      1. Hardcoded DEFAULT_BRAND
      2. An org-wide default .docx template uploaded via Proposal Builder /
         RFP Auto-Respond / RFP upload (Settings > Proposal Template)
      3. 'own_company_profile' in MongoDB (explicit manual overrides)
      4. `overrides` passed in by the caller
    Validates asset paths exist; logs warnings for missing assets.
    Auto-detects available system fonts.
    """
    cfg = dict(DEFAULT_BRAND)

    # If an org-wide default template has been uploaded, use its extracted
    # branding/contact info instead of the hardcoded OrbitAvanya defaults.
    try:
        from documents.default_template import get_default_template_path
        default_template_path = get_default_template_path()
        if default_template_path:
            from documents.template_analyzer import analyze_template
            profile = analyze_template(default_template_path)
            cfg.update(profile.to_brand_config_dict())
    except Exception as e:
        logger.debug(f"Could not load org-wide default template branding: {e}")

    # Try fetching saved company profile from MongoDB
    try:
        from utils.db_client import get_collection
        col = get_collection("own_company_profile")
        db_profile = col.find_one({}, {"_id": 0})
        if db_profile:
            if db_profile.get("name"):
                cfg["company_name"] = db_profile["name"]
            if db_profile.get("phone"):
                cfg["phone"] = db_profile["phone"]
            if db_profile.get("email"):
                cfg["email"] = db_profile["email"]
            if db_profile.get("city") and db_profile.get("state"):
                cfg["address_line2"] = f"{db_profile['city']}, {db_profile['state']}"
    except Exception as e:
        logger.debug(f"Could not load own_company_profile from MongoDB: {e}")

    if overrides:
        cfg.update(overrides)

    # Validate and resolve asset paths
    for key in ("logo_path", "cover_graphic_path"):
        cfg[key] = _resolve_asset(cfg.get(key, ""))

    # Auto-detect available font if Fira Sans is requested but may not be installed
    body_font = cfg.get("body_font", "Fira Sans Light")
    heading_font = cfg.get("heading_font", "Fira Sans SemiBold")
    
    # Check if font names contain "Fira Sans" and detect availability
    if "fira" in body_font.lower():
        available = detect_available_font(["Fira Sans"])
        if available != "Fira Sans":
            # Fira Sans not installed, use the detected fallback
            cfg["body_font"] = available
            cfg["heading_font"] = available
            logger.info(f"Fira Sans not available, using '{available}' instead.")

    return cfg


def is_mock_solicitation(solicitation_number: Optional[str]) -> bool:
    """Centralized check for whether a solicitation number represents a mock/test solicitation."""
    if not solicitation_number:
        return True
    s = str(solicitation_number).strip().lower()
    return s in ("unknown", "none", "n/a", "") or s.startswith("mock") or s.startswith("bidforge-mock")
