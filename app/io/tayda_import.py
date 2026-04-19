"""Parse Tayda Box Tool drill-template data into our canonical `Hole` list.

The Tayda Box Tool stores each hole as:
    side (A/B/C/D/E), diameter_mm, x_mm (from center), y_mm (from center)

Tayda itself exports to its own site format, but in practice users round-
trip via copy-paste or CSV. This module handles several realistic shapes:

  1. CSV / TSV / whitespace-separated text, with or without a header row:
        side,diameter,x,y
        A,12.2,0,-45.1
        A,7.2,-16.5,38.1
        ...

  2. JSON array of dicts with flexible key names:
        [{"side":"A","diameter":12.2,"x":0,"y":-45.1}, ...]
        [{"Side":"A","Diameter (mm)":12.2,"X Position (mm)":0,"Y Position (mm)":-45.1}, ...]

  3. JSON object with a top-level "holes" key.

Whichever the source, the output is always `list[Hole]` in our canonical
shape. `powder_coat_margin` is enabled by default (matching Tayda's "add
0.4mm" recommendation), but the caller can override per hole afterwards.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Iterable

from app.core.models import Hole, VALID_SIDE


class TaydaParseError(ValueError):
    """Raised when the input can't be interpreted as a hole list."""


# ---- public entry points -------------------------------------------------

def parse_tayda_text(text: str) -> list[Hole]:
    """Auto-detect CSV vs JSON and parse."""
    s = text.strip()
    if not s:
        raise TaydaParseError("Empty input")
    if s[0] in "[{":
        return parse_tayda_json(s)
    return parse_tayda_csv(s)


def parse_tayda_file(path: Path | str) -> list[Hole]:
    p = Path(path)
    content = p.read_text(encoding="utf-8-sig")  # tolerate BOM
    return parse_tayda_text(content)


# ---- JSON ----------------------------------------------------------------

_JSON_SIDE_KEYS = ("side", "Side", "s", "face", "Face")
_JSON_DIAM_KEYS = ("diameter_mm", "diameter", "Diameter (mm)", "Diameter", "d", "dia")
_JSON_X_KEYS = ("x_mm", "x", "X", "X Position (mm)", "x_pos", "xPos")
_JSON_Y_KEYS = ("y_mm", "y", "Y", "Y Position (mm)", "y_pos", "yPos")
_JSON_LABEL_KEYS = ("label", "Label", "name", "Name")
_JSON_PC_KEYS = ("powder_coat_margin", "powder_coat", "pc_margin")


def parse_tayda_json(text: str) -> list[Hole]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("holes") or data.get("Holes") or []
    if not isinstance(data, list):
        raise TaydaParseError("JSON is not a list of holes")
    out: list[Hole] = []
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise TaydaParseError(f"Hole #{idx + 1} is not an object")
        out.append(_json_entry_to_hole(idx, entry))
    return out


def _json_entry_to_hole(idx: int, entry: dict[str, Any]) -> Hole:
    side = _first(entry, _JSON_SIDE_KEYS)
    diameter = _first(entry, _JSON_DIAM_KEYS)
    x = _first(entry, _JSON_X_KEYS)
    y = _first(entry, _JSON_Y_KEYS)
    if side is None or diameter is None or x is None or y is None:
        raise TaydaParseError(
            f"Hole #{idx + 1} missing one of side/diameter/x/y; got keys {list(entry)}"
        )
    side = str(side).strip().upper()
    if side not in VALID_SIDE:
        raise TaydaParseError(f"Hole #{idx + 1}: unknown side {side!r}")
    label = _first(entry, _JSON_LABEL_KEYS)
    pc = _first(entry, _JSON_PC_KEYS)
    return Hole(
        side=side,                                      # type: ignore[arg-type]
        x_mm=float(x),
        y_mm=float(y),
        diameter_mm=float(diameter),
        label=str(label).strip() if label is not None else None,
        powder_coat_margin=bool(pc) if pc is not None else True,
    )


def _first(entry: dict[str, Any], keys: Iterable[str]) -> Any:
    for k in keys:
        if k in entry and entry[k] not in (None, ""):
            return entry[k]
    return None


# ---- CSV / TSV / whitespace ---------------------------------------------

