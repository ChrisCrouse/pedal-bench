"""AI fallback for BOM extraction.

When the deterministic table parser in ``pedalpcb_extract`` returns no rows
(typically because the PDF uses an older multi-column "Parts List" layout
with section headers instead of LOCATION/VALUE/TYPE columns), we rasterize
the parts-list page and ask Claude to read it.

Best-effort fallback. Only invoked when the vector path returns nothing.
Returns None on any failure rather than raising.

Cost envelope (Haiku 4.5): ~$0.005-0.015 per call.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
from pathlib import Path

from pedal_bench.core.models import BOMItem

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4000
IMAGE_DPI = 200  # high enough to read small location codes (R12, C9, etc.)

# Substrings that strongly suggest a page is the parts list. Used to pick
# which page to rasterize when the vector extractor doesn't tell us.
_PARTS_PAGE_HINTS = (
    "parts list",
    "resistors",
    "capacitors",
    "transistors",
    "integrated circuits",
)

_TOOL_SCHEMA = {
    "name": "report_bom",
    "description": (
        "Report every component you can read from the parts-list image. "
        "Each component must include its location designator (e.g. R7, C12, "
        "Q1, IC1, D2), its value (e.g. '4K7', '100n', '2N5089'), and a type "
        "string (e.g. 'Resistor, 1/4W', 'Ceramic capacitor', 'NPN transistor'). "
        "Always call this tool — never reply in plain text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low", "none"],
                "description": (
                    "How confident you are that you've captured the parts "
                    "list correctly. 'none' if the image isn't a parts list."
                ),
            },
            "bom": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "Reference designator like R1, C12, Q3, IC2.",
                        },
                        "value": {
                            "type": "string",
                            "description": "Component value (e.g. '4K7', '100n', '2N5089').",
                        },
                        "type": {
                            "type": "string",
                            "description": (
                                "Short type string. Use the section header "
                                "from the image when available (e.g. "
                                "'Resistor, 1/4W' under RESISTORS (1/4W); "
                                "'Capacitor' under CAPACITORS; 'Transistor' "
                                "under TRANSISTORS; 'Diode' under DIODES; "
                                "'Integrated circuit' under INTEGRATED CIRCUITS). "
                                "Refine when the value gives more info "
                                "(e.g. 'Electrolytic capacitor' for an "
                                "obvious electro)."
                            ),
                        },
                        "notes": {
                            "type": "string",
                            "description": "Any additional info from the row (rare).",
                        },
                    },
                    "required": ["location", "value", "type"],
                },
            },
        },
        "required": ["confidence", "bom"],
    },
}


def extract_bom_with_ai(pdf_path: Path | str) -> list[BOMItem] | None:
    """Find the parts-list page and ask Claude to read the BOM.

    Returns None on any failure (no key, API error, no parts page found,
    confidence='none', empty result).
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        return None

    try:
        page_index, png_bytes = _find_and_render_parts_page(pdf_path)
    except Exception as exc:
        log.info("AI BOM extract: could not render parts page: %s", exc)
        return None
    if png_bytes is None:
        return None

    try:
        resp = _call_claude(png_bytes)
    except Exception as exc:
        log.info("AI BOM extract: API call failed: %s", exc)
        return None

    return _parse_response(resp)


def _find_and_render_parts_page(pdf_path: Path) -> tuple[int | None, bytes | None]:
    """Find the page that looks most like a parts list and rasterize it.

    Strategy:
      1. Use pdfplumber to scan the first 4 pages' text.
      2. Pick the page with the most parts-list keywords.
      3. Rasterize via pypdfium2.
    Returns (page_index, png_bytes) or (None, None) if no page qualifies.
    """
    import pdfplumber
    import pypdfium2 as pdfium

    best_idx: int | None = None
    best_score = 0
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[:4]):
            text = (page.extract_text() or "").lower()
            score = sum(1 for h in _PARTS_PAGE_HINTS if h in text)
            if score > best_score:
                best_score = score
                best_idx = i

    if best_idx is None or best_score == 0:
        return None, None

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        page = doc[best_idx]
        scale = IMAGE_DPI / 72.0
        pil = page.render(scale=scale).to_pil()
        buf = io.BytesIO()
        pil.save(buf, format="PNG", optimize=True)
        return best_idx, buf.getvalue()
    finally:
        doc.close()


def _call_claude(png_bytes: bytes):
    import anthropic

    client = anthropic.Anthropic()

    system = (
        "You read parts lists from PedalPCB build documentation. The image "
        "may show parts arranged in multi-column sections with category "
        "headers (RESISTORS, CAPACITORS, TRANSISTORS, DIODES, INTEGRATED "
        "CIRCUITS) above each block, or as a single LOCATION/VALUE/TYPE "
        "table. Either way, return one row per component. Use the section "
        "header to fill in 'type' when the row only has location + value. "
        "Always call the report_bom tool — never reply in plain text."
    )

    user_text = (
        "Extract every component from this parts-list image. Preserve the "
        "exact value strings as printed (e.g. '4K7' as '4K7', not '4.7K'). "
        "Skip blanks, footnotes, and anything that isn't a component row. "
        "If the image is not a parts list, report confidence 'none' with "
        "an empty bom array."
    )

    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "report_bom"},
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


_LOC_RE = re.compile(r"^[A-Z]{1,3}\d{1,3}$")
_POLARITY_RE = re.compile(
    r"diode|electrolytic|transistor|op[- ]?amp|led|tantalum|integrated\s*circuit|^ic$",
    re.IGNORECASE,
)


def _parse_response(resp) -> list[BOMItem] | None:
    tool_input = None
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and block.name == "report_bom":
            tool_input = block.input
            break
    if tool_input is None:
        return None

    confidence = tool_input.get("confidence", "none")
    if confidence == "none":
        return None

    raw_rows = tool_input.get("bom", [])
    if not isinstance(raw_rows, list):
        return None

    items: list[BOMItem] = []
    seen_locations: set[str] = set()
    for raw in raw_rows:
        try:
            location = str(raw.get("location", "")).strip().upper()
            value = str(raw.get("value", "")).strip()
            type_str = str(raw.get("type", "")).strip()
            if not location or not value:
                continue
            if not _LOC_RE.match(location):
                # Drop garbage like "1/4W" or "RESISTORS"
                continue
            if location in seen_locations:
                continue
            seen_locations.add(location)
            notes = str(raw.get("notes") or "").strip()[:120]
            items.append(
                BOMItem(
                    location=location,
                    value=value[:40],
                    type=type_str[:80] or "Component",
                    notes=notes,
                    quantity=1,
                    polarity_sensitive=bool(_POLARITY_RE.search(type_str)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    if not items:
        return None
    items.sort(key=_sort_key)
    return items


def _sort_key(item: BOMItem) -> tuple[str, int]:
    """Sort by designator family then numeric suffix: R1, R2, ..., R10, C1, C2..."""
    m = re.match(r"^([A-Z]+)(\d+)$", item.location)
    if not m:
        return (item.location, 0)
    return (m.group(1), int(m.group(2)))


__all__ = ["extract_bom_with_ai"]
