"""Parametric 3D-printable drill-guide generator using build123d.

Produces a **wrap-around shell** that slips over the drilled face of a
Hammond enclosure and self-locates via a skirt wrapping the adjacent
side walls.

The shell can carry one of three hole styles per export, controlled by
``template_mode``:

* ``"pilot"`` (default) — small through-hole (~3 mm) sized for a center
  punch, with a conical countersink on the top surface that self-centers
  the punch tip. Best general-purpose drilling guide; reusable across
  many builds because no full-size bit ever passes through it.
* ``"mark"`` — countersunk dimple only, no through-hole. Strongest /
  most reusable; pure punch guide.
* ``"full"`` — through-hole at the component's final diameter (the
  original behavior). Rarely the right choice for FDM prints because a
  full-size twist bit chews the guide oversized on first use, but kept
  for users who want it (e.g., aligning a Forstner bit, or prints in
  rigid material).

Both ``pilot`` and ``mark`` modes can additionally emboss a thin
debossed ring on the top surface at each hole's *final* diameter — a
visual sanity check that components won't collide before drilling.

Geometry (all mm, origin at the center of the guide's top surface):

    z = +top_t          ─  top of guide
    z = 0               ─  top face of the enclosure sits here
    z = -skirt_h        ─  bottom edge of the skirt

    X, Y                ─  Tayda face coordinates (same as Hole.x_mm/y_mm)

The `build123d` import is deferred inside functions so importing this
module stays cheap — OCP bindings take ~2 s to load on Windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, Sequence

from pedal_bench.core.models import Enclosure, Hole, Side

if TYPE_CHECKING:
    from build123d import Part  # pragma: no cover

# Defaults chosen for 125B-class enclosures printed in PLA/PETG on a
# consumer FDM printer. Override via kwargs when a specific build calls for it.
DEFAULT_SKIRT_H = 5.0
DEFAULT_TOP_T = 3.0
DEFAULT_WALL = 2.0
DEFAULT_CLEARANCE = 0.3

# Pilot/mark template defaults.
DEFAULT_TEMPLATE_MODE: "TemplateMode" = "pilot"
DEFAULT_PILOT_DIAMETER_MM = 3.0      # fits common spring-loaded center punches
DEFAULT_COUNTERSINK_DIAMETER_MM = 5.0
DEFAULT_COUNTERSINK_DEPTH_MM = 1.0
DEFAULT_RING_DEPTH_MM = 0.4
DEFAULT_RING_WIDTH_MM = 0.4

TemplateMode = Literal["pilot", "mark", "full"]


def build_wrap_around_shell(
    face_w_mm: float,
    face_h_mm: float,
    holes: Sequence[Hole],
    *,
    skirt_h: float = DEFAULT_SKIRT_H,
    top_t: float = DEFAULT_TOP_T,
    wall: float = DEFAULT_WALL,
    clearance: float = DEFAULT_CLEARANCE,
    template_mode: TemplateMode = DEFAULT_TEMPLATE_MODE,
    pilot_diameter_mm: float = DEFAULT_PILOT_DIAMETER_MM,
    countersink_diameter_mm: float = DEFAULT_COUNTERSINK_DIAMETER_MM,
    countersink_depth_mm: float = DEFAULT_COUNTERSINK_DEPTH_MM,
    show_final_size_ring: bool = True,
    ring_depth_mm: float = DEFAULT_RING_DEPTH_MM,
    ring_width_mm: float = DEFAULT_RING_WIDTH_MM,
) -> "Part":
    """Build a single-face drill guide as a build123d Part.

    Args:
        face_w_mm, face_h_mm: outer dimensions of the enclosure face
            (the side we're drilling through).
        holes: iterable of Hole records. Only the x_mm/y_mm/effective
            diameter are used; `side` is ignored (caller has already
            filtered to the face being built).
        skirt_h: how far the shell wraps down the side walls.
        top_t: thickness of the solid top slab.
        wall: shell wall thickness around the outside.
        clearance: air gap between shell inner wall and enclosure outer
            wall; tuned so the guide slips on without binding.
        template_mode: ``"pilot"`` (small through-hole + countersink),
            ``"mark"`` (countersink only, no through-hole), or
            ``"full"`` (through-hole at component's final diameter).
        pilot_diameter_mm: through-hole diameter in ``pilot`` mode.
        countersink_diameter_mm: outer diameter of the conical
            countersink (top surface). Tapers to ``pilot_diameter_mm``
            in ``pilot`` mode and to a point in ``mark`` mode.
        countersink_depth_mm: depth of the conical countersink.
        show_final_size_ring: in ``pilot``/``mark`` modes, deboss a thin
            ring on the top surface at each hole's final diameter as a
            visual sanity check. Ignored in ``full`` mode.
        ring_depth_mm, ring_width_mm: dimensions of the debossed ring.

    Returns:
        A build123d Part. Subtract / union / export to taste.
    """
    from build123d import Box, Cone, Cylinder, Location

    if face_w_mm <= 0 or face_h_mm <= 0:
        raise ValueError(f"face_w_mm and face_h_mm must be positive")
    if skirt_h <= 0 or top_t <= 0 or wall <= 0:
        raise ValueError("skirt_h, top_t, wall must all be positive")
    if template_mode not in ("pilot", "mark", "full"):
        raise ValueError(f"unknown template_mode: {template_mode!r}")
    if template_mode in ("pilot", "mark"):
        if countersink_depth_mm <= 0 or countersink_depth_mm >= top_t:
            raise ValueError(
                "countersink_depth_mm must be > 0 and < top_t "
                f"(got {countersink_depth_mm} vs top_t={top_t})"
            )
        if countersink_diameter_mm <= 0:
            raise ValueError("countersink_diameter_mm must be positive")
    if template_mode == "pilot":
        if pilot_diameter_mm <= 0:
            raise ValueError("pilot_diameter_mm must be positive")
        if pilot_diameter_mm >= countersink_diameter_mm:
            raise ValueError(
                "pilot_diameter_mm must be smaller than countersink_diameter_mm"
            )

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

    # Per-hole features. Geometry differs by mode but always sits on the
    # top slab between z=0 and z=top_t; ring deboss bites into the top
    # surface only.
    cyl_overshoot = 2.0  # poke out the top/bottom so booleans yield clean openings
    for h in holes:
        final_d = h.effective_diameter_mm()
        if final_d <= 0:
            continue

        if template_mode == "full":
            cyl = Cylinder(final_d / 2.0, top_t + cyl_overshoot).locate(
                Location((h.x_mm, h.y_mm, top_t / 2.0))
            )
            shell = shell - cyl
            # No ring in full mode — the through-hole already shows final size.
            continue

        # pilot or mark — both get a conical countersink that opens at
        # the top surface (z = top_t) and tapers down into the slab. To
        # avoid coplanar-face boolean glitches, the cone is extended
        # slightly above the top surface using its own linear taper.
        if template_mode == "pilot":
            narrow_r = pilot_diameter_mm / 2.0
        else:  # "mark"
            # Non-zero tiny radius avoids a degenerate cone apex that
            # OCCT can render as a non-manifold point.
            narrow_r = 0.05
        wide_r = countersink_diameter_mm / 2.0
        slope = (wide_r - narrow_r) / countersink_depth_mm
        cone_overshoot = 0.5
        cone_h = countersink_depth_mm + cone_overshoot
        cone_top_r = wide_r + slope * cone_overshoot
        cone_center_z = (top_t - countersink_depth_mm) + cone_h / 2.0
        cone = Cone(
            bottom_radius=narrow_r,
            top_radius=cone_top_r,
            height=cone_h,
        ).locate(
            Location((h.x_mm, h.y_mm, cone_center_z))
        )
        shell = shell - cone

        if template_mode == "pilot":
            pilot = Cylinder(
                pilot_diameter_mm / 2.0, top_t + cyl_overshoot
            ).locate(Location((h.x_mm, h.y_mm, top_t / 2.0)))
            shell = shell - pilot

        if show_final_size_ring and final_d > countersink_diameter_mm:
            # Annular deboss at the top surface: outer cyl minus inner cyl.
            outer_r = final_d / 2.0
            inner_r = max(outer_r - ring_width_mm, countersink_diameter_mm / 2.0)
            if outer_r - inner_r > 1e-3:
                ring_cyl_h = ring_depth_mm + cyl_overshoot
                ring_center_z = top_t - ring_depth_mm / 2.0 + cyl_overshoot / 2.0
                outer_cyl = Cylinder(outer_r, ring_cyl_h).locate(
                    Location((h.x_mm, h.y_mm, ring_center_z))
                )
                inner_cyl = Cylinder(inner_r, ring_cyl_h + 0.1).locate(
                    Location((h.x_mm, h.y_mm, ring_center_z))
                )
                ring = outer_cyl - inner_cyl
                shell = shell - ring

    return shell


def build_face_guide(
    enclosure: Enclosure,
    side: Side,
    all_holes: Sequence[Hole],
    **kwargs,
) -> "Part":
    """Build a guide for `side`, using whichever holes match that side.

    Skirt / wall / clearance / template_mode and related kwargs are
    forwarded to :func:`build_wrap_around_shell`.
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
    "TemplateMode",
    "build_wrap_around_shell",
    "build_face_guide",
    "export_face_guide_stl",
    "export_all_face_guides",
    "DEFAULT_SKIRT_H",
    "DEFAULT_TOP_T",
    "DEFAULT_WALL",
    "DEFAULT_CLEARANCE",
    "DEFAULT_TEMPLATE_MODE",
    "DEFAULT_PILOT_DIAMETER_MM",
    "DEFAULT_COUNTERSINK_DIAMETER_MM",
    "DEFAULT_COUNTERSINK_DEPTH_MM",
    "DEFAULT_RING_DEPTH_MM",
    "DEFAULT_RING_WIDTH_MM",
]
