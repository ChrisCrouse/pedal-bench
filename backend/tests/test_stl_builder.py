from __future__ import annotations

import json
from pathlib import Path

import pytest

from pedal_bench.core.models import Enclosure, Hole
from pedal_bench.io.stl_builder import (
    DEFAULT_PILOT_DIAMETER_MM,
    build_wrap_around_shell,
    export_all_face_guides,
    export_face_guide_stl,
)


@pytest.fixture(scope="module")
def enclosures() -> dict[str, Enclosure]:
    data = json.loads(
        (Path(__file__).parent.parent / "pedal_bench" / "data" / "enclosures.json").read_text(
            encoding="utf-8"
        )
    )
    return {k: Enclosure.from_json(k, v) for k, v in data.items() if not k.startswith("_")}


def _watertight(path: Path) -> tuple[bool, float, list[list[float]]]:
    import trimesh
    mesh = trimesh.load_mesh(str(path))
    return bool(mesh.is_watertight), float(mesh.volume), mesh.bounds.tolist()


def _export(part, path: Path) -> None:
    from build123d import export_stl
    export_stl(part, str(path))


def test_single_shell_is_watertight(tmp_path: Path) -> None:
    holes = [
        Hole(side="A", x_mm=0, y_mm=0, diameter_mm=7.2, label="KNOB"),
    ]
    out = tmp_path / "guide.stl"

    # 125B face A is 66 x 121.5 mm (portrait).
    part = build_wrap_around_shell(66.0, 121.5, holes, template_mode="full")
    _export(part, out)

    wt, vol, bbox = _watertight(out)
    assert wt, "shell must be watertight"
    assert vol > 0
    # Outer footprint X = face_w + 2*(wall+clearance) = 66 + 4.6 = 70.6
    assert bbox[0][0] == pytest.approx(-35.3, abs=0.05)
    assert bbox[1][0] == pytest.approx(35.3, abs=0.05)
    # Outer footprint Y = face_h + 2*(wall+clearance) = 121.5 + 4.6 = 126.1
    assert bbox[0][1] == pytest.approx(-63.05, abs=0.05)
    assert bbox[1][1] == pytest.approx(63.05, abs=0.05)
    # Z extent = total_h = skirt_h (5) + top_t (3) = 8, span [-5, +3]
    assert bbox[0][2] == pytest.approx(-5.0, abs=0.05)
    assert bbox[1][2] == pytest.approx(3.0, abs=0.05)


def test_export_face_guide_stl(tmp_path: Path, enclosures: dict[str, Enclosure]) -> None:
    holes = [Hole(side="A", x_mm=0, y_mm=0, diameter_mm=12.2)]
    path = export_face_guide_stl(
        enclosures["125B"], "A", holes, tmp_path / "guide_A.stl",
        template_mode="full",
    )
    assert path.is_file()
    assert path.stat().st_size > 0
    wt, _, _ = _watertight(path)
    assert wt


def test_export_all_face_guides_sherwood_shape(
    tmp_path: Path, enclosures: dict[str, Enclosure]
) -> None:
    holes = [
        # Face A: 4 pots + LED
        Hole(side="A", x_mm=-22, y_mm=12, diameter_mm=7.2, label="LEVEL"),
        Hole(side="A", x_mm=22,  y_mm=12, diameter_mm=7.2, label="DRIVE"),
        Hole(side="A", x_mm=-22, y_mm=-12, diameter_mm=7.2, label="BASS"),
        Hole(side="A", x_mm=22,  y_mm=-12, diameter_mm=7.2, label="TREBLE"),
        Hole(side="A", x_mm=0,   y_mm=0,   diameter_mm=5.0, label="LED"),
        # Side B: input + output + DC jacks
        Hole(side="B", x_mm=-18, y_mm=0, diameter_mm=9.7, label="INPUT"),
        Hole(side="B", x_mm=18,  y_mm=0, diameter_mm=9.7, label="OUTPUT"),
        Hole(side="B", x_mm=0,   y_mm=8, diameter_mm=8.1, label="DC"),
        # Side D: footswitch
        Hole(side="D", x_mm=0, y_mm=0, diameter_mm=12.2, label="FOOTSWITCH"),
    ]
    results = export_all_face_guides(
        enclosures["125B"], holes, tmp_path, template_mode="full"
    )
    assert set(results.keys()) == {"A", "B", "D"}
    for side, path in results.items():
        wt, vol, bbox = _watertight(path)
        assert wt, f"side {side} not watertight"
        assert vol > 0
        # Z extents should be [-skirt_h, +top_t] = [-5, +3] regardless of face.
        assert bbox[0][2] == pytest.approx(-5.0, abs=0.05)
        assert bbox[1][2] == pytest.approx(3.0, abs=0.05)


