"""Tests for the AI diagnosis response parser + input guards.

No live API calls — fakes anthropic responses.
"""

from __future__ import annotations

from types import SimpleNamespace

from pedal_bench.io.ai_diagnose import PinReading, _parse_response, diagnose


def _fake_response(tool_input: dict) -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text=""),
            SimpleNamespace(
                type="tool_use", name="report_diagnosis", input=tool_input
            ),
        ]
    )


class TestParseResponse:
    def test_full_diagnosis(self) -> None:
        resp = _fake_response(
            {
                "primary_suspect": "C5 coupling cap backwards",
                "reasoning": "Pin 1 reading 8.5V suggests DC is leaking through C5.",
                "next_probe": "Measure the DC across C5; if you see supply voltage across it, flip it.",
                "confidence": "medium",
                "alternative_suspects": ["IC1 pin 2 shorted to VCC"],
                "caveats": ["Schematic was low-res; reading may be off"],
            }
        )
        r = _parse_response(resp)
        assert r.primary_suspect == "C5 coupling cap backwards"
        assert r.confidence == "medium"
        assert r.next_probe.startswith("Measure")
        assert len(r.alternative_suspects) == 1
        assert len(r.caveats) == 1

    def test_minimum_required_fields(self) -> None:
        resp = _fake_response(
            {
                "primary_suspect": "X",
                "reasoning": "Y",
                "next_probe": "Z",
                "confidence": "high",
            }
        )
        r = _parse_response(resp)
        assert r.alternative_suspects == []
        assert r.caveats == []

    def test_invalid_confidence_defaults_low(self) -> None:
        resp = _fake_response(
            {
                "primary_suspect": "X",
                "reasoning": "Y",
                "next_probe": "Z",
                "confidence": "absolute",
            }
        )
        r = _parse_response(resp)
        assert r.confidence == "low"

    def test_returns_error_without_tool_use(self) -> None:
        resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")])
        r = _parse_response(resp)
        assert r.confidence == "error"

    def test_truncates_long_fields(self) -> None:
        resp = _fake_response(
            {
                "primary_suspect": "x" * 2000,
                "reasoning": "y" * 10000,
                "next_probe": "z" * 5000,
                "confidence": "low",
            }
        )
        r = _parse_response(resp)
        assert len(r.primary_suspect) <= 500
        assert len(r.reasoning) <= 3000
        assert len(r.next_probe) <= 800

    def test_caps_array_lengths(self) -> None:
        resp = _fake_response(
            {
                "primary_suspect": "X",
                "reasoning": "Y",
                "next_probe": "Z",
                "confidence": "low",
                "alternative_suspects": [f"alt {i}" for i in range(100)],
                "caveats": [f"caveat {i}" for i in range(100)],
            }
        )
        r = _parse_response(resp)
        assert len(r.alternative_suspects) <= 6
        assert len(r.caveats) <= 6


class TestDiagnoseGuards:
    def test_rejects_empty_symptom(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        r = diagnose(
            symptom="",
            supply_vcc_v=9.0,
            supply_vref_v=4.5,
            selected_ic=None,
            readings=[],
        )
        assert r.confidence == "error"
        assert "pedal" in r.next_probe.lower()

    def test_errors_without_key(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = diagnose(
            symptom="no sound",
            supply_vcc_v=9.0,
            supply_vref_v=4.5,
            selected_ic=None,
            readings=[],
        )
        assert r.confidence == "error"
        assert "ANTHROPIC_API_KEY" in r.next_probe


class TestPinReadingFrozen:
    def test_frozen(self) -> None:
        r = PinReading(pin=1, name="OUT A", expected_v=4.5, tolerance_v=0.5, measured_v=4.4)
        try:
            r.pin = 2  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("PinReading should be frozen")
