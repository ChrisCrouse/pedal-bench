from __future__ import annotations

import json
from pathlib import Path

import pytest

from pedal_bench.core.models import Enclosure, Hole
from pedal_bench.io.stl_builder import (
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


def test_single_shell_is_watertight(tmp_path: Path) -> None:
    holes = [
        Hole(side="A", x_mm=0, y_mm=0, diameter_mm=7.2, label="KNOB"),
    ]
    out = tmp_path / "guide.stl"
    from build123d import export_stl

    # 125B face A is 66 x 121.5 mm (portrait).
    part = build_wrap_around_shell(66.0, 121.5, holes)
    export_stl(part, str(out))

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
    path = export_face_guide_stl(enclosures["125B"], "A", holes, tmp_path / "guide_A.stl")
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
    results = export_all_face_guides(enclosures["125B"], holes, tmp_path)
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
    from pedal_bench.io.stl_builder import build_face_guide  # noqa: F401
    encs_key = "125B"
    data = json.loads(
        (Path(__file__).parent.parent / "pedal_bench" / "data" / "enclosures.json").read_text(
            encoding="utf-8"
        )
    )
    encl = Enclosure.from_json(encs_key, data[encs_key])

    # Build two shells with the same nominal diameter, one with margin, one without.
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
