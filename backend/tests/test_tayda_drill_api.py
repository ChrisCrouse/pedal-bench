"""Tests for the Tayda Manufacturing Center drill-template API client.

The parser is tested against a captured payload (fuzz-face's 7 holes —
real response captured 2026-04-25). Live network is exercised by the
end-to-end tests in /scripts, not here.
"""

from __future__ import annotations

from pedal_bench.io.tayda_drill_api import (
    _parse_box_design,
    public_key_from_url,
)


# Captured 2026-04-25 from
#   GET https://api.taydakits.com/api/v4/box_designs/new?public_key=TG1mR0tsZ1JLTWNaNHpoSUJkTk95Zz09Cg==
#   (the fuzz-face Taydakits build)
FUZZ_FACE_PAYLOAD = {
    "box_design": {
        "id": 10200,
        "name": "DH.TB1",
        "enclosure_type": "1590B",
        "hole_count": 7,
        "box_design_holes": [
            {"box_side": "A", "diameter": 8.0, "position_x": 14.0, "position_y": 38.0},
            {"box_side": "A", "diameter": 8.0, "position_x": -14.0, "position_y": 38.0},
            {"box_side": "A", "diameter": 3.2, "position_x": 0.0, "position_y": 4.5},
            {"box_side": "A", "diameter": 13.0, "position_x": 0.0, "position_y": -22.0},
            {"box_side": "C", "diameter": 10.5, "position_x": 0.0, "position_y": -3.0},
            {"box_side": "E", "diameter": 10.5, "position_x": 0.0, "position_y": -3.0},
            {"box_side": "E", "diameter": 9.0, "position_x": 1.5, "position_y": -25.5},
        ],
        "box_design_lines": [],
        "box_design_shapes": [],
    }
}


# ---- public_key extraction ----------------------------------------------

class TestPublicKeyFromUrl:
    def test_extracts_key_from_canonical_url(self) -> None:
        url = (
            "https://drill.taydakits.com/box-designs/new"
            "?public_key=TG1mR0tsZ1JLTWNaNHpoSUJkTk95Zz09Cg=="
        )
        assert public_key_from_url(url) == "TG1mR0tsZ1JLTWNaNHpoSUJkTk95Zz09Cg=="

    def test_returns_none_for_non_drill_host(self) -> None:
        assert public_key_from_url("https://taydakits.com/foo?public_key=abc") is None

    def test_returns_none_for_empty_url(self) -> None:
        assert public_key_from_url("") is None

    def test_returns_none_when_param_missing(self) -> None:
        assert (
            public_key_from_url("https://drill.taydakits.com/box-designs/new") is None
        )


# ---- payload parsing -----------------------------------------------------

class TestParseBoxDesign:
    def test_parses_fuzz_face_seven_holes(self) -> None:
        holes = _parse_box_design(FUZZ_FACE_PAYLOAD)
        assert len(holes) == 7

    def test_preserves_coordinates_and_diameters(self) -> None:
        holes = _parse_box_design(FUZZ_FACE_PAYLOAD)
        # Hole 4 in the fuzz-face image is the 13mm footswitch on face A.
        fs = next(
            h for h in holes
            if h.side == "A" and h.diameter_mm == 13.0
        )
        assert fs.x_mm == 0.0
        assert fs.y_mm == -22.0
        assert fs.icon == "footswitch"

        # Hole 5 is the 3.2mm LED on face A.
        led = next(
            h for h in holes
            if h.side == "A" and h.diameter_mm == 3.2
        )
        assert led.icon == "led"
        assert led.label == "LED"

    def test_classifies_side_jacks(self) -> None:
        holes = _parse_box_design(FUZZ_FACE_PAYLOAD)
        side_c = [h for h in holes if h.side == "C"]
        side_e = [h for h in holes if h.side == "E"]
        assert len(side_c) == 1
        assert len(side_e) == 2
        # Side jacks default to "jack" icon.
        assert all(h.icon == "jack" for h in side_c + side_e)

    def test_drops_invalid_diameter(self) -> None:
        bad = {
            "box_design": {
                "box_design_holes": [
                    {"box_side": "A", "diameter": 0, "position_x": 0, "position_y": 0},
                    {"box_side": "A", "diameter": 50, "position_x": 0, "position_y": 0},
                    {"box_side": "A", "diameter": 8, "position_x": 0, "position_y": 0},
                ]
            }
        }
        holes = _parse_box_design(bad)
        assert len(holes) == 1

    def test_drops_invalid_side(self) -> None:
        bad = {
            "box_design": {
                "box_design_holes": [
                    {"box_side": "Z", "diameter": 8, "position_x": 0, "position_y": 0},
                    {"box_side": "A", "diameter": 8, "position_x": 0, "position_y": 0},
                ]
            }
        }
        holes = _parse_box_design(bad)
        assert len(holes) == 1
        assert holes[0].side == "A"

    def test_handles_missing_box_design(self) -> None:
        assert _parse_box_design({}) == []
        assert _parse_box_design({"box_design": None}) == []
        assert _parse_box_design({"box_design": {}}) == []
