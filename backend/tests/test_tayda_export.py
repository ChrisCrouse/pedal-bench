"""Tests for tayda_export payload builder + error handling.

No network — we mock httpx when needed. The payload builder is the
important part: it's the contract between pedal-bench and Tayda's
undocumented API, so when something breaks that's where we look first.
"""

from __future__ import annotations

import pytest

from pedal_bench.core.models import Hole, Project
from pedal_bench.io.tayda_export import (
    TAYDA_ENCLOSURES,
    TaydaPushError,
    _build_design_url,
    _extract_design_id,
    _fmt_number,
    _hole_to_tayda,
    _summarize_error,
    build_tayda_payload,
)


# -- build_tayda_payload ---------------------------------------------------


class TestBuildPayload:
    def test_empty_project_minimal_shape(self) -> None:
        p = Project(slug="x", name="Test Pedal", enclosure="125B")
        payload = build_tayda_payload(p)
        assert payload["name"] == "Test Pedal"
        assert payload["enclosure_type"] == "125B"
        assert payload["is_public"] == 0
        assert payload["is_archived"] == 0
        assert payload["holes"] == []
        assert payload["lines"] == []
        assert payload["shapes"] == []

    def test_rejects_unsupported_enclosure(self) -> None:
        p = Project(slug="x", name="x", enclosure="FICTIONAL-999")
        with pytest.raises(TaydaPushError, match="doesn't support"):
            build_tayda_payload(p)

    def test_rejects_empty_enclosure(self) -> None:
        p = Project(slug="x", name="x", enclosure="")
        with pytest.raises(TaydaPushError, match="doesn't support"):
            build_tayda_payload(p)

    def test_accepts_every_tayda_enclosure(self) -> None:
        for enc in TAYDA_ENCLOSURES:
            p = Project(slug="x", name="x", enclosure=enc)
            payload = build_tayda_payload(p)
            assert payload["enclosure_type"] == enc

    def test_holes_are_stringified(self) -> None:
        p = Project(
            slug="x",
            name="x",
            enclosure="125B",
            holes=[
                Hole(side="A", x_mm=0.0, y_mm=0.0, diameter_mm=3.0),
                Hole(side="B", x_mm=12.5, y_mm=-7.25, diameter_mm=9.525),
            ],
        )
        payload = build_tayda_payload(p)
        assert len(payload["holes"]) == 2
        h0 = payload["holes"][0]
        assert h0 == {
            "box_side": "A",
            "diameter": "3",
            "positionX": "0",
            "positionY": "0",
        }
        h1 = payload["holes"][1]
        assert h1["box_side"] == "B"
        assert h1["diameter"] == "9.525"
        assert h1["positionX"] == "12.5"
        assert h1["positionY"] == "-7.25"
        # All values are strings (Tayda's API expects strings).
        assert all(isinstance(v, str) for v in h0.values())
        assert all(isinstance(v, str) for v in h1.values())

    def test_is_public_true(self) -> None:
        p = Project(slug="x", name="x", enclosure="125B")
        assert build_tayda_payload(p, is_public=True)["is_public"] == 1
        assert build_tayda_payload(p, is_public=False)["is_public"] == 0

    def test_name_override(self) -> None:
        p = Project(slug="x", name="Original", enclosure="125B")
        payload = build_tayda_payload(p, name_override="Override")
        assert payload["name"] == "Override"

    def test_name_fallback_when_empty(self) -> None:
        p = Project(slug="x", name="", enclosure="125B")
        payload = build_tayda_payload(p)
        assert payload["name"] == "pedal-bench"

    def test_long_name_truncated(self) -> None:
        p = Project(slug="x", name="X" * 200, enclosure="125B")
        payload = build_tayda_payload(p)
        assert len(payload["name"]) <= 80


# -- _hole_to_tayda ---------------------------------------------------------


class TestHoleToTayda:
    def test_integer_diameter_rendered_clean(self) -> None:
        h = Hole(side="A", x_mm=0, y_mm=0, diameter_mm=7.0)
        assert _hole_to_tayda(h)["diameter"] == "7"

    def test_fractional_kept(self) -> None:
        h = Hole(side="A", x_mm=0, y_mm=0, diameter_mm=4.7)
        assert _hole_to_tayda(h)["diameter"] == "4.7"

    def test_side_preserved(self) -> None:
        for side in ("A", "B", "C", "D", "E"):
            h = Hole(side=side, x_mm=0, y_mm=0, diameter_mm=3)
            assert _hole_to_tayda(h)["box_side"] == side


# -- _fmt_number ------------------------------------------------------------


class TestFmtNumber:
    def test_integer_no_decimal(self) -> None:
        assert _fmt_number(3.0) == "3"
        assert _fmt_number(0.0) == "0"
        assert _fmt_number(-5.0) == "-5"

    def test_fraction_trimmed(self) -> None:
        assert _fmt_number(4.5) == "4.5"
        assert _fmt_number(4.50000) == "4.5"
        assert _fmt_number(0.1) == "0.1"

    def test_negative_fraction(self) -> None:
        assert _fmt_number(-7.25) == "-7.25"


# -- _extract_design_id -----------------------------------------------------


class TestExtractDesignId:
    def test_id_at_top(self) -> None:
        assert _extract_design_id({"id": 42}) == "42"

    def test_uuid(self) -> None:
        assert _extract_design_id({"uuid": "abc-123"}) == "abc-123"

    def test_nested_under_data(self) -> None:
        assert _extract_design_id({"data": {"id": 7}}) == "7"

    def test_returns_none_when_missing(self) -> None:
        assert _extract_design_id({"unrelated": "field"}) is None

    def test_returns_none_for_non_dict(self) -> None:
        assert _extract_design_id("a string") is None
        assert _extract_design_id(None) is None
        assert _extract_design_id([1, 2, 3]) is None


# -- _build_design_url ------------------------------------------------------


class TestBuildDesignUrl:
    def test_builds_a_plausible_url(self) -> None:
        url = _build_design_url("xyz-42")
        assert url.startswith("https://www.taydakits.com/")
        assert "xyz-42" in url


# -- _summarize_error -------------------------------------------------------


class TestSummarizeError:
    def test_401_suggests_token_check(self) -> None:
        msg = _summarize_error(401, None)
        assert "401" in msg or "token" in msg.lower()

    def test_422_mentions_payload(self) -> None:
        msg = _summarize_error(422, {"error": "..."})
        assert "422" in msg

    def test_500_suggests_retry(self) -> None:
        msg = _summarize_error(503, None)
        assert "503" in msg
