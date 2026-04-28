"""Aion FX drill-template extraction.

Aion PDFs print the useful drill data as inch coordinates beside the drawing,
so this parser favors the text labels over trying to infer scale from artwork.
"""

from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path
from typing import Any

from pedal_bench.core.models import Enclosure, Hole, IconKind

INCH_TO_MM = 25.4
_FACE_COORD_TOL_MM = 2.5

_COORD_VALUE_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?[,]?$")
_DIAMETER_RE = re.compile(r"ø\s*(\d+)\s*/\s*(\d+)")
_LABELS = {
    "VOLUME",
    "DISTORTION",
    "FILTER",
    "SWEEP",
    "TONE",
    "DRIVE",
    "GAIN",
    "LEVEL",
    "MODE",
    "CLIP",
    "LED",
    "FOOTSWITCH",
    "OUT",
    "DC",
    "IN",
}


def extract_drill_holes(
    pdf_path: Path | str,
    enclosure: Enclosure | None = None,
    page_index: int | None = None,
) -> list[Hole] | None:
    import pdfplumber

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        idx = page_index if page_index is not None else _locate_drill_page(pdf)
        if idx is None or idx < 0 or idx >= len(pdf.pages):
            return None
        words = pdf.pages[idx].extract_words(use_text_flow=False) or []

    holes = _extract_face_a_holes(words)
    holes.extend(_infer_top_jack_holes(words))
    holes = _apply_enclosure_transform_and_validation(holes, enclosure)
    holes = _dedupe(holes)
    return holes or None


def _locate_drill_page(pdf: Any) -> int | None:
    for idx, page in enumerate(pdf.pages):
        try:
            lines = (page.extract_text() or "").splitlines()
        except Exception:
            continue
        first = next((line.strip().upper() for line in lines if line.strip()), "")
        if first == "DRILL TEMPLATE":
            return idx
    return None


def _extract_face_a_holes(words: list[dict[str, Any]]) -> list[Hole]:
    labels = _label_words(words)
    diameters = _diameter_words(words)
    holes: list[Hole] = []

    for group in _coordinate_groups(words):
        diameter = _nearest_diameter_mm(group, diameters)
        if diameter is None:
            continue
        label = _nearest_label(group, labels)
        icon = _icon_for_label(label, diameter)
        holes.append(
            Hole(
                side="A",
                x_mm=round(group["x_in"] * INCH_TO_MM, 2),
                y_mm=round(group["y_in"] * INCH_TO_MM, 2),
                diameter_mm=round(diameter, 2),
                label=label,
                powder_coat_margin=True,
                icon=icon,
            )
        )
    return holes


def _coordinate_groups(words: list[dict[str, Any]]) -> list[dict[str, float]]:
    rows = _rows_from_words(words)
    groups: list[dict[str, float]] = []
    for top, row in rows:
        row = sorted(row, key=lambda w: float(w["x0"]))
        idx = 0
        while idx < len(row):
            if str(row[idx].get("text", "")).lower() != "x:":
                idx += 1
                continue
            if idx + 3 >= len(row):
                idx += 1
                continue
            x_word, y_marker, y_word = row[idx + 1], row[idx + 2], row[idx + 3]
            if str(y_marker.get("text", "")).lower() != "y:":
                idx += 1
                continue
            x_raw = str(x_word.get("text", ""))
            y_raw = str(y_word.get("text", ""))
            if not _COORD_VALUE_RE.match(x_raw) or not _COORD_VALUE_RE.match(y_raw):
                idx += 1
                continue
            groups.append(
                {
                    "top": top,
                    "x0": float(row[idx]["x0"]),
                    "cx": (
                        float(row[idx]["x0"]) + float(y_word.get("x1", y_word["x0"]))
                    )
                    / 2,
                    "x_in": float(x_raw.rstrip(",")),
                    "y_in": float(y_raw.rstrip(",")),
                }
            )
            idx += 4
    return groups


def _rows_from_words(words: list[dict[str, Any]]) -> list[tuple[float, list[dict[str, Any]]]]:
    rows: list[tuple[float, list[dict[str, Any]]]] = []
    for word in sorted(words, key=lambda w: (float(w["top"]), float(w["x0"]))):
        top = float(word["top"])
        if rows and abs(rows[-1][0] - top) <= 3.0:
            rows[-1][1].append(word)
        else:
            rows.append((top, [word]))
    return rows


def _diameter_words(words: list[dict[str, Any]]) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for word in words:
        text = str(word.get("text", ""))
        mm = _diameter_mm(text)
        if mm is None:
            continue
        out.append(
            {
                "top": float(word["top"]),
                "cx": (float(word["x0"]) + float(word.get("x1", word["x0"]))) / 2,
                "mm": mm,
            }
        )
    return out


def _nearest_diameter_mm(
    group: dict[str, float], diameters: list[dict[str, float]]
) -> float | None:
    candidates = [
        d
        for d in diameters
        if 0.0 <= d["top"] - group["top"] <= 18.0
        and abs(d["cx"] - group["cx"]) <= 35.0
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda d: (abs(d["cx"] - group["cx"]), abs(d["top"] - group["top"])),
    )["mm"]


