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
from typing import Any

from docx import Document as OpenDocument

logger = logging.getLogger(__name__)


def extract_template_brand(template_path: str, output_dir: str | None = None) -> dict[str, Any]:
    """Best-effort extraction of a brand profile from `template_path`.

    Prefers the full TemplateAnalyzer (tables, IDs, sections, contacts) and
    merges logo/cover extraction. Falls back to OrbitAvanya defaults so
    generation never loses branding.
    """
    import importlib
    try:
        from backend.documents.brand_config import get_brand_config
    except ImportError:
        get_brand_config = importlib.import_module("documents.brand_config").get_brand_config

    brand = get_brand_config()

    # Rich analyzer: fonts, colors, contacts, tables, identifiers, sections
    try:
        from documents.template_analyzer import analyze_template
        profile = analyze_template(template_path)
        rich = profile.to_brand_config_dict()
        for k, v in rich.items():
            if v not in (None, "", [], {}):
                brand[k] = v
    except Exception as exc:
        logger.warning(f"[TemplateProfile] TemplateAnalyzer failed ({exc}); using lightweight extract.")

    try:
        doc = OpenDocument(template_path)
    except Exception as exc:
        logger.warning(f"[TemplateProfile] Could not open template '{template_path}' for brand extraction: {exc}")
        return brand

    logo_path, cover_path = _extract_logo_and_cover(doc, template_path, output_dir)
    if logo_path:
        brand["logo_path"] = logo_path
    if cover_path:
        brand["cover_graphic_path"] = cover_path
    elif logo_path:
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
        f"cover_graphic={'yes' if cover_path else ('same as logo' if logo_path else 'no (using default)')}, "
        f"accent={brand.get('accent_color')}, heading_font={brand.get('heading_font')}, "
        f"body_font={brand.get('body_font')}, sections={len(brand.get('sections') or [])}"
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


def _extract_logo_and_cover(
    doc, template_path: str, output_dir: str | None
):
    """Finds the template's running-page logo and its (possibly distinct)
    cover-page graphic, and writes each out as a standalone file
    proposal_generator.py can use as logo_path / cover_graphic_path.
    Returns (logo_path, cover_path), either of which may be None.

    Earlier versions assumed a cover-page logo always lives in the first-page
    header, and stopped looking as soon as ANY header image was found. That
    assumption doesn't hold for every template: it's just as common for a
    template's real cover-page artwork to be placed directly in the document
    BODY (as its own picture on page 1), while the first-page header/footer
    only carry a small recurring letterhead banner. Stopping at the header
    tier in that case grabs the small banner for the cover page too, and the
    real cover art is never even considered — which is exactly the
    header/footer-vs-cover mismatch this function now avoids.

    Instead we score two candidate pools independently:
      - LOGO candidates: images found in any header or footer (first-page or
        running). This is deliberately narrow, since a logo is meant to
        repeat on every page.
      - COVER candidates: the LOGO candidates plus every image embedded in
        the document body. The body is included because that's where a
        template's largest, most deliberate piece of cover artwork usually
        lives; the header/footer banner stays in the pool too in case the
        template genuinely doesn't have a separate body graphic.

    For each pool we pick the largest-by-pixel-area image (skipping
    spacer/bullet/divider-sized graphics), so the two paths only diverge when
    a template actually has a distinct, larger cover graphic outside the
    header/footer.
    """
    try:
        logo_candidates: list = []
        for section in doc.sections:
            for header_or_footer in (
                getattr(section, "first_page_header", None),
                section.header,
                getattr(section, "first_page_footer", None),
                section.footer,
            ):
                part = getattr(header_or_footer, "part", None)
                logo_candidates.extend(_images_in_part(part))

        cover_candidates = list(logo_candidates) + _images_in_part(doc.part)

        logo_image = _largest_image(logo_candidates)
        cover_image = _largest_image(cover_candidates)

        out_dir = Path(output_dir) if output_dir else Path(template_path).resolve().parent
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(template_path).stem

        logo_path = _write_image_part(logo_image, out_dir, f"{stem}_extracted_logo")
        if cover_image is logo_image:
            cover_path = logo_path
        else:
            cover_path = _write_image_part(cover_image, out_dir, f"{stem}_extracted_cover")

        return logo_path, cover_path
    except Exception as exc:
        logger.warning(f"[TemplateProfile] Logo/cover extraction failed: {exc}")
        return None, None


def _write_image_part(image_part, out_dir: Path, filename_stem: str) -> str | None:
    if image_part is None:
        return None
    ext = (image_part.partname.ext or "png").lstrip(".")
    out_path = out_dir / f"{filename_stem}.{ext}"
    out_path.write_bytes(image_part.blob)
    return str(out_path)


def _extract_accent_color(doc) -> str | None:
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


def _style_font(doc, style_names) -> str | None:
    for name in style_names:
        try:
            style = doc.styles[name]
        except KeyError:
            continue
        font_name = getattr(style.font, "name", None)
        if font_name:
            return font_name
    return None