def test_zero_holes_still_produces_valid_shell(tmp_path: Path, enclosures: dict[str, Enclosure]) -> None:
    path = export_face_guide_stl(enclosures["125B"], "A", [], tmp_path / "blank.stl")
    wt, vol, _ = _watertight(path)
    assert wt
    assert vol > 0


def test_powder_coat_margin_enlarges_hole() -> None:
    # Margin logic lives on the Hole model itself; verify here so a
    # change in stl_builder defaults can't silently break callers.
    nominal = Hole(side="A", x_mm=0, y_mm=0, diameter_mm=10.0, powder_coat_margin=False)
    margined = Hole(side="A", x_mm=0, y_mm=0, diameter_mm=10.0, powder_coat_margin=True)
    assert margined.effective_diameter_mm() == 10.4
    assert nominal.effective_diameter_mm() == 10.0


def test_invalid_dimensions_raise() -> None:
    with pytest.raises(ValueError):
        build_wrap_around_shell(-1, 10, [])
    with pytest.raises(ValueError):
        build_wrap_around_shell(10, 10, [], skirt_h=0)
    with pytest.raises(ValueError):
        build_wrap_around_shell(10, 10, [], top_t=-1)


def test_unknown_template_mode_raises() -> None:
    with pytest.raises(ValueError):
        build_wrap_around_shell(50, 50, [], template_mode="bogus")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Pilot / mark mode geometry tests
# ---------------------------------------------------------------------------


def _bore_radius_at(mesh, x: float, y: float, z_inside_slab: float) -> float | None:
    """Return the bore radius at the given xy by probing containment at
    a z-height inside the slab. Returns None if the slab is solid at
    that xy (no bore through it).
    """
    import numpy as np

    # If the on-axis point is inside the part, there's no bore here.
    on_axis = np.array([[x, y, z_inside_slab]])
    if mesh.contains(on_axis)[0]:
        return None
    # Bisection outward to find the bore wall.
    lo, hi = 0.0, 50.0
    for _ in range(40):
        mid = (lo + hi) / 2.0
        probe = np.array([[x + mid, y, z_inside_slab]])
        if mesh.contains(probe)[0]:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def test_pilot_mode_makes_small_through_hole(tmp_path: Path) -> None:
    import trimesh

    holes = [Hole(side="A", x_mm=0, y_mm=0, diameter_mm=12.2, label="FOOTSWITCH")]
    out = tmp_path / "pilot.stl"
    part = build_wrap_around_shell(
        66.0, 121.5, holes,
        template_mode="pilot",
        show_final_size_ring=False,
    )
    _export(part, out)

    mesh = trimesh.load_mesh(str(out))
    assert mesh.is_watertight, "pilot-mode shell must be watertight"

    # Probe well below the countersink (z=1.0) so we measure the pilot
    # bore, not the wider conical opening.
    r = _bore_radius_at(mesh, 0.0, 0.0, z_inside_slab=1.0)
    assert r is not None, "pilot mode should leave a through-hole"
    expected_r = DEFAULT_PILOT_DIAMETER_MM / 2.0
    assert r == pytest.approx(expected_r, abs=0.15), (
        f"pilot bore radius {r:.3f} mm differs from expected {expected_r:.3f} mm"
    )