def _diameter_mm(text: str) -> float | None:
    match = _DIAMETER_RE.search(text.replace("”", "").replace('"', ""))
    if not match:
        return None
    frac = Fraction(int(match.group(1)), int(match.group(2)))
    return float(frac) * INCH_TO_MM


def _label_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for word in words:
        text = str(word.get("text", "")).upper().strip()
        if text in _LABELS:
            labels.append(word)
    return labels


def _nearest_label(group: dict[str, float], labels: list[dict[str, Any]]) -> str | None:
    candidates = []
    for label in labels:
        top = float(label["top"])
        if top > group["top"] + 1.0:
            continue
        cx = (float(label["x0"]) + float(label.get("x1", label["x0"]))) / 2
        dy = abs(top - group["top"])
        dx = abs(cx - group["cx"])
        if dy <= 70.0 and dx <= 55.0:
            candidates.append((dy, dx, str(label["text"]).upper()))
    if not candidates:
        return None
    return min(candidates)[2]


def _icon_for_label(label: str | None, diameter_mm: float) -> IconKind:
    if label == "LED":
        return "led"
    if label == "FOOTSWITCH":
        return "footswitch"
    if label in {"MODE", "CLIP"}:
        return "toggle"
    if label == "DC":
        return "dc-jack"
    if label in {"IN", "OUT"}:
        return "jack"
    if diameter_mm >= 10.5:
        return "footswitch"
    if diameter_mm <= 5.5:
        return "led"
    if diameter_mm <= 6.6:
        return "toggle"
    return "pot"


def _infer_top_jack_holes(words: list[dict[str, Any]]) -> list[Hole]:
    labels = _label_words(words)
    top_labels = {
        str(w["text"]).upper()
        for w in labels
        if str(w["text"]).upper() in {"OUT", "DC", "IN"} and float(w["top"]) < 340.0
    }
    if not {"OUT", "DC", "IN"}.issubset(top_labels):
        return []

    spacing_mm = 0.625 * INCH_TO_MM
    return [
        Hole(
            side="B",
            x_mm=round(-spacing_mm, 2),
            y_mm=0.0,
            diameter_mm=round((3 / 8) * INCH_TO_MM, 2),
            label="OUT",
            icon="jack",
        ),
        Hole(
            side="B",
            x_mm=0.0,
            y_mm=0.0,
            diameter_mm=round(0.5 * INCH_TO_MM, 2),
            label="DC",
            icon="dc-jack",
        ),
        Hole(
            side="B",
            x_mm=round(spacing_mm, 2),
            y_mm=0.0,
            diameter_mm=round((3 / 8) * INCH_TO_MM, 2),
            label="IN",
            icon="jack",
        ),
    ]


def _apply_enclosure_transform_and_validation(
    holes: list[Hole],
    enclosure: Enclosure | None,
) -> list[Hole]:
    if enclosure is None:
        return holes

    normalized: list[Hole] = []
    for hole in holes:
        face = enclosure.faces.get(hole.side)
        if face is None:
            normalized.append(hole)
            continue

        x_mm = _normalize_axis_to_center(hole.x_mm, face.width_mm)
        y_mm = _normalize_axis_to_center(hole.y_mm, face.height_mm)
        if not _hole_fits_face(x_mm, y_mm, hole.diameter_mm, face.width_mm, face.height_mm):
            continue

        normalized.append(
            Hole(
                side=hole.side,
                x_mm=round(x_mm, 2),
                y_mm=round(y_mm, 2),
                diameter_mm=hole.diameter_mm,
                label=hole.label,
                powder_coat_margin=hole.powder_coat_margin,
                icon=hole.icon,
            )
        )

    return normalized


def _normalize_axis_to_center(value_mm: float, span_mm: float) -> float:
    centered_limit = (span_mm / 2) + _FACE_COORD_TOL_MM
    if -centered_limit <= value_mm <= centered_limit:
        return value_mm

    # Some source docs use edge-origin coordinates; recenter to the
    # face midpoint so downstream consumers always receive center-origin mm.
    edge_limit = span_mm + _FACE_COORD_TOL_MM
    if -_FACE_COORD_TOL_MM <= value_mm <= edge_limit:
        return value_mm - (span_mm / 2)

    return value_mm


def _hole_fits_face(
    x_mm: float,
    y_mm: float,
    diameter_mm: float,
    width_mm: float,
    height_mm: float,
) -> bool:
    half_w = width_mm / 2
    half_h = height_mm / 2
    if abs(x_mm) > half_w + _FACE_COORD_TOL_MM:
        return False
    if abs(y_mm) > half_h + _FACE_COORD_TOL_MM:
        return False
    return 0.0 < diameter_mm <= min(width_mm, height_mm) + _FACE_COORD_TOL_MM


def _dedupe(holes: list[Hole]) -> list[Hole]:
    out: list[Hole] = []
    for hole in holes:
        if not any(
            existing.side == hole.side
            and abs(existing.x_mm - hole.x_mm) < 0.3
            and abs(existing.y_mm - hole.y_mm) < 0.3
            for existing in out
        ):
            out.append(hole)
    return out


__all__ = [
    "extract_drill_holes",
    "_apply_enclosure_transform_and_validation",
    "_diameter_mm",
]
