"""Tests for the AI drill-extract response parsing + plausibility filter.

Real API calls aren't tested here — only the pure logic that turns Claude's
tool_use output into Hole objects. Building fake response objects with the
shape anthropic's SDK returns keeps these tests offline-safe.
"""

from __future__ import annotations

from types import SimpleNamespace

from pedal_bench.core.models import Enclosure, FaceDims, Hole
from pedal_bench.io.ai_drill_extract import (
    _hole_is_plausible,
    _parse_response,
)


def _fake_enclosure() -> Enclosure:
    return Enclosure(
        key="125B",
        name="Hammond 125B",
        length_mm=121.5,
        width_mm=66.0,
        height_mm=39.3,
        wall_thickness_mm=2.5,
        faces={
            "A": FaceDims(width_mm=66.0, height_mm=121.5, label="Top"),
            "B": FaceDims(width_mm=66.0, height_mm=39.3, label="End B"),
            "C": FaceDims(width_mm=121.5, height_mm=39.3, label="Side C"),
            "D": FaceDims(width_mm=66.0, height_mm=39.3, label="End D"),
            "E": FaceDims(width_mm=121.5, height_mm=39.3, label="Side E"),
        },
        notes="",
    )


def _fake_response(tool_input: dict) -> SimpleNamespace:
    """Shape a fake anthropic response with one tool_use block."""
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text=""),  # sometimes present
            SimpleNamespace(type="tool_use", name="report_holes", input=tool_input),
        ]
    )


class TestParseResponse:
    def test_returns_none_if_no_tool_use(self) -> None:
        resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")])
        assert _parse_response(resp, _fake_enclosure()) is None

    def test_returns_none_when_confidence_none(self) -> None:
        resp = _fake_response({"confidence": "none", "holes": []})
        assert _parse_response(resp, _fake_enclosure()) is None

    def test_parses_valid_hole(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "holes": [
                    {
                        "side": "A",
                        "x_mm": 0.0,
                        "y_mm": 20.0,
                        "diameter_mm": 7.0,
                        "icon": "pot",
                        "label": "GAIN",
                    }
                ],
            }
        )
        holes = _parse_response(resp, _fake_enclosure())
        assert holes is not None
        assert len(holes) == 1
        h = holes[0]
        assert h.side == "A"
        assert h.x_mm == 0.0
        assert h.y_mm == 20.0
        assert h.diameter_mm == 7.0
        assert h.icon == "pot"
        assert h.label == "GAIN"
        assert h.powder_coat_margin is True

    def test_drops_invalid_side(self) -> None:
        resp = _fake_response(
            {
                "confidence": "medium",
                "holes": [
                    {"side": "Z", "x_mm": 0, "y_mm": 0, "diameter_mm": 7.0},
                    {"side": "A", "x_mm": 0, "y_mm": 0, "diameter_mm": 7.0},
                ],
            }
        )
        holes = _parse_response(resp, _fake_enclosure())
        assert holes is not None
        assert [h.side for h in holes] == ["A"]

    def test_drops_nonpositive_diameter(self) -> None:
        resp = _fake_response(
            {
                "confidence": "medium",
                "holes": [
                    {"side": "A", "x_mm": 0, "y_mm": 0, "diameter_mm": 0},
                    {"side": "A", "x_mm": 0, "y_mm": 0, "diameter_mm": -5},
                    {"side": "A", "x_mm": 0, "y_mm": 0, "diameter_mm": 7.0},
                ],
            }
        )
        holes = _parse_response(resp, _fake_enclosure())
        assert holes is not None and len(holes) == 1

    def test_drops_absurd_diameter(self) -> None:
        resp = _fake_response(
            {
                "confidence": "medium",
                "holes": [
                    {"side": "A", "x_mm": 0, "y_mm": 0, "diameter_mm": 999}
                ],
            }
        )
        holes = _parse_response(resp, _fake_enclosure())
        # All invalid → returns empty list, not None
        assert holes == []

    def test_ignores_invalid_icon(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "holes": [
                    {
                        "side": "A",
                        "x_mm": 0,
                        "y_mm": 0,
                        "diameter_mm": 7.0,
                        "icon": "nonsense",
                    }
                ],
            }
        )
        holes = _parse_response(resp, _fake_enclosure())
        assert holes is not None
        assert holes[0].icon is None

    def test_truncates_long_label(self) -> None:
        long_label = "x" * 200
        resp = _fake_response(
            {
                "confidence": "high",
                "holes": [
                    {
                        "side": "A",
                        "x_mm": 0,
                        "y_mm": 0,
                        "diameter_mm": 7.0,
                        "label": long_label,
                    }
                ],
            }
        )
        holes = _parse_response(resp, _fake_enclosure())
        assert holes is not None
        assert holes[0].label is not None
        assert len(holes[0].label) <= 40

    def test_survives_missing_fields_in_one_hole(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "holes": [
                    {"side": "A"},  # missing x/y/diameter → skipped
                    {"side": "A", "x_mm": 0, "y_mm": 0, "diameter_mm": 7.0},
                ],
            }
        )
        holes = _parse_response(resp, _fake_enclosure())
        assert holes is not None and len(holes) == 1


class TestHoleIsPlausible:
    def test_accepts_center_hole(self) -> None:
        enc = _fake_enclosure()
        h = Hole(side="A", x_mm=0, y_mm=0, diameter_mm=7.0)
        assert _hole_is_plausible(h, enc)

    def test_accepts_near_edge(self) -> None:
        enc = _fake_enclosure()
        # Face A is 66 × 121.5 → half = 33 × 60.75
        h = Hole(side="A", x_mm=32.0, y_mm=60.0, diameter_mm=7.0)
        assert _hole_is_plausible(h, enc)

    def test_rejects_beyond_edge(self) -> None:
        enc = _fake_enclosure()
        h = Hole(side="A", x_mm=100.0, y_mm=0.0, diameter_mm=7.0)
        assert not _hole_is_plausible(h, enc)

    def test_rejects_unknown_side(self) -> None:
        enc = _fake_enclosure()
        # Pretend side is valid at the type level but missing in catalog —
        # Hole's Side literal prevents that; use a real side with empty faces.
        empty_enc = Enclosure(
            key="X", name="nope", length_mm=10, width_mm=10, height_mm=10,
            wall_thickness_mm=1, faces={}, notes="",
        )
        h = Hole(side="A", x_mm=0, y_mm=0, diameter_mm=7.0)
        assert not _hole_is_plausible(h, empty_enc)
