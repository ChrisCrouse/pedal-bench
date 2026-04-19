"""Parametric 3D-printable drill-guide generator using build123d.

Produces a **wrap-around shell** that slips over the drilled face of a
Hammond enclosure and self-locates via a skirt wrapping the adjacent
side walls. Each hole on the drilled face becomes a cylindrical through-
hole in the guide's top slab, sized to the enclosure's desired hole
diameter (+0.4 mm powder-coat margin if set on the Hole).

Geometry (all mm, origin at the center of the guide's top surface):

    z = +top_t          \u2500  top of guide
    z = 0               \u2500  top face of the enclosure sits here
    z = -skirt_h        \u2500  bottom edge of the skirt

    X, Y                \u2500  Tayda face coordinates (same as Hole.x_mm/y_mm)

The `build123d` import is deferred inside functions so importing this
module stays cheap \u2014 OCP bindings take ~2 s to load on Windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from pedal_bench.core.models import Enclosure, Hole, Side

if TYPE_CHECKING:
    from build123d import Part  # pragma: no cover

# Defaults chosen for 125B-class enclosures printed in PLA/PETG on a
# consumer FDM printer. Override via kwargs when a specific build calls for it.
DEFAULT_SKIRT_H = 5.0
DEFAULT_TOP_T = 3.0
DEFAULT_WALL = 2.0
DEFAULT_CLEARANCE = 0.3


def build_wrap_around_shell(
    face_w_mm: float,
    face_h_mm: float,
    holes: Sequence[Hole],
    *,
    skirt_h: float = DEFAULT_SKIRT_H,
    top_t: float = DEFAULT_TOP_T,
    wall: float = DEFAULT_WALL,
    clearance: float = DEFAULT_CLEARANCE,
) -> "Part":
    """Build a single-face drill guide as a build123d Part.

    Args:
        face_w_mm, face_h_mm: outer dimensions of the enclosure face
            (the side we're drilling through).
        holes: iterable of Hole records. Only the x_mm/y_mm/effective
            diameter are used; `side` is ignored (caller has already
            filtered to the face being built).
        skirt_h: how far the shell wraps down the side walls.
        top_t: thickness of the solid top slab (through which the
            cylindrical holes pass).
        wall: shell wall thickness around the outside.
        clearance: air gap between shell inner wall and enclosure outer
            wall; tuned so the guide slips on without binding.

    Returns:
        A build123d Part. Subtract / union / export to taste.
    """
    from build123d import Box, Cylinder, Location

    if face_w_mm <= 0 or face_h_mm <= 0:
        raise ValueError(f"face_w_mm and face_h_mm must be positive")
    if skirt_h <= 0 or top_t <= 0 or wall <= 0:
        raise ValueError("skirt_h, top_t, wall must all be positive")

    outer_w = face_w_mm + 2.0 * (wall + clearance)
    outer_h = face_h_mm + 2.0 * (wall + clearance)
    total_h = top_t + skirt_h
    # Center the outer box so its z-extent is [-skirt_h, +top_t].
    outer_center_z = (top_t - skirt_h) / 2.0
    shell = Box(outer_w, outer_h, total_h).locate(
        Location((0.0, 0.0, outer_center_z))
    )

    # Cavity where the enclosure fits. Open at the bottom (z = -skirt_h),
    # closed at the top by the solid slab between z=0 and z=+top_t.
    inner_w = face_w_mm + 2.0 * clearance
    inner_h = face_h_mm + 2.0 * clearance
    pocket = Box(inner_w, inner_h, skirt_h).locate(
        Location((0.0, 0.0, -skirt_h / 2.0))
    )
    shell = shell - pocket

    # Through-hole cylinders. Overextend top/bottom so the boolean
    # subtract yields a clean open hole with no slivers.
    cyl_h = top_t + 2.0
    cyl_center_z = top_t / 2.0  # z-range: [-1, top_t + 1]
    for h in holes:
        d = h.effective_diameter_mm()
        if d <= 0:
            continue
        cyl = Cylinder(d / 2.0, cyl_h).locate(
            Location((h.x_mm, h.y_mm, cyl_center_z))
        )
        shell = shell - cyl

    return shell


def build_face_guide(
    enclosure: Enclosure,
    side: Side,
    all_holes: Sequence[Hole],
    **kwargs,
) -> "Part":
    """Build a guide for `side`, using whichever holes match that side.

    Skirt / wall / clearance defaults can be overridden via kwargs.
    """
    face = enclosure.face(side)
    side_holes = [h for h in all_holes if h.side == side]
    return build_wrap_around_shell(face.width_mm, face.height_mm, side_holes, **kwargs)


def export_face_guide_stl(
    enclosure: Enclosure,
    side: Side,
    all_holes: Sequence[Hole],
    output_path: Path | str,
    **kwargs,
) -> Path:
    """Build and export a single face's guide to STL."""
    from build123d import export_stl

    part = build_face_guide(enclosure, side, all_holes, **kwargs)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_stl(part, str(output_path))
    return output_path


def export_all_face_guides(
    enclosure: Enclosure,
    holes: Sequence[Hole],
    output_dir: Path | str,
    *,
    filename_pattern: str = "guide_{side}.stl",
    **kwargs,
) -> dict[str, Path]:
    """Export one STL per face that has at least one hole.

    Returns a mapping of side -> written STL path.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    holes_by_side: dict[str, list[Hole]] = {}
    for h in holes:
        holes_by_side.setdefault(h.side, []).append(h)

    results: dict[str, Path] = {}
    for side, side_holes in sorted(holes_by_side.items()):
        if side not in enclosure.faces:
            # Skip any holes assigned to a side the enclosure doesn't define.
            continue
        path = output_dir / filename_pattern.format(side=side)
        export_face_guide_stl(enclosure, side, side_holes, path, **kwargs)
        results[side] = path
    return results


__all__ = [
    "build_wrap_around_shell",
    "build_face_guide",
    "export_face_guide_stl",
    "export_all_face_guides",
    "DEFAULT_SKIRT_H",
    "DEFAULT_TOP_T",
    "DEFAULT_WALL",
    "DEFAULT_CLEARANCE",
]
