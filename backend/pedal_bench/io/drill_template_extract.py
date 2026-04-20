"""Vector extraction of drill-template hole positions from PedalPCB PDFs.

PedalPCB drill-template pages render each enclosure face as a large
rectangular outline and each hole as a circle. Both are stored as
stroked Bezier curves in the PDF, which pdfplumber exposes via
`page.curves` with bounding-box coordinates.

Strategy
--------
1. Find the drill-template page by text match (``drill template`` +
   ``enclosure``).
2. Collect rectangle-like curves (aspect ratio far from 1, size large
   enough to be a face outline) and cluster them into the 5-face cross
   layout (A center, B above, D below, C left, E right).
3. Collect circle-like curves (aspect ratio ≈ 1, bbox in the plausible
   hole-size range of 2–18 mm) and assign each to the face whose bbox
   contains its center.
4. Convert each circle's PDF coordinates to Tayda-convention face-local
   mm (x+ right, y+ up, origin at face center — PDF is y-up, matching
   Tayda, so no axis flip is needed).
5. Heuristically assign icon kinds from hole diameter + face location:
   - diameter > 10.5 mm on face A  → footswitch
   - diameter < 5.5 mm on face A   → LED
   - else on face A                → pot
   - diameter < 8.5 mm on face B   → dc-jack
   - else on face B                → jack
   - on sides C / D / E            → jack (fallback)

Returns ``None`` if the page layout is too ambiguous to identify faces.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pedal_bench.core.models import Enclosure, Hole, IconKind, Side

PT_PER_MM = 72.0 / 25.4  # 2.8346 points per mm


@dataclass
class _FaceRect:
    side: Side
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1


def extract_drill_holes(
    pdf_path: Path | str, enclosure: Enclosure | None = None
) -> list[Hole] | None:
    """Extract holes from the drill-template page, or None if we can't."""
    import pdfplumber

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        page_index = _locate_drill_page(pdf)
        if page_index is None:
            return None
        page = pdf.pages[page_index]
        rect_curves = _rectangle_like_curves(page)
        circle_curves = _circle_like_curves(page)

    if not rect_curves or not circle_curves:
        return None

    faces = _classify_faces(rect_curves)
    if not faces:
        return None

    holes: list[Hole] = []
    for c in circle_curves:
        cx = (c["x0"] + c["x1"]) / 2
        cy = (c["y0"] + c["y1"]) / 2
        d_pt = ((c["x1"] - c["x0"]) + (c["y1"] - c["y0"])) / 2
        face = next((f for f in faces if f.contains(cx, cy)), None)
        if face is None:
            continue
        # PDF y+ matches Tayda y+ — no flip. Scale factor (mm per point)
        # derived from the face's known width in mm if we have the enclosure
        # spec, else assume a uniform scale from the main face rectangle.
        scale = _scale_for_face(face, enclosure)
        x_mm = (cx - face.cx) * scale
        y_mm = (cy - face.cy) * scale
        d_mm = d_pt * scale
        icon = _classify_icon(face.side, d_mm)
        label = _default_label(icon)
        holes.append(
            Hole(
                side=face.side,
                x_mm=round(x_mm, 2),
                y_mm=round(y_mm, 2),
                diameter_mm=round(d_mm, 2),
                label=label,
                powder_coat_margin=True,
                icon=icon,
            )
        )

    # Deduplicate coincident extractions (PDFs sometimes render a circle
    # as overlaid strokes; we get each as a curve).
    holes = _dedupe(holes)

    # Drop the PedalPCB logo: rects below face A that contain only small
    # (< 5 mm) circles are decorative artwork, not drill holes. Face A and
    # B always carry holes; C/D/E pass only if they have at least one
    # plausibly-sized circle (>= 5 mm).
    holes = _drop_decorative_sides(holes)

    if not holes:
        return None
    return holes


