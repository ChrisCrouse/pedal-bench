"""Extract a BOM from a PedalPCB build-document PDF.

Target format (confirmed from the Sherwood Overdrive PDF):
    - One or more BOM pages titled "Parts List (Page N of M)"
    - Table with 4 columns: LOCATION | VALUE | TYPE | NOTES
    - Section breaks are blank rows (resistors, caps, diodes, etc.)
    - NOTES cell may contain asterisked footnotes ("* LED current limiting resistor")

If a future PedalPCB PDF breaks this parser, add a format-detection branch
rather than forcing all PDFs through one path.
"""

from __future__ import annotations

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
        raise BOMParseError(
            f"No BOM table with LOCATION/VALUE/TYPE columns found in {pdf_path}"
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


__all__ = ["extract_bom", "BOMParseError"]
