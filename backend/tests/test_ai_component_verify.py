"""Tests for ai_component_verify response parsing.

Doesn't hit the API — fakes the anthropic response shape.
"""

from __future__ import annotations

from types import SimpleNamespace

from pedal_bench.io.ai_component_verify import (
    VerifyResult,
    _parse_response,
    verify_component_photo,
)


def _fake_response(tool_input: dict) -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text=""),
            SimpleNamespace(type="tool_use", name="report_verdict", input=tool_input),
        ]
    )


class TestParseResponse:
    def test_parses_match(self) -> None:
        resp = _fake_response(
            {
                "verdict": "match",
                "explanation": "Color bands read red-violet-red-gold = 2.7 kΩ ±5%, matches the expected 2K7 resistor.",
            }
        )
        r = _parse_response(resp)
        assert r.verdict == "match"
        assert "2.7 k" in r.explanation
        assert r.guess_value is None

    def test_parses_mismatch_with_guess(self) -> None:
        resp = _fake_response(
            {
                "verdict": "mismatch",
                "explanation": "Bands read brown-black-red-gold = 1 kΩ. Expected 4.7 kΩ.",
                "guess_value": "1K",
                "guess_type": "1/4W carbon film resistor",
            }
        )
        r = _parse_response(resp)
        assert r.verdict == "mismatch"
        assert r.guess_value == "1K"
        assert r.guess_type == "1/4W carbon film resistor"

    def test_defaults_unknown_verdict(self) -> None:
        resp = _fake_response(
            {"verdict": "questionable", "explanation": "shrug"}
        )
        r = _parse_response(resp)
        assert r.verdict == "unsure"

    def test_defaults_missing_explanation(self) -> None:
        resp = _fake_response({"verdict": "match"})
        r = _parse_response(resp)
        assert r.verdict == "match"
        assert r.explanation  # non-empty

    def test_returns_error_without_tool_use(self) -> None:
        resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")])
        r = _parse_response(resp)
        assert r.verdict == "error"

    def test_truncates_long_explanation(self) -> None:
        long_text = "x" * 5000
        resp = _fake_response({"verdict": "match", "explanation": long_text})
        r = _parse_response(resp)
        assert len(r.explanation) <= 600


class TestVerifyComponentPhotoGuards:
    def test_rejects_empty_bytes(self) -> None:
        r = verify_component_photo(
            b"", "image/jpeg", "4K7", "resistor",
        )
        assert r.verdict == "error"
        assert "No image" in r.explanation

    def test_rejects_bad_media_type(self, monkeypatch) -> None:
        # Pretend we have a key so we bypass the no-key guard and exercise the media-type check.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        r = verify_component_photo(
            b"\x89PNG", "image/bmp", "4K7", "resistor",
        )
        assert r.verdict == "error"
        assert "Unsupported" in r.explanation


class TestVerifyResult:
    def test_frozen(self) -> None:
        r = VerifyResult("match", "ok")
        try:
            r.verdict = "mismatch"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("VerifyResult should be frozen")
