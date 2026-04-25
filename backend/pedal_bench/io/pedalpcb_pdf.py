"""Extract a BOM from a PedalPCB build-document PDF.

Two formats supported:

1. Modern tabular layout (Sherwood Overdrive era):
     - "Parts List (Page N of M)" header
     - Table with 4 columns: LOCATION | VALUE | TYPE | NOTES
     - Section breaks are blank rows
     - NOTES cell may contain asterisked footnotes

2. Legacy multi-column "Parts List" layout (Gerkin Fuzz era, ~2018):
     - No table — just flowing text in 3+ columns
     - Section headers in bold ALL-CAPS: RESISTORS, CAPACITORS,
       INTEGRATED CIRCUITS, DIODES, POTENTIOMETERS, TRIM POTS
     - Rows are "<refdes>  <value>" (e.g. "R1  33K", "C100  100u")
     - Pots use the control name as the refdes (LOUDNESS, FILTER, ...)

The tabular parser runs first; if it produces nothing, the parts-list
parser runs as a deterministic fallback (no AI required).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from pedal_bench.core.models import BOMItem

# Column header aliases (PedalPCB variants spotted in the wild).
_HEADER_LOCATION = {"LOCATION", "LOC", "REFDES"}
_HEADER_VALUE = {"VALUE", "VAL"}
_HEADER_TYPE = {"TYPE", "PART TYPE", "DESCRIPTION"}
_HEADER_NOTES = {"NOTES", "NOTE", "COMMENT", "COMMENTS"}


class BOMParseError(RuntimeError):
    """Raised when no BOM table can be located in the PDF."""


def extract_bom(pdf_path: Path | str) -> list[BOMItem]:
    """Parse a PedalPCB PDF and return its BOM as a list of BOMItem.

    Raises BOMParseError if no BOM table is found.
    """
    import pdfplumber  # deferred so `import app.io.pedalpcb_pdf` works before install

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    items: list[BOMItem] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in _iter_tables(page):
                header_idx, col_map = _find_header(table)
                if header_idx is None:
                    continue
                items.extend(_rows_to_items(table[header_idx + 1 :], col_map))

        if not items:
            items = _extract_parts_list(pdf)

    if not items:
        raise BOMParseError(
            f"No BOM table or parts-list section found in {pdf_path}"
        )
    return items


def _iter_tables(page: Any) -> Iterable[list[list[str | None]]]:
    """Yield tables from a page, tolerant of extraction variations."""
    try:
        tables = page.extract_tables() or []
    except Exception:  # pdfplumber occasionally throws on oddly-encoded PDFs
        return []
    for table in tables:
        if table:
            yield table


def _find_header(table: list[list[str | None]]) -> tuple[int | None, dict[str, int]]:
    """Find the header row index and map column-role -> column-index.

    Returns (None, {}) if the table doesn't look like a BOM.
    """
    for idx, row in enumerate(table):
        cells = [_normalize_header_cell(c) for c in row]
        col_map: dict[str, int] = {}
        for col_idx, cell in enumerate(cells):
            if cell in _HEADER_LOCATION and "location" not in col_map:
                col_map["location"] = col_idx
            elif cell in _HEADER_VALUE and "value" not in col_map:
                col_map["value"] = col_idx
            elif cell in _HEADER_TYPE and "type" not in col_map:
                col_map["type"] = col_idx
            elif cell in _HEADER_NOTES and "notes" not in col_map:
                col_map["notes"] = col_idx
        if {"location", "value", "type"}.issubset(col_map):
            return idx, col_map
    return None, {}


def _normalize_header_cell(cell: str | None) -> str:
    if cell is None:
        return ""
    return cell.strip().upper()


def _rows_to_items(
    rows: list[list[str | None]],
    col_map: dict[str, int],
) -> list[BOMItem]:
    items: list[BOMItem] = []
    for row in rows:
        loc = _cell(row, col_map.get("location"))
        val = _cell(row, col_map.get("value"))
        typ = _cell(row, col_map.get("type"))
        notes = _cell(row, col_map.get("notes"))

        # Skip blank section-break rows.
        if not (loc or val or typ):
            continue
        # Skip rows that lack the three required fields — likely a footer
        # or a page-number row that slipped into the table.
        if not loc or not val or not typ:
            continue
        # Skip a repeated header that appears across page breaks.
        if (
            loc.upper() in _HEADER_LOCATION
            and val.upper() in _HEADER_VALUE
            and typ.upper() in _HEADER_TYPE
        ):
            continue

        items.append(BOMItem.from_pdf_row(
            location=loc,
            value=val,
            type_=typ,
            notes=notes,
        ))
    return items


def _cell(row: list[str | None], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    value = row[idx]
    if value is None:
        return ""
    # pdfplumber sometimes returns embedded newlines inside a cell when the
    # source text wrapped; collapse to a single space.
    return " ".join(value.split())


# ---- legacy "Parts List" multi-column text parser ------------------------
#
# Older PedalPCB build docs (Gerkin Fuzz, ~2018) don't render the BOM as a
# table — they use flowing text in 3 columns under bold ALL-CAPS section
# headers. pdfplumber's table extractor returns nothing for these pages, so
# we fall back to extracting the page's words with their (x, y) positions,
# clustering them into columns, and then walking each column top-to-bottom
# as its own line stream.

# Section header → BOMItem.type string. Matched as a whole-segment prefix
# (case-insensitive, whitespace collapsed) so headers like "RESISTORS (1/4W)"
# still resolve to "RESISTORS".
_SECTION_TYPES: dict[str, str] = {
    "RESISTORS": "Resistor, 1/4W",
    "CAPACITORS": "Capacitor",
    "INTEGRATED CIRCUITS": "Integrated circuit",
    "TRANSISTORS": "Transistor",
    "DIODES": "Diode",
    "POTENTIOMETERS": "Potentiometer",
    "TRIM POTS": "Trim pot",
    "TRIMPOTS": "Trim pot",
    "SWITCHES": "Switch",
    "INDUCTORS": "Inductor",
    "RELAYS": "Relay",
}

# Refdes pattern for the electronic-component sections (R1, C100, D5, Q1,
# IC1, etc.). One or two letters followed by digits.
_REFDES_RE = re.compile(r"^[A-Z]{1,3}\d{1,4}$")
# Bare-name refdes used in pot/switch sections (LOUDNESS, FILTER, ...).
# Min 3 chars to avoid matching joiner words like "OR".
_NAME_REFDES_RE = re.compile(r"^[A-Z][A-Z0-9_-]{2,20}$")
# Joiner / boilerplate words that look like a refdes but aren't.
_REFDES_BLOCKLIST = {"OR", "AND", "SEE", "USE", "TO", "FOR", "THE", "IF",
                     "VERSION", "BUILD", "NOTE", "NOTES"}
# Whole words that, if present in a value, indicate the line is prose
# (a build note like "D1 and D2 orientation"), not a real component value.
_VALUE_PROSE_WORDS = {"and", "are", "is", "the", "with", "see", "if", "or",
                      "only", "needed", "when", "using", "these", "can",
                      "be", "omitted"}


def _looks_like_prose(value: str) -> bool:
    if len(value.split()) > 4:
        return True
    tokens = re.findall(r"[A-Za-z]+", value)
    return any(t.lower() in _VALUE_PROSE_WORDS for t in tokens)
# Value-shaped tokens (used to recognize orphaned pot taper/value tokens
# that landed in a separate visual column from their pot name).
_VALUE_RE = re.compile(r"^[ABCWMabcwm]?\d+[KkMmRrUuPpNn]?\d*[KkMmRrUuPpNn]?$")


def _section_for(segment_text: str) -> tuple[str, str] | None:
    """Return (section_key, type_str) if this segment starts with a known
    section header. Header may have trailing decoration like "(1/4W)".
    """
    upper = segment_text.upper().strip()
    for key, type_str in _SECTION_TYPES.items():
        if upper == key or upper.startswith(key + " ") or upper.startswith(key + "("):
            return key, type_str
    return None


def _extract_parts_list(pdf: Any) -> list[BOMItem]:
    """Fallback parser for older multi-column 'Parts List' pages."""
    items: list[BOMItem] = []
    seen: set[str] = set()
    for page in pdf.pages:
        try:
            words = page.extract_words(use_text_flow=False) or []
        except Exception:
            continue
        if not words:
            continue
        # Quick reject: page must mention at least one section header.
        page_text_upper = " ".join(w.get("text", "") for w in words).upper()
        if not any(h in page_text_upper for h in _SECTION_TYPES):
            continue

        for item in _parse_parts_list_page(words):
            if item.location in seen:
                continue
            seen.add(item.location)
            items.append(item)
    return items


def _segments_from_words(words: list[dict]) -> list[tuple[float, float, str]]:
    """Return (x_start, y_top, text) segments. A segment is a run of words
    on the same visual row separated from neighbors by a >=25pt x-gap.
    """
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda d: (round(float(d["top"]), 0), float(d["x0"]))):
        top = float(w["top"])
        if rows and abs(float(rows[-1][0]["top"]) - top) <= 2.5:
            rows[-1].append(w)
        else:
            rows.append([w])

    segments: list[tuple[float, float, str]] = []
    for row in rows:
        row_sorted = sorted(row, key=lambda d: float(d["x0"]))
        seg_words: list[dict] = []
        last_x1: float | None = None
        seg_x0: float | None = None
        for w in row_sorted:
            x0 = float(w["x0"])
            x1 = float(w["x1"])
            if last_x1 is not None and (x0 - last_x1) >= 25.0:
                segments.append((seg_x0, float(seg_words[0]["top"]),
                                 " ".join(d["text"] for d in seg_words)))
                seg_words = []
                seg_x0 = None
            if seg_x0 is None:
                seg_x0 = x0
            seg_words.append(w)
            last_x1 = x1
        if seg_words:
            segments.append((seg_x0, float(seg_words[0]["top"]),
                             " ".join(d["text"] for d in seg_words)))
    return segments


def _parse_parts_list_page(words: list[dict]) -> list[BOMItem]:
    """Walk a page's segments, grouping into columns and parsing each
    column top-to-bottom. Pot/switch sections also pair name-only entries
    with orphan value tokens at matching y-positions (left-to-right).
    """
    segments = _segments_from_words(words)
    if not segments:
        return []

    # Cluster segments into columns by x_start.
    x_positions = sorted(s[0] for s in segments)
    clusters: list[list[float]] = []
    for x in x_positions:
        if clusters and abs(clusters[-1][-1] - x) <= 30.0:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    cluster_centers = [sum(c) / len(c) for c in clusters]

    def column_index(x: float) -> int:
        return min(range(len(cluster_centers)),
                   key=lambda i: abs(cluster_centers[i] - x))

    columns: list[list[tuple[float, str]]] = [[] for _ in cluster_centers]
    for x_start, y_top, text in segments:
        columns[column_index(x_start)].append((y_top, text))
    for col in columns:
        col.sort(key=lambda t: t[0])

    items: list[BOMItem] = []
    for col_idx, col in enumerate(columns):
        right_cols = columns[col_idx + 1:]
        items.extend(_parse_column(col, right_cols))
    return items


def _parse_column(
    col: list[tuple[float, str]],
    right_cols: list[list[tuple[float, str]]],
) -> list[BOMItem]:
    items: list[BOMItem] = []
    current_type: str | None = None
    current_section: str | None = None

    for y_top, raw in col:
        line = " ".join(raw.split())
        if not line:
            continue

        section = _section_for(line)
        if section is not None:
            current_section, current_type = section
            continue
        if current_type is None:
            continue

        parts = line.split(None, 1)
        refdes = parts[0].strip()
        value = parts[1].strip() if len(parts) == 2 else ""

        if refdes.upper() in _REFDES_BLOCKLIST:
            continue

        if current_section in ("POTENTIOMETERS", "TRIM POTS", "TRIMPOTS",
                               "SWITCHES"):
            if not _NAME_REFDES_RE.match(refdes):
                continue
            if not value:
                # Pull a value from the closest segment to the right at
                # matching y. Common in older PDFs that tab pot values into
                # their own visual column.
                value = _find_orphan_value(y_top, right_cols)
                if not value:
                    continue
        else:
            if not _REFDES_RE.match(refdes):
                continue
            if not value:
                continue
            if _looks_like_prose(value):
                continue

        items.append(BOMItem.from_pdf_row(
            location=refdes,
            value=value,
            type_=current_type,
        ))
    return items


def _find_orphan_value(
    y_top: float,
    right_cols: list[list[tuple[float, str]]],
    tolerance: float = 3.0,
) -> str:
    """Search columns to the right for a value-shaped segment whose y is
    close to ``y_top``. Returns the first match, or "".
    """
    for col in right_cols:
        for cy, ctext in col:
            if abs(cy - y_top) <= tolerance:
                candidate = " ".join(ctext.split())
                # Accept either a value-shaped token, a named transistor,
                # or a short phrase (e.g. "3mm Red LED").
                if candidate and not _section_for(candidate):
                    return candidate
    return ""


__all__ = ["extract_bom", "BOMParseError"]
