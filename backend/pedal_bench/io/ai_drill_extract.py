"""AI fallback for drill-template extraction.

When the deterministic vector extractor in ``drill_template_extract`` fails
on a PDF (image-only PDFs, non-standard layouts, weird fonts), we rasterize
the drill-template page and ask Claude to pull the hole coordinates.

This is a best-effort fallback — it's only invoked when the vector path
returns nothing, and any exception here is caught at the call site so the
user still gets their project created (just without auto-extracted holes).

Contract:
    extract_drill_holes_with_ai(pdf_path, page_index, enclosure) -> list[Hole] | None

    Returns None on any failure (no key, API error, malformed response,
    impossible coordinates, etc.). Never raises.

Cost envelope (Haiku 4.5):
    One image + ~800 tokens of instructions + ~500-token response.
    Roughly $0.005-0.01 per call. Only invoked on PDFs where the vector
    extractor already failed, so it's not on the hot path.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from pathlib import Path

from pedal_bench.core.models import Enclosure, Hole, IconKind, Side

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1500
IMAGE_DPI = 150  # high enough to read small hole marks, low enough to stay cheap

VALID_SIDES: set[Side] = {"A", "B", "C", "D", "E"}
VALID_ICONS: set[IconKind] = {
    "pot",
    "chicken-head",
    "footswitch",
    "toggle",
    "led",
    "jack",
    "dc-jack",
    "expression",
}

_TOOL_SCHEMA = {
    "name": "report_holes",
    "description": (
        "Report the drill holes you extracted from the drill-template image. "
        "Every hole must include its face side (A=top, B=top-end, C=left-end, "
        "D=bottom-end, E=right-end), coordinates in millimeters (x+ is right, "
        "y+ is up, origin at the face center), diameter in millimeters, and "
        "optionally an icon kind and a short label."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low", "none"],
                "description": (
                    "Overall confidence that the extracted holes match the "
                    "drill template. Use 'none' if the image doesn't actually "
                    "show a drill template."
                ),
            },
            "holes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "side": {
                            "type": "string",
                            "enum": list(VALID_SIDES),
                        },
                        "x_mm": {"type": "number"},
                        "y_mm": {"type": "number"},
                        "diameter_mm": {"type": "number"},
                        "label": {"type": "string"},
                        "icon": {
                            "type": "string",
                            "enum": list(VALID_ICONS),
                        },
                    },
                    "required": ["side", "x_mm", "y_mm", "diameter_mm"],
                },
            },
        },
        "required": ["confidence", "holes"],
    },
}


def extract_drill_holes_with_ai(
    pdf_path: Path | str,
    page_index: int,
    enclosure: Enclosure,
    *,
    api_key: str | None = None,
) -> list[Hole] | None:
    """Ask Claude to read a drill-template page and return the holes.

    Returns None on any failure — caller treats None as "no AI result"
    and falls back to leaving holes empty.

    ``api_key`` is the per-request key (BYOK from the browser); falls
    back to the ANTHROPIC_API_KEY env var for self-hosters.
    """
    effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not effective_key:
        return None

    try:
        png_bytes = _render_page_png(Path(pdf_path), page_index)
    except Exception as exc:
        log.info("AI drill extract: could not render page: %s", exc)
        return None

    try:
        resp = _call_claude(png_bytes, enclosure, api_key=effective_key)
    except Exception as exc:
        log.info("AI drill extract: API call failed: %s", exc)
        return None

    holes = _parse_response(resp, enclosure)
    if holes is None:
        return None
    # Filter obvious nonsense (zero diameter, hole off the face).
    holes = [h for h in holes if _hole_is_plausible(h, enclosure)]
    return holes or None


def _render_page_png(pdf_path: Path, page_index: int) -> bytes:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        if page_index < 0 or page_index >= len(doc):
            raise IndexError(f"page {page_index} out of range")
        page = doc[page_index]
        scale = IMAGE_DPI / 72.0
        pil = page.render(scale=scale).to_pil()
        buf = io.BytesIO()
        pil.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    finally:
        doc.close()


def _call_claude(png_bytes: bytes, enclosure: Enclosure, *, api_key: str):
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    face_summary = _describe_faces(enclosure)

    system = (
        "You extract drill-template hole coordinates from PedalPCB build-doc "
        "images. You must call the report_holes tool with your findings — do "
        "not reply in plain text. Be conservative: if the image is not a "
        "drill template, or if you cannot locate faces clearly, return an "
        "empty holes array with confidence 'none'."
    )

    user_text = (
        f"This is a drill template for a {enclosure.key} enclosure.\n\n"
        f"{face_summary}\n\n"
        "Extract every hole you can see. Use the face side letters above. "
        "For each hole give me:\n"
        "- side (A/B/C/D/E)\n"
        "- x_mm, y_mm (millimeters, origin at face center, x+ right, y+ up)\n"
        "- diameter_mm (the hole's actual drill size, not including any "
        "outline)\n"
        "- optional: icon kind (pot/footswitch/toggle/led/jack/dc-jack/etc.)\n"
        "- optional: short label (FOOTSWITCH, GAIN, IN, OUT, etc.)\n\n"
        "Only include holes you are confident about. Skip alignment marks "
        "or center-crosses. If the image is not actually a drill template, "
        "report confidence 'none' with an empty holes array."
    )

    b64 = base64.standard_b64encode(png_bytes).decode("ascii")

    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "report_holes"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    )


def _describe_faces(enc: Enclosure) -> str:
    lines = [f"{enc.name} face dimensions (width × height, mm):"]
    for side in ("A", "B", "C", "D", "E"):
        face = enc.faces.get(side)
        if face:
            lines.append(
                f"  {side} ({face.label}): "
                f"{face.width_mm:.1f} × {face.height_mm:.1f}"
            )
    return "\n".join(lines)


def _parse_response(resp, enclosure: Enclosure) -> list[Hole] | None:
    """Extract the tool_use block's input and materialize into Hole objects."""
    tool_input = None
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and block.name == "report_holes":
            tool_input = block.input
            break
    if tool_input is None:
        log.info("AI drill extract: no report_holes tool_use in response")
        return None

    confidence = tool_input.get("confidence", "none")
    if confidence == "none":
        return None

    raw_holes = tool_input.get("holes", [])
    if not isinstance(raw_holes, list):
        return None

    holes: list[Hole] = []
    for raw in raw_holes:
        try:
            side = raw["side"]
            if side not in VALID_SIDES:
                continue
            x_mm = float(raw["x_mm"])
            y_mm = float(raw["y_mm"])
            diameter = float(raw["diameter_mm"])
            if diameter <= 0 or diameter > 40:
                continue
            icon_raw = raw.get("icon")
            icon: IconKind | None = (
                icon_raw if icon_raw in VALID_ICONS else None
            )
            label = raw.get("label") or None
            if label is not None:
                label = str(label)[:40].strip() or None
            holes.append(
                Hole(
                    side=side,
                    x_mm=x_mm,
                    y_mm=y_mm,
                    diameter_mm=diameter,
                    label=label,
                    powder_coat_margin=True,
                    icon=icon,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    return holes


def _hole_is_plausible(hole: Hole, enclosure: Enclosure) -> bool:
    face = enclosure.faces.get(hole.side)
    if face is None:
        return False
    half_w = face.width_mm / 2 + 1.0  # 1 mm tolerance past edge
    half_h = face.height_mm / 2 + 1.0
    return abs(hole.x_mm) <= half_w and abs(hole.y_mm) <= half_h


__all__ = ["extract_drill_holes_with_ai"]
