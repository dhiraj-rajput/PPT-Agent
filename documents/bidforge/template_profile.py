"""
bidforge/template_profile.py
-----------------------------
Extracts a lightweight *brand profile* (logo, accent color, fonts) from a
user-uploaded .docx template, in the same shape as
documents.brand_config.get_brand_config().

Why this exists: the old flow (template_filler.py) opened the uploaded
template and surgically inserted AI text after matching headings, leaving
any placeholder body text already in the template behind and producing a
document that was part-original, part-generated. That's fragile and the
opposite of what a proposal generator should do.

This module instead treats the uploaded template purely as a *style
source* — colors, fonts, logo — extracted once. The actual document is
always generated fresh, end to end, by scripts/proposal_generator.py using
that extracted style plus the AI-authored section content, and returned as an editable DOCX. Nothing is ever inserted into the uploaded file itself.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from docx import Document as OpenDocument

logger = logging.getLogger(__name__)


def extract_template_brand(template_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Best-effort extraction of a brand profile from `template_path`.

    Every field that can't be confidently determined falls back to the
    OrbitAvanya default brand (via get_brand_config()), so the generated
    document never ends up with missing/blank branding even if the
    uploaded template is plain or unusually structured.
    """
    from documents.brand_config import get_brand_config

    brand = get_brand_config()

    try:
        doc = OpenDocument(template_path)
    except Exception as exc:
        logger.warning(f"[TemplateProfile] Could not open template '{template_path}' for brand extraction: {exc}")
        return brand

    logo_path = _extract_first_image(doc, template_path, output_dir)
    if logo_path:
        brand["logo_path"] = logo_path
        # We don't know which embedded image (if there were several) was
        # meant as a distinct cover graphic vs. a header logo, so reuse the
        # same one for both rather than guessing wrong.
        brand["cover_graphic_path"] = logo_path

    accent = _extract_accent_color(doc)
    if accent:
        brand["accent_color"] = accent

    heading_font = _style_font(doc, ["Heading 1", "Title"])
    body_font = _style_font(doc, ["Normal", "Body Text"])
    if heading_font:
        brand["heading_font"] = heading_font
    if body_font:
        brand["body_font"] = body_font

    logger.info(
        f"[TemplateProfile] Extracted brand from '{Path(template_path).name}': "
        f"logo={'yes' if logo_path else 'no (using default)'}, "
        f"accent={brand.get('accent_color')}, heading_font={brand.get('heading_font')}, "
        f"body_font={brand.get('body_font')}"
    )
    return brand


def _images_in_part(part) -> list:
    """Returns the image parts embedded in a single header/footer/body part,
    in the order python-docx exposes them (dict order == XML relationship
    order, not visual order — see the caller for how we disambiguate)."""
    if part is None:
        return []
    try:
        return [rel.target_part for rel in part.rels.values() if "image" in rel.reltype]
    except Exception:
        return []


def _largest_image(image_parts: list):
    """Picks the image with the largest pixel area from a candidate list,
    skipping anything that looks like a spacer/bullet/divider graphic
    (under 30px in either dimension) rather than a real logo. Falls back to
    the first candidate if Pillow can't decode any of them (e.g. WMF/EMF
    vector art, which python-docx templates sometimes embed)."""
    from io import BytesIO

    try:
        from PIL import Image
    except ImportError:
        return image_parts[0] if image_parts else None

    best_part = None
    best_area = -1
    for part in image_parts:
        try:
            with Image.open(BytesIO(part.blob)) as img:
                w, h = img.size
            if w < 30 or h < 30:
                continue  # spacer / bullet / divider, not a logo
            area = w * h
            if area > best_area:
                best_area = area
                best_part = part
        except Exception:
            continue  # undecodable (e.g. WMF/EMF) — not a usable logo candidate

    return best_part or (image_parts[0] if image_parts else None)


def _extract_first_image(doc, template_path: str, output_dir: Optional[str]) -> Optional[str]:
    """Finds the template's logo and writes it out as a standalone file
    proposal_generator.py can use as logo_path.

    Priority order matters here: a cover-page logo is almost always stored
    in the FIRST PAGE header (`section.first_page_header`) when the template
    has "different first page" enabled — which proposal_generator.py itself
    relies on for the cover — followed by the regular running header. Only
    if neither has an image do we fall back to the footer, and only after
    that to the document body. Mixing header and footer images into one
    bag and grabbing whichever happened to come first in relationship-ID
    order (the previous behavior) could just as easily surface a small
    footer graphic (social icon, watermark, divider) as the real logo,
    which is why the footer logo could end up looking wrong/mismatched.
    """
    try:
        candidate_tiers: list = []
        for section in doc.sections:
            tier: list = []
            for header_like in (
                getattr(section, "first_page_header", None),
                section.header,
            ):
                part = getattr(header_like, "part", None)
                tier.extend(_images_in_part(part))
            if tier:
                candidate_tiers.append(tier)

        if not candidate_tiers:
            for section in doc.sections:
                tier = []
                for footer_like in (
                    getattr(section, "first_page_footer", None),
                    section.footer,
                ):
                    part = getattr(footer_like, "part", None)
                    tier.extend(_images_in_part(part))
                if tier:
                    candidate_tiers.append(tier)

        if not candidate_tiers:
            body_images = _images_in_part(doc.part)
            if body_images:
                candidate_tiers.append(body_images)

        if not candidate_tiers:
            return None

        image_part = _largest_image(candidate_tiers[0])
        if image_part is None:
            return None

        ext = (image_part.partname.ext or "png").lstrip(".")
        out_dir = Path(output_dir) if output_dir else Path(template_path).resolve().parent
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{Path(template_path).stem}_extracted_logo.{ext}"
        out_path.write_bytes(image_part.blob)
        return str(out_path)
    except Exception as exc:
        logger.warning(f"[TemplateProfile] Logo extraction failed: {exc}")
        return None


def _extract_accent_color(doc) -> Optional[str]:
    """Looks for an explicit, non-black/white color on a heading style or run —
    that's almost always the template's brand accent color."""
    try:
        for style_name in ("Heading 1", "Heading 2", "Title"):
            try:
                style = doc.styles[style_name]
            except KeyError:
                continue
            color = getattr(style.font.color, "rgb", None)
            if color and str(color) not in ("000000", "FFFFFF"):
                return str(color)

        # Style itself may not carry direct formatting — scan actual runs
        # in the first heading-styled paragraphs as a fallback.
        for p in doc.paragraphs[:80]:
            style_name = (p.style.name if p.style else "") or ""
            if style_name.lower().startswith("heading") or style_name.lower() == "title":
                for run in p.runs:
                    color = getattr(run.font.color, "rgb", None)
                    if color and str(color) not in ("000000", "FFFFFF"):
                        return str(color)
    except Exception as exc:
        logger.warning(f"[TemplateProfile] Accent color extraction failed: {exc}")
    return None


def _style_font(doc, style_names) -> Optional[str]:
    for name in style_names:
        try:
            style = doc.styles[name]
        except KeyError:
            continue
        font_name = getattr(style.font, "name", None)
        if font_name:
            return font_name
    return None