def _drop_decorative_sides(holes: list[Hole]) -> list[Hole]:
    """Filter out PedalPCB logo / other decorative artwork that looks
    superficially like holes.

    Strategy:
      - On any non-A face, require at least one "plausible" hole (between
        5.5 mm and 16 mm). If the face has no plausible holes, discard.
      - Within a face, drop tiny (< 4 mm) circles and circles that sit on
        top of a larger one (dedupe by near-position regardless of diameter);
        the PedalPCB logo's fine-detail strokes triggered false-positives.
    """
    PLAUSIBLE_MIN = 5.5
    PLAUSIBLE_MAX = 16.0
    TINY_MAX = 4.0

    by_side: dict[Side, list[Hole]] = {}
    for h in holes:
        by_side.setdefault(h.side, []).append(h)

    keep: list[Hole] = []
    for side, group in by_side.items():
        cleaned = [h for h in group if h.diameter_mm > TINY_MAX]
        cleaned = _dedupe_by_position(cleaned)
        if side == "A":
            keep.extend(cleaned)
            continue
        plausible = [h for h in cleaned if PLAUSIBLE_MIN <= h.diameter_mm <= PLAUSIBLE_MAX]
        # Side faces: a single isolated circle is almost always a PedalPCB
        # logo artifact; real side-face layouts always come in groups (2–3
        # jacks on side B, for instance). Require >= 2 plausible holes on
        # sides B/C/D/E; face A holes always pass (handled above).
        if len(plausible) >= 2:
            keep.extend(plausible)
    return keep


def _dedupe_by_position(holes: list[Hole]) -> list[Hole]:
    """Collapse overlapping circles at the same (x, y) into a single hole
    with the largest diameter — PedalPCB outlines are sometimes stroked
    twice, producing two curves at the same spot with slightly different radii.
    """
    out: list[Hole] = []
    for h in holes:
        match = next(
            (
                e
                for e in out
                if abs(e.x_mm - h.x_mm) < 0.6 and abs(e.y_mm - h.y_mm) < 0.6
            ),
            None,
        )
        if match is None:
            out.append(h)
        elif h.diameter_mm > match.diameter_mm:
            out.remove(match)
            out.append(h)
    return out


# ---- page location -------------------------------------------------------

def _locate_drill_page(pdf) -> int | None:
    for idx, page in enumerate(pdf.pages):
        try:
            text = (page.extract_text() or "").lower()
        except Exception:
            continue
        if "drill template" in text:
            return idx
    # Fallback: last page often is the drill template.
    if len(pdf.pages) >= 5:
        return len(pdf.pages) - 1
    return None


# ---- vector primitive extraction -----------------------------------------

def _rectangle_like_curves(page) -> list[dict[str, Any]]:
    """Curves or rects large enough to be face outlines."""
    out: list[dict[str, Any]] = []
    for obj in list(page.curves) + list(page.rects):
        w = float(obj["x1"] - obj["x0"])
        h = float(obj["y1"] - obj["y0"])
        if w < 60 or h < 60:        # minimum plausible face size in points
            continue
        if 0.85 <= w / h <= 1.15:   # too-square = likely not a face
            continue
        out.append(obj)
    return out


def _circle_like_curves(page) -> list[dict[str, Any]]:
    """Curves with roughly square bbox in the plausible hole-diameter range."""
    out: list[dict[str, Any]] = []
    for obj in page.curves:
        w = float(obj["x1"] - obj["x0"])
        h = float(obj["y1"] - obj["y0"])
        if w < 4 or h < 4:
            continue
        ar = w / h
        if ar < 0.85 or ar > 1.15:
            continue
        # 2–18 mm in points
        if w < 2 * PT_PER_MM or w > 18 * PT_PER_MM:
            continue
        out.append(obj)
    return out


# ---- face classification --------------------------------------------------

