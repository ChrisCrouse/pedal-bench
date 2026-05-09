"""Static price oracle — fallback unit costs for parts the user hasn't
priced themselves. Sits between InventoryItem.unit_cost_usd and "no price
known" in the cost-to-finish lookup chain."""

from __future__ import annotations

from pathlib import Path

import pytest

from pedal_bench.core import price_oracle


def test_lookup_prefers_exact_value_over_default() -> None:
    # 10k is in the values table; default_prices.json should have a more
    # specific entry than the kind default.
    p = price_oracle.lookup("resistor", "10k")
    assert p is not None
    assert p > 0


def test_lookup_falls_back_to_kind_default() -> None:
    # An obscure resistor value not in the seed table should still get the
    # resistor kind default, not None.
    p = price_oracle.lookup("resistor", "9.42k")
    assert p is not None
    assert p > 0


def test_lookup_returns_none_when_kind_default_is_null() -> None:
    # ICs intentionally have default=null because prices vary 10x; an
    # unknown IC should return None rather than a misleading guess.
    assert price_oracle.lookup("ic", "MADE_UP_PART_12345") is None


def test_lookup_returns_none_for_unknown_kind() -> None:
    assert price_oracle.lookup("nonsense-kind", "anything") is None


def test_lookup_returns_none_for_empty_inputs() -> None:
    assert price_oracle.lookup("", "10k") is None
    assert price_oracle.lookup("resistor", "") is None


@pytest.mark.parametrize(
    "kind, value",
    [
        ("resistor", "10k"),
        ("resistor", "1M"),
        ("resistor", "4.7k"),
        ("film-cap", "100n"),
        ("electrolytic", "10u"),
        ("diode", "1N4148"),
        ("ic", "TL072"),
        ("transistor", "2N3904"),
    ],
)
def test_lookup_covers_common_pedal_parts(kind: str, value: str) -> None:
    """The seed table must cover the parts that show up in nearly every
    pedal build, otherwise cost-to-finish numbers will systematically
    undershoot."""
    assert price_oracle.lookup(kind, value) is not None


def test_reload_drops_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests that rewrite the prices file mid-run can call reload() and see
    fresh data on the next lookup."""
    fake_path = tmp_path / "prices.json"
    fake_path.write_text(
        '{"resistor": {"default": 0.42, "values": {"10k": 0.13}}}'
    )
    monkeypatch.setattr(price_oracle, "_PATH", fake_path)
    price_oracle.reload()
    try:
        assert price_oracle.lookup("resistor", "10k") == 0.13
        assert price_oracle.lookup("resistor", "9999") == 0.42
    finally:
        # Restore real cache for downstream tests.
        price_oracle.reload()
