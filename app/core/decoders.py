"""Pure-function parsers and formatters for resistor and capacitor values.

Used by the bench-mode side panel. No UI code here — the view is thin.

Value notation conventions (PedalPCB / European electronics style):
    Resistors:
        "100R" = 100 Ω
        "4K7"  = 4.7 kΩ   (letter acts as decimal point)
        "10K"  = 10 kΩ
        "1M"   = 1 MΩ
        "1M5"  = 1.5 MΩ
        Also accepts: "4.7K", "4.7k", "10000", "1000 Ω"
    Capacitors:
        "100p" = 100 pF
        "4n7"  = 4.7 nF    (letter acts as decimal point)
        "100n" = 100 nF
        "10u"  = 10 µF
        Also accepts: "4.7n", "4.7nF", "100nF", "10uF", "10µF"
"""

from __future__ import annotations

import re
from typing import Literal

# ---- Resistor text <-> ohms -----------------------------------------------

_R_UNITS: dict[str, float] = {"R": 1.0, "K": 1e3, "M": 1e6}
_R_EMBEDDED = re.compile(r"^(\d+)([RKM])(\d+)$")
_R_PLAIN = re.compile(r"^(\d+(?:\.\d+)?)([RKM]?)$")


def parse_resistor(text: str) -> float:
    """Parse resistor value text into ohms."""
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")
    t = text.strip().upper().replace("Ω", "").replace("OHM", "").replace("OHMS", "")
    t = t.replace(" ", "")
    if not t:
        raise ValueError("Empty resistor value")

    m = _R_EMBEDDED.match(t)
    if m:
        mantissa = float(f"{m.group(1)}.{m.group(3)}")
        return mantissa * _R_UNITS[m.group(2)]

    m = _R_PLAIN.match(t)
    if m:
        mantissa = float(m.group(1))
        unit = m.group(2) or "R"
        return mantissa * _R_UNITS[unit]

    raise ValueError(f"Cannot parse resistor value {text!r}")


def resistor_to_text(ohms: float) -> str:
    """Render ohms in PedalPCB-style notation ("4K7", "1M", "100R")."""
    if ohms <= 0:
        raise ValueError(f"ohms must be > 0, got {ohms}")
    if ohms < 1_000:
        return _format_unit(ohms, "R")
    if ohms < 1_000_000:
        return _format_unit(ohms / 1_000, "K")
    return _format_unit(ohms / 1_000_000, "M")


def resistor_display(ohms: float) -> str:
    """Human-friendly display with unit symbol ("4.7 kΩ", "1 MΩ")."""
    if ohms < 1_000:
        return f"{_g(ohms)} Ω"
    if ohms < 1_000_000:
        return f"{_g(ohms / 1_000)} kΩ"
    return f"{_g(ohms / 1_000_000)} MΩ"


# ---- Capacitor text <-> farads --------------------------------------------

_C_UNITS: dict[str, float] = {"P": 1e-12, "N": 1e-9, "U": 1e-6}
_C_EMBEDDED = re.compile(r"^(\d+)([PNU])(\d+)$")
_C_PLAIN = re.compile(r"^(\d+(?:\.\d+)?)([PNU])$")


def parse_capacitor(text: str) -> float:
    """Parse capacitor value text into farads."""
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")
    t = text.strip().upper().replace("µ", "U").replace("Μ", "U")  # mu/micro
    # Strip trailing "F" / "FD" but not the unit letter that precedes it.
    # e.g. "100NF" -> "100N", "10UF" -> "10U"
    t = t.replace(" ", "")
    if t.endswith("FD"):
        t = t[:-2]
    elif t.endswith("F"):
        t = t[:-1]
    if not t:
        raise ValueError("Empty capacitor value")

    m = _C_EMBEDDED.match(t)
    if m:
        mantissa = float(f"{m.group(1)}.{m.group(3)}")
        return mantissa * _C_UNITS[m.group(2)]

    m = _C_PLAIN.match(t)
    if m:
        return float(m.group(1)) * _C_UNITS[m.group(2)]

    raise ValueError(f"Cannot parse capacitor value {text!r}")


def capacitor_to_text(farads: float) -> str:
    """Render farads in PedalPCB-style notation ("100n", "4n7", "10u")."""
    if farads <= 0:
        raise ValueError(f"farads must be > 0, got {farads}")
    if farads >= 1e-6:
        return _format_unit(farads / 1e-6, "u")
    if farads >= 1e-9:
        return _format_unit(farads / 1e-9, "n")
    return _format_unit(farads / 1e-12, "p")


def capacitor_display(farads: float) -> str:
    """Human-friendly display with unit symbol ("100 nF", "10 µF")."""
    if farads >= 1e-6:
        return f"{_g(farads * 1e6)} µF"
    if farads >= 1e-9:
        return f"{_g(farads * 1e9)} nF"
    return f"{_g(farads * 1e12)} pF"


