"""
documents/brand_config.py
--------------------------
Centralized branding configuration and shared document constants.
Eliminates duplicated brand dicts and confidentiality text across all generators.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

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


def get_brand_config(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Returns a fresh copy of DEFAULT_BRAND with optional key overrides applied."""
    cfg = dict(DEFAULT_BRAND)
    if overrides:
        cfg.update(overrides)
    # Ensure asset paths exist or resolve correctly
    for key in ("logo_path", "cover_graphic_path"):
        val = cfg.get(key)
        if val and not Path(val).is_absolute():
            cfg[key] = str((PROJECT_ROOT / val).resolve())
    return cfg


def is_mock_solicitation(solicitation_number: Optional[str]) -> bool:
    """Centralized check for whether a solicitation number represents a mock/test solicitation."""
    if not solicitation_number:
        return True
    s = str(solicitation_number).strip().lower()
    return s in ("unknown", "none", "n/a", "") or s.startswith("mock") or s.startswith("bidforge-mock")