def _classify_faces(rects: list[dict[str, Any]]) -> list[_FaceRect]:
    """Identify up to 5 face rectangles arranged in a cross layout."""
    # Deduplicate overlapping rects (face outlines drawn as two overlaid strokes).
    uniq: list[dict[str, Any]] = []
    for r in rects:
        if not any(_bbox_similar(r, u) for u in uniq):
            uniq.append(r)

    if not uniq:
        return []

    # Face A = largest area.
    uniq.sort(key=lambda r: (r["x1"] - r["x0"]) * (r["y1"] - r["y0"]), reverse=True)
    a = uniq[0]
    a_face = _FaceRect("A", a["x0"], a["y0"], a["x1"], a["y1"])
    face_a_cx, face_a_cy = a_face.cx, a_face.cy

    candidates = uniq[1:]
    faces: dict[Side, _FaceRect] = {"A": a_face}  # type: ignore[dict-item]

    for r in candidates:
        cx = (r["x0"] + r["x1"]) / 2
        cy = (r["y0"] + r["y1"]) / 2
        w = r["x1"] - r["x0"]
        h = r["y1"] - r["y0"]
        dx = cx - face_a_cx
        dy = cy - face_a_cy

        # Skip anything whose center is inside face A (probably decorative).
        if a_face.contains(cx, cy):
            continue

        # Above/below: x-overlap with A, and wider than tall.
        x_overlap = max(0, min(r["x1"], a["x1"]) - max(r["x0"], a["x0"]))
        y_overlap = max(0, min(r["y1"], a["y1"]) - max(r["y0"], a["y0"]))
        mostly_x_aligned = x_overlap > 0.5 * min(w, a_face.w)
        mostly_y_aligned = y_overlap > 0.5 * min(h, a_face.h)

        if mostly_x_aligned and w > h:
            # PDF y+ is up → B (top of page, high y) is ABOVE A.
            side: Side = "B" if dy > 0 else "D"
            if side not in faces:
                faces[side] = _FaceRect(side, r["x0"], r["y0"], r["x1"], r["y1"])
        elif mostly_y_aligned and h > w:
            side = "C" if dx < 0 else "E"
            if side not in faces:
                faces[side] = _FaceRect(side, r["x0"], r["y0"], r["x1"], r["y1"])

    # We need at least face A and one side face to make useful sense.
    if "A" not in faces or len(faces) < 2:
        return []
    return list(faces.values())


def _bbox_similar(a: dict[str, Any], b: dict[str, Any], tol: float = 2.0) -> bool:
    return (
        abs(a["x0"] - b["x0"]) < tol
        and abs(a["y0"] - b["y0"]) < tol
        and abs(a["x1"] - b["x1"]) < tol
        and abs(a["y1"] - b["y1"]) < tol
    )


def _scale_for_face(face: _FaceRect, enclosure: Enclosure | None) -> float:
    """Return mm-per-point for this face.

    When we know the enclosure, scale off the face's expected width.
    Otherwise fall back to the PDF's native 1:1 scale (pt→mm at 72 DPI),
    which is right for templates drawn at actual size (most PedalPCB PDFs).
    """
    if enclosure is not None:
        face_spec = enclosure.faces.get(face.side)
        if face_spec is not None and face.w > 0:
            return float(face_spec.width_mm) / face.w
    return 1.0 / PT_PER_MM


# ---- icon inference -------------------------------------------------------

def _classify_icon(side: Side, diameter_mm: float) -> IconKind:
    if side == "A":
        if diameter_mm >= 10.5:
            return "footswitch"
        if diameter_mm <= 5.5:
            return "led"
        return "pot"
    if side == "B":
        if diameter_mm <= 8.5:
            return "dc-jack"
        return "jack"
    # Non-standard sides (C / D / E) — assume jack by default.
    return "jack"


def _default_label(icon: IconKind) -> str | None:
    return {
        "pot": "POT",
        "led": "LED",
        "footswitch": "FOOTSWITCH",
        "jack": "JACK",
        "dc-jack": "DC",
        "toggle": "TOGGLE",
        "chicken-head": "KNOB",
        "expression": "EXP",
    }.get(icon)


def _dedupe(holes: list[Hole]) -> list[Hole]:
    out: list[Hole] = []
    for h in holes:
        if not any(
            e.side == h.side
            and abs(e.x_mm - h.x_mm) < 0.3
            and abs(e.y_mm - h.y_mm) < 0.3
            and abs(e.diameter_mm - h.diameter_mm) < 0.3
            for e in out
        ):
            out.append(h)
    return out


__all__ = ["extract_drill_holes"]