# ---- Resistor 4-band color codes ------------------------------------------

Color = Literal[
    "black", "brown", "red", "orange", "yellow",
    "green", "blue", "violet", "grey", "white",
    "gold", "silver",
]

_DIGIT_COLORS: tuple[str, ...] = (
    "black", "brown", "red", "orange", "yellow",
    "green", "blue", "violet", "grey", "white",
)
# Multiplier exponent (10**n) -> color band
_MULT_EXP_TO_COLOR: dict[int, str] = {
    -2: "silver",
    -1: "gold",
    0: "black",
    1: "brown",
    2: "red",
    3: "orange",
    4: "yellow",
    5: "green",
    6: "blue",
    7: "violet",
    8: "grey",
    9: "white",
}
_MULT_COLOR_TO_EXP: dict[str, int] = {c: e for e, c in _MULT_EXP_TO_COLOR.items()}
# Tolerance band -> percent
TOLERANCE_BY_COLOR: dict[str, float] = {
    "brown": 1.0,
    "red": 2.0,
    "gold": 5.0,
    "silver": 10.0,
}


def resistor_to_bands(ohms: float, tolerance_pct: float = 5.0) -> list[str]:
    """Return 4-band color sequence for the given resistance.

    Defaults to a gold (5%) tolerance band.
    """
    if ohms <= 0:
        raise ValueError(f"ohms must be > 0, got {ohms}")

    # Normalize to mantissa in [10, 100) and an integer multiplier exponent.
    exp = 0
    v = float(ohms)
    while v >= 100:
        v /= 10
        exp += 1
    while v < 10:
        v *= 10
        exp -= 1
    d1 = int(v // 10)
    d2 = int(round(v - d1 * 10))
    if d2 == 10:
        d2 = 0
        d1 += 1
        if d1 == 10:
            d1 = 1
            exp += 1

    if exp not in _MULT_EXP_TO_COLOR:
        raise ValueError(f"Resistance {ohms} out of 4-band range")

    tol_color = _tolerance_color(tolerance_pct)
    return [_DIGIT_COLORS[d1], _DIGIT_COLORS[d2], _MULT_EXP_TO_COLOR[exp], tol_color]


def bands_to_resistor(bands: list[str]) -> float:
    """Interpret a 3- or 4-band color list into ohms (tolerance band ignored)."""
    if len(bands) not in (3, 4):
        raise ValueError(f"Expected 3 or 4 bands, got {len(bands)}")
    try:
        d1 = _DIGIT_COLORS.index(bands[0])
        d2 = _DIGIT_COLORS.index(bands[1])
    except ValueError as exc:
        raise ValueError(f"Invalid digit band color: {exc}") from exc
    mult_color = bands[2]
    if mult_color not in _MULT_COLOR_TO_EXP:
        raise ValueError(f"Invalid multiplier band color: {mult_color!r}")
    exp = _MULT_COLOR_TO_EXP[mult_color]
    return (d1 * 10 + d2) * (10**exp)


def tolerance_from_band(band_color: str) -> float | None:
    return TOLERANCE_BY_COLOR.get(band_color)


# ---- Shared helpers -------------------------------------------------------

def _format_unit(val: float, unit: str) -> str:
    """Render val in the PedalPCB embedded-unit form.

    10    -> "10{unit}"
    4.7   -> "4{unit}7"
    1     -> "1{unit}"
    1.5   -> "1{unit}5"
    100   -> "100{unit}"
    """
    # Absorb IEEE-754 scaling noise. e.g. 100e-9 / 1e-9 = 99.99999... — without
    # this, a clean 100nF would render as "99n".
    val = round(val, 6)
    if val == int(val):
        return f"{int(val)}{unit}"
    whole = int(val)
    # Preserve up to 3 decimal digits — pedal values rarely need more.
    frac_str = f"{val - whole:.3f}"[2:].rstrip("0")
    if not frac_str:
        return f"{whole}{unit}"
    return f"{whole}{unit}{frac_str}"


def _g(x: float) -> str:
    """`%g` style formatter that trims trailing zeros without scientific form."""
    s = f"{x:.6g}"
    return s


def _tolerance_color(pct: float) -> str:
    for color, tol in TOLERANCE_BY_COLOR.items():
        if abs(pct - tol) < 0.01:
            return color
    return "gold"  # default 5%


__all__ = [
    "parse_resistor",
    "resistor_to_text",
    "resistor_display",
    "resistor_to_bands",
    "bands_to_resistor",
    "parse_capacitor",
    "capacitor_to_text",
    "capacitor_display",
    "TOLERANCE_BY_COLOR",
    "tolerance_from_band",
]
