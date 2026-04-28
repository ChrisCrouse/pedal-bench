"""Deterministic BOM extraction for Aion FX build-document PDFs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pedal_bench.core.models import BOMItem


class AionFXBOMParseError(RuntimeError):
    """Raised when no Aion FX parts-list rows can be located."""


_HEADER_CELLS = ("PART", "VALUE", "TYPE", "NOTES")
_REFDES_RE = re.compile(r"^[A-Z][A-Z0-9-]{0,20}\d*$")
_FOOTER_PREFIXES = ("HELIOS", "AION", "DOCUMENT", "LICENSE")


def extract_bom(pdf_path: Path | str) -> list[BOMItem]:
    import pdfplumber

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    items: list[BOMItem] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False) or []
            if _is_parts_list_page(words):
                items.extend(_parse_parts_list_words(words))

    if not items:
        raise AionFXBOMParseError(f"No Aion FX parts list found in {pdf_path}")
    return items


def _is_parts_list_page(words: list[dict[str, Any]]) -> bool:
    top_words = [
        str(w.get("text", "")).upper().rstrip(",")
        for w in words
        if float(w.get("top", 9999.0)) < 70.0
    ]
    joined = " ".join(top_words)
    return joined.startswith("PARTS LIST")


def _parse_parts_list_words(words: list[dict[str, Any]]) -> list[BOMItem]:
    header = _find_header(words)
    if header is None:
        return []
    header_top, col_x = header
    use_first_value_only = _header_has_multiple_value_columns(words, header_top)
    rows = _rows_from_words(
        [
            w
            for w in words
            if header_top + 5.0 < float(w.get("top", 0.0)) < 725.0
        ]
    )

    items: list[BOMItem] = []
    last_item: BOMItem | None = None
    for _top, row_words in rows:
        cells = _split_row(row_words, col_x)
        part = _clean(cells["part"])
        value = _clean(cells["value"])
        type_ = _clean(cells["type"])
        notes = _clean(cells["notes"])
        part, value = _normalize_part_value_cells(part, value, use_first_value_only)

        if not part and not value and not type_ and not notes:
            continue
        if _looks_like_footer(part, value, type_, notes):
            continue

        if part and value and type_ and _looks_like_refdes(part):
            item = BOMItem.from_pdf_row(
                location=part,
                value=value,
                type_=type_,
                notes=notes,
            )
            items.append(item)
            last_item = item
            continue

        # Wrapped note/type continuations have no part/value cells. Preserve
        # them on the preceding item instead of dropping useful guidance.
        if last_item is not None and not part and not value:
            continuation = " ".join(x for x in (type_, notes) if x)
            if continuation:
                last_item.notes = " ".join(
                    x for x in (last_item.notes, continuation) if x
                )

    return items


def _find_header(words: list[dict[str, Any]]) -> tuple[float, dict[str, float]] | None:
    rows = _rows_from_words(words)
    for top, row_words in rows:
        part_word = None
        type_word = None
        notes_word = None
        value_words: list[dict[str, Any]] = []
        for word in row_words:
            text = str(word.get("text", "")).upper()
            if text == "PART":
                part_word = word
            elif text == "TYPE":
                type_word = word
            elif text == "NOTES":
                notes_word = word
            elif text.startswith("VALUE"):
                value_words.append(word)
        if part_word is None or type_word is None or notes_word is None or not value_words:
            continue
        value_words.sort(key=lambda w: float(w["x0"]))
        col_x = {
            "part": float(part_word["x0"]),
            "value": float(value_words[0]["x0"]),
            "type": float(type_word["x0"]),
            "notes": float(notes_word["x0"]),
        }
        if len(value_words) >= 2:
            col_x["value2"] = float(value_words[1]["x0"])
        return top, col_x
    return None


def _rows_from_words(words: list[dict[str, Any]]) -> list[tuple[float, list[dict[str, Any]]]]:
    rows: list[tuple[float, list[dict[str, Any]]]] = []
    for word in sorted(words, key=lambda w: (float(w["top"]), float(w["x0"]))):
        top = float(word["top"])
        if rows and abs(rows[-1][0] - top) <= 3.0:
            rows[-1][1].append(word)
        else:
            rows.append((top, [word]))
    return rows


def _split_row(row_words: list[dict[str, Any]], col_x: dict[str, float]) -> dict[str, str]:
    if "value2" in col_x:
        value_start = col_x["value"] - 2.0
        value2_start = col_x["value2"] - 2.0
        type_start = col_x["type"] - 2.0
        notes_start = col_x["notes"] - 5.0

        cells: dict[str, list[str]] = {
            "part": [],
            "value": [],
            "value2": [],
            "type": [],
            "notes": [],
        }
        for word in sorted(row_words, key=lambda w: float(w["x0"])):
            x0 = float(word["x0"])
            text = str(word.get("text", ""))
            if x0 < value_start:
                cells["part"].append(text)
            elif x0 < value2_start:
                cells["value"].append(text)
            elif x0 < type_start:
                cells["value2"].append(text)
            elif x0 < notes_start:
                cells["type"].append(text)
            else:
                cells["notes"].append(text)
        return {key: " ".join(value) for key, value in cells.items()}

    part_value_mid = (col_x["part"] + col_x["value"]) / 2
    value_type_mid = (col_x["value"] + col_x["type"]) / 2
    notes_start = col_x["notes"] - 5.0

    cells: dict[str, list[str]] = {"part": [], "value": [], "type": [], "notes": []}
    for word in sorted(row_words, key=lambda w: float(w["x0"])):
        x0 = float(word["x0"])
        text = str(word.get("text", ""))
        if x0 < part_value_mid:
            cells["part"].append(text)
        elif x0 < value_type_mid:
            cells["value"].append(text)
        elif x0 < notes_start:
            cells["type"].append(text)
        else:
            cells["notes"].append(text)
    return {key: " ".join(value) for key, value in cells.items()}


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _looks_like_refdes(value: str) -> bool:
    upper = value.upper()
    if upper in _HEADER_CELLS:
        return False
    return bool(_REFDES_RE.match(upper))


def _looks_like_footer(*cells: str) -> bool:
    joined = " ".join(cells).strip().upper()
    return any(joined.startswith(prefix) for prefix in _FOOTER_PREFIXES)


def _header_has_multiple_value_columns(
    words: list[dict[str, Any]],
    header_top: float,
) -> bool:
    value_headers = 0
    for word in words:
        top = float(word.get("top", 0.0))
        if abs(top - header_top) > 3.0:
            continue
        text = str(word.get("text", "")).upper()
        if text.startswith("VALUE"):
            value_headers += 1
    return value_headers >= 2


def _normalize_part_value_cells(
    part: str,
    value: str,
    use_first_value_only: bool,
) -> tuple[str, str]:
    """Repair rows where the first value token bleeds into the part column."""
    if _looks_like_refdes(part):
        return part, value
    tokens = part.split()
    if len(tokens) < 2:
        return part, value
    candidate_part = tokens[0]
    if not _looks_like_refdes(candidate_part):
        return part, value
    spilled_value = " ".join(tokens[1:])
    if use_first_value_only:
        return candidate_part, spilled_value
    merged_value = _clean(" ".join(x for x in (spilled_value, value) if x))
    return candidate_part, merged_value


__all__ = [
    "AionFXBOMParseError",
    "extract_bom",
    "_parse_parts_list_words",
]
