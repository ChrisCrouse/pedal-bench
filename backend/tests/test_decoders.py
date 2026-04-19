from __future__ import annotations

import math

import pytest

from pedal_bench.core.decoders import (
    bands_to_resistor,
    capacitor_display,
    capacitor_to_text,
    parse_capacitor,
    parse_resistor,
    resistor_display,
    resistor_to_bands,
    resistor_to_text,
)


# ---- resistor parsing ----------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("100R", 100.0),
        ("100", 100.0),
        ("4K7", 4_700.0),
        ("4.7K", 4_700.0),
        ("4.7k", 4_700.0),
        ("10K", 10_000.0),
        ("33K", 33_000.0),
        ("150K", 150_000.0),
        ("470K", 470_000.0),
        ("1M", 1_000_000.0),
        ("1M5", 1_500_000.0),
        ("2.2M", 2_200_000.0),
        ("6K2", 6_200.0),
        (" 4K7 ", 4_700.0),
        ("100 Ω", 100.0),
        ("100 ohm", 100.0),
    ],
)
def test_parse_resistor(text: str, expected: float) -> None:
    assert parse_resistor(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "abc", "K", "4X7", "1.2.3K"])
def test_parse_resistor_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_resistor(text)


@pytest.mark.parametrize(
    "ohms,expected",
    [
        (100, "100R"),
        (470, "470R"),
        (4_700, "4K7"),
        (10_000, "10K"),
        (33_000, "33K"),
        (150_000, "150K"),
        (470_000, "470K"),
        (1_000_000, "1M"),
        (1_500_000, "1M5"),
        (2_200_000, "2M2"),
    ],
)
def test_resistor_to_text(ohms: float, expected: str) -> None:
    assert resistor_to_text(ohms) == expected


def test_resistor_roundtrip_on_sherwood_values() -> None:
    # All resistor values on the Sherwood Overdrive BOM.
    values = [
        "1M", "1K", "470K", "4K7", "6K2", "150K", "33K", "100R", "47K",
    ]
    for text in values:
        assert resistor_to_text(parse_resistor(text)) == text


def test_resistor_display() -> None:
    assert resistor_display(4700) == "4.7 kΩ"
    assert resistor_display(100) == "100 Ω"
    assert resistor_display(1_000_000) == "1 MΩ"
    assert resistor_display(150_000) == "150 kΩ"


# ---- resistor color bands ------------------------------------------------

@pytest.mark.parametrize(
    "ohms,bands",
    [
        (4_700, ["yellow", "violet", "red", "gold"]),
        (10_000, ["brown", "black", "orange", "gold"]),
        (1_000_000, ["brown", "black", "green", "gold"]),
        (100, ["brown", "black", "brown", "gold"]),
        (470_000, ["yellow", "violet", "yellow", "gold"]),
        (150_000, ["brown", "green", "yellow", "gold"]),
        (6_200, ["blue", "red", "red", "gold"]),
    ],
)
def test_resistor_to_bands(ohms: int, bands: list[str]) -> None:
    assert resistor_to_bands(ohms) == bands


@pytest.mark.parametrize(
    "bands,ohms",
    [
        (["yellow", "violet", "red", "gold"], 4_700),
        (["brown", "black", "orange"], 10_000),
        (["brown", "black", "green", "gold"], 1_000_000),
        (["blue", "grey", "red", "gold"], 6_800),
    ],
)
def test_bands_to_resistor(bands: list[str], ohms: int) -> None:
    assert bands_to_resistor(bands) == ohms


def test_resistor_band_roundtrip() -> None:
    for val in [100, 220, 470, 1_000, 4_700, 10_000, 33_000, 150_000, 1_000_000]:
        bands = resistor_to_bands(val)
        assert bands_to_resistor(bands) == val


# ---- capacitor parsing ---------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("100p", 100e-12),
        ("100P", 100e-12),
        ("100pF", 100e-12),
        ("4n7", 4.7e-9),
        ("100n", 100e-9),
        ("100nF", 100e-9),
        ("220n", 220e-9),
        ("4n7", 4.7e-9),
        ("1u", 1e-6),
        ("10u", 10e-6),
        ("10uF", 10e-6),
        ("10µF", 10e-6),
        ("47n", 47e-9),
        ("1n5", 1.5e-9),
    ],
)
def test_parse_capacitor(text: str, expected: float) -> None:
    assert parse_capacitor(text) == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize("text", ["", "abc", "100", "100xF", "u", "1.2.3n"])
def test_parse_capacitor_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_capacitor(text)


@pytest.mark.parametrize(
    "farads,expected",
    [
        (100e-12, "100p"),
        (4.7e-9, "4n7"),
        (100e-9, "100n"),
        (220e-9, "220n"),
        (1e-6, "1u"),
        (10e-6, "10u"),
    ],
)
def test_capacitor_to_text(farads: float, expected: str) -> None:
    assert capacitor_to_text(farads) == expected


def test_capacitor_roundtrip_on_sherwood_values() -> None:
    values = ["100p", "100n", "220n", "10u", "1u", "4n7", "47n"]
    for text in values:
        assert capacitor_to_text(parse_capacitor(text)) == text


def test_capacitor_display() -> None:
    assert capacitor_display(100e-9) == "100 nF"
    assert capacitor_display(4.7e-9) == "4.7 nF"
    assert capacitor_display(10e-6) == "10 µF"
    assert capacitor_display(100e-12) == "100 pF"


# ---- cross-check: a few inputs don't throw unexpected ---------------------

def test_very_small_and_very_large() -> None:
    # Edge cases we want to at least not crash on.
    assert parse_capacitor("1p") == pytest.approx(1e-12)
    assert math.isfinite(parse_resistor("10M"))