def test_mark_mode_has_no_through_hole(tmp_path: Path) -> None:
    import numpy as np
    import trimesh

    holes = [Hole(side="A", x_mm=0, y_mm=0, diameter_mm=12.2, label="FOOTSWITCH")]
    out = tmp_path / "mark.stl"
    part = build_wrap_around_shell(
        66.0, 121.5, holes,
        template_mode="mark",
        show_final_size_ring=False,
    )
    _export(part, out)

    mesh = trimesh.load_mesh(str(out))
    assert mesh.is_watertight, "mark-mode shell must be watertight"

    # A point well below the countersink but still inside the slab must
    # be solid (no through-hole at the origin).
    countersink_depth = 1.0
    z_below = 3.0 - countersink_depth - 0.5  # 0.5 mm under the countersink tip
    sample = np.array([[0.0, 0.0, z_below]])
    assert mesh.contains(sample)[0], (
        "mark mode must leave the slab solid below the countersink dimple"
    )

    # And a point at the very top surface, on-axis, must be inside the
    # countersink void (i.e., NOT inside the part).
    top_sample = np.array([[0.0, 0.0, 3.0 - 0.05]])
    assert not mesh.contains(top_sample)[0], (
        "mark mode must carve a dimple at the top surface"
    )


def test_pilot_mode_volume_smaller_than_full_mode(tmp_path: Path) -> None:
    """Pilot mode should remove much less material than full mode for
    the same hole — large component diameters become small pilot bores.
    """
    holes = [
        Hole(side="A", x_mm=-22, y_mm=12, diameter_mm=12.2),
        Hole(side="A", x_mm=22, y_mm=12, diameter_mm=12.2),
        Hole(side="A", x_mm=-22, y_mm=-12, diameter_mm=12.2),
        Hole(side="A", x_mm=22, y_mm=-12, diameter_mm=12.2),
    ]
    pilot_out = tmp_path / "pilot.stl"
    full_out = tmp_path / "full.stl"
    _export(
        build_wrap_around_shell(
            66.0, 121.5, holes,
            template_mode="pilot",
            show_final_size_ring=False,
        ),
        pilot_out,
    )
    _export(
        build_wrap_around_shell(66.0, 121.5, holes, template_mode="full"),
        full_out,
    )
    _, pilot_vol, _ = _watertight(pilot_out)
    _, full_vol, _ = _watertight(full_out)
    # Pilot mode preserves more material.
    assert pilot_vol > full_vol, (
        f"pilot vol {pilot_vol:.1f} should exceed full vol {full_vol:.1f}"
    )


def test_final_size_ring_removes_extra_material(tmp_path: Path) -> None:
    """Toggling the final-size ring on should remove a small amount of
    additional material (the debossed annulus) compared to no ring.
    """
    holes = [
        Hole(side="A", x_mm=0, y_mm=0, diameter_mm=12.2),
    ]
    no_ring = tmp_path / "no_ring.stl"
    with_ring = tmp_path / "with_ring.stl"
    _export(
        build_wrap_around_shell(
            66.0, 121.5, holes,
            template_mode="pilot",
            show_final_size_ring=False,
        ),
        no_ring,
    )
    _export(
        build_wrap_around_shell(
            66.0, 121.5, holes,
            template_mode="pilot",
            show_final_size_ring=True,
        ),
        with_ring,
    )
    _, vol_no, _ = _watertight(no_ring)
    _, vol_yes, _ = _watertight(with_ring)
    assert vol_yes < vol_no, "ring deboss should reduce volume"
    # Sanity bound: the deboss is small (< ~1 mm³ per hole at these defaults
    # times safety margin), should not be a huge difference.
    assert (vol_no - vol_yes) < 50.0