# Header labels we recognise for each column.
_HDR_SIDE = {"side", "s", "face"}
_HDR_DIAM = {"diameter", "diameter_mm", "diameter (mm)", "dia", "d"}
_HDR_X = {"x", "x_mm", "x position", "x position (mm)", "x pos", "x_pos"}
_HDR_Y = {"y", "y_mm", "y position", "y position (mm)", "y pos", "y_pos"}
_HDR_LABEL = {"label", "name"}

_WHITESPACE_SPLIT = re.compile(r"[,\t;]+|\s{2,}|\s+")


def parse_tayda_csv(text: str) -> list[Hole]:
    """Parse CSV/TSV/whitespace-separated hole rows.

    If the first row looks like a header, columns are detected by label;
    otherwise rows are assumed to be `side,diameter,x,y[,label]`.
    """
    # Normalize line endings. Strip BOM.
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise TaydaParseError("Empty input")

    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        raise TaydaParseError("No rows found")

    # Split the first line with several delimiter candidates; pick the one
    # that yields the most columns.
    first_split = _split_row(lines[0])
    if _looks_like_header(first_split):
        col_map = _header_column_map(first_split)
        data_rows = [_split_row(ln) for ln in lines[1:]]
    else:
        # Assume positional columns.
        col_map = {"side": 0, "diameter": 1, "x": 2, "y": 3, "label": 4}
        data_rows = [_split_row(ln) for ln in lines]

    required = ("side", "diameter", "x", "y")
    for key in required:
        if key not in col_map:
            raise TaydaParseError(
                f"Could not locate {key!r} column (found: {sorted(col_map)})"
            )

    out: list[Hole] = []
    for row_idx, cells in enumerate(data_rows, start=1):
        if not any(c.strip() for c in cells):
            continue
        try:
            side = cells[col_map["side"]].strip().upper()
            diameter = float(cells[col_map["diameter"]])
            x = float(cells[col_map["x"]])
            y = float(cells[col_map["y"]])
        except (IndexError, ValueError) as exc:
            raise TaydaParseError(
                f"Row {row_idx}: could not parse ({exc}): {cells}"
            ) from exc
        if side not in VALID_SIDE:
            raise TaydaParseError(f"Row {row_idx}: unknown side {side!r}")
        label: str | None = None
        if "label" in col_map and col_map["label"] < len(cells):
            raw_label = cells[col_map["label"]].strip()
            label = raw_label or None
        out.append(Hole(
            side=side,                                  # type: ignore[arg-type]
            x_mm=x,
            y_mm=y,
            diameter_mm=diameter,
            label=label,
            powder_coat_margin=True,
        ))
    if not out:
        raise TaydaParseError("No data rows found")
    return out


def _split_row(line: str) -> list[str]:
    # Tab-delimited: split directly (csv.reader defaults to comma).
    if "\t" in line:
        return [p.strip() for p in line.split("\t")]
    # Comma or semicolon: real CSV parse to handle quoting.
    if "," in line or ";" in line:
        try:
            reader = csv.reader(io.StringIO(line))
            parts = next(reader, [])
            if parts:
                return [p.strip() for p in parts]
        except csv.Error:
            pass
    # Loose whitespace paste.
    return [p for p in _WHITESPACE_SPLIT.split(line.strip()) if p]


def _looks_like_header(cells: list[str]) -> bool:
    # Any non-numeric cell + recognisable column label → header.
    lower = [c.strip().lower() for c in cells]
    return any(
        c in _HDR_SIDE or c in _HDR_DIAM or c in _HDR_X or c in _HDR_Y
        for c in lower
    )


def _header_column_map(cells: list[str]) -> dict[str, int]:
    col_map: dict[str, int] = {}
    for idx, cell in enumerate(cells):
        c = cell.strip().lower()
        if c in _HDR_SIDE and "side" not in col_map:
            col_map["side"] = idx
        elif c in _HDR_DIAM and "diameter" not in col_map:
            col_map["diameter"] = idx
        elif c in _HDR_X and "x" not in col_map:
            col_map["x"] = idx
        elif c in _HDR_Y and "y" not in col_map:
            col_map["y"] = idx
        elif c in _HDR_LABEL and "label" not in col_map:
            col_map["label"] = idx
    return col_map


__all__ = [
    "parse_tayda_text",
    "parse_tayda_file",
    "parse_tayda_csv",
    "parse_tayda_json",
    "TaydaParseError",
]
