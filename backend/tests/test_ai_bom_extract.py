"""Tests for ai_bom_extract response parsing.

No network — fakes anthropic responses to exercise _parse_response.
"""

from __future__ import annotations

from types import SimpleNamespace

from pedal_bench.io.ai_bom_extract import _parse_response


def _fake_response(tool_input: dict) -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text=""),
            SimpleNamespace(
                type="tool_use", name="report_bom", input=tool_input
            ),
        ]
    )


class TestParseResponse:
    def test_returns_none_when_confidence_none(self) -> None:
        resp = _fake_response({"confidence": "none", "bom": []})
        assert _parse_response(resp) is None

    def test_returns_none_without_tool_use(self) -> None:
        resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")])
        assert _parse_response(resp) is None

    def test_parses_basic_rows(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "bom": [
                    {"location": "R1", "value": "1M", "type": "Resistor, 1/4W"},
                    {"location": "R2", "value": "10K", "type": "Resistor, 1/4W"},
                    {"location": "C1", "value": "100n", "type": "Capacitor"},
                ],
            }
        )
        items = _parse_response(resp)
        assert items is not None
        assert len(items) == 3
        # Output sorted by family then numeric: C1, R1, R2
        assert [i.location for i in items] == ["C1", "R1", "R2"]
        r1 = next(i for i in items if i.location == "R1")
        assert r1.value == "1M"
        assert r1.type == "Resistor, 1/4W"

    def test_drops_garbage_locations(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "bom": [
                    {"location": "RESISTORS", "value": "1/4W", "type": ""},
                    {"location": "1/4W", "value": "100", "type": ""},
                    {"location": "R1", "value": "1M", "type": "Resistor"},
                ],
            }
        )
        items = _parse_response(resp)
        assert items is not None
        assert len(items) == 1
        assert items[0].location == "R1"

    def test_dedups_locations(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "bom": [
                    {"location": "R1", "value": "1M", "type": "Resistor"},
                    {"location": "r1", "value": "1M", "type": "Resistor"},  # case-insensitive
                ],
            }
        )
        items = _parse_response(resp)
        assert items is not None
        assert len(items) == 1

    def test_polarity_flag_set_for_diodes(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "bom": [
                    {"location": "D1", "value": "1N4148", "type": "Diode"},
                    {"location": "Q1", "value": "2N5089", "type": "NPN Transistor"},
                    {"location": "C1", "value": "10u", "type": "Electrolytic capacitor"},
                    {"location": "R1", "value": "1K", "type": "Resistor, 1/4W"},
                ],
            }
        )
        items = _parse_response(resp)
        assert items is not None
        flags = {i.location: i.polarity_sensitive for i in items}
        assert flags["D1"] is True
        assert flags["Q1"] is True
        assert flags["C1"] is True
        assert flags["R1"] is False

    def test_polarity_flag_for_ic_type_string(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "bom": [
                    {"location": "IC1", "value": "TL072", "type": "Integrated Circuit"},
                    {"location": "IC2", "value": "LM308", "type": "IC"},
                ],
            }
        )
        items = _parse_response(resp)
        assert items is not None
        assert all(i.polarity_sensitive for i in items)

    def test_skips_rows_without_location(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "bom": [
                    {"location": "", "value": "1M", "type": "Resistor"},
                    {"location": "R1", "value": "", "type": "Resistor"},  # also drop
                    {"location": "R2", "value": "1K", "type": "Resistor"},
                ],
            }
        )
        items = _parse_response(resp)
        assert items is not None
        assert len(items) == 1
        assert items[0].location == "R2"

    def test_sorted_within_designator_family(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "bom": [
                    {"location": "R10", "value": "10K", "type": "Resistor"},
                    {"location": "R2", "value": "1K", "type": "Resistor"},
                    {"location": "C1", "value": "100n", "type": "Capacitor"},
                    {"location": "R1", "value": "1M", "type": "Resistor"},
                ],
            }
        )
        items = _parse_response(resp)
        assert items is not None
        # Sort key: family then numeric. Cs come before Rs alphabetically.
        assert [i.location for i in items] == ["C1", "R1", "R2", "R10"]

    def test_returns_none_on_empty_after_filtering(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "bom": [{"location": "RESISTORS", "value": "1M", "type": ""}],
            }
        )
        assert _parse_response(resp) is None

    def test_truncates_long_fields(self) -> None:
        resp = _fake_response(
            {
                "confidence": "high",
                "bom": [
                    {
                        "location": "R1",
                        "value": "x" * 200,
                        "type": "y" * 500,
                        "notes": "z" * 500,
                    }
                ],
            }
        )
        items = _parse_response(resp)
        assert items is not None
        assert len(items[0].value) <= 40
        assert len(items[0].type) <= 80
        assert len(items[0].notes) <= 120
