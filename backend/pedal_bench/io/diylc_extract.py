"""DIYLC (.diy) file → BOM extractor.

DIYLC files are XStream-serialized XML. Components live under <components>
with type encoded in the element tag (e.g. `diylc.passive.Resistor`,
`diylc.semiconductors.DIL__IC`). We classify by tag, extract reference
designator from <name>, and pull the value from a typed sub-element.

The parser handles both file generations:
  - v4 / current: root <project>, namespace `diylc.*`
  - v3 / legacy:  root <org.diylc.core.Project>, namespace `org.diylc.components.*`

Non-BOM elements (boards, traces, hookup wire, labels, ground symbols) are
filtered. Output is a list of BOMItem ready to drop into a Project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from pedal_bench.core.models import BOMItem, is_polarity_sensitive


@dataclass
class DIYLCExtractResult:
    title: str | None
    bom: list[BOMItem]
    skipped_count: int     # decorative/connectivity components dropped
    warnings: list[str]


# Tag-substring → pedal-bench kind. Order matters: earlier rules win for
# tags that match multiple substrings (e.g. "ElectrolyticCapacitor" must
# hit "Electrolytic" before "Capacitor").
_KIND_RULES: list[tuple[str, str]] = [
    ("Electrolytic",                "electrolytic"),
    ("Tantalum",                    "electrolytic"),
    ("CeramicDiskCapacitor",        "film-cap"),
    ("FilmCapacitor",               "film-cap"),
    ("CapacitorSymbol",             "film-cap"),
    ("Capacitor",                   "film-cap"),
    ("Resistor",                    "resistor"),
    ("Diode",                       "diode"),
    ("LED",                         "diode"),  # PedalPCB convention
    ("TransistorTO",                "transistor"),
    ("Transistor",                  "transistor"),
    ("JFET",                        "transistor"),
    ("BJT",                         "transistor"),
    ("MOSFET",                      "transistor"),
    ("DIL__IC",                     "ic"),
    ("SIL__IC",                     "ic"),
    ("ICSymbol",                    "ic"),
    ("Potentiometer",               "pot"),
    ("Trimmer",                     "pot"),
    ("Inductor",                    "inductor"),
    ("Toroid",                      "inductor"),
    ("Switch",                      "switch"),
    ("Jack",                        "switch"),  # I/O hardware grouped here
    ("DCJack",                      "switch"),
]

# Tags ending in any of these are decoration / wiring, not BOM rows.
_NON_BOM_PREFIXES = (
    "diylc.boards.",
    "diylc.connectivity.",
    "diylc.misc.",
    "org.diylc.components.connectivity.",
    "org.diylc.components.misc.",
    "org.diylc.components.boards.",
)

# Human-readable type strings for each kind, used when the .diy doesn't
# tell us the value (transistors/ICs often don't).
_KIND_TYPE_LABELS = {
    "resistor":     "Resistor",
    "film-cap":     "Film/ceramic capacitor",
    "electrolytic": "Electrolytic capacitor",
    "diode":        "Diode",
    "transistor":   "Transistor",
    "ic":           "IC / op-amp",
    "pot":          "Potentiometer",
    "inductor":     "Inductor",
    "switch":       "Switch / jack",
}


def _classify_tag(tag: str) -> str | None:
    """Return pedal-bench kind for a DIYLC component tag, or None to skip."""
    if any(tag.startswith(p) for p in _NON_BOM_PREFIXES):
        return None
    for needle, kind in _KIND_RULES:
        if needle in tag:
            return kind
    return None


def _strip_underscore_enum(s: str) -> str:
    """DIYLC writes enum values as `_63V`, `_8`, `_LOG`. Strip leading `_`."""
    return s[1:] if s.startswith("_") else s


def _extract_value(el: ET.Element, kind: str) -> str:
    """Pull a human-readable value string from a component element.

    For passives DIYLC stores `<value value="68.0" unit="K"/>` or
    `<resistance value="10.0" unit="K"/>`. For semis the value field is
    often empty — return empty string and let the user fill it in.
    """
    # Some components use <value> as a typed sub-element; others as scalar text.
    val_el = el.find("value")
    if val_el is not None:
        attr_val = val_el.get("value")
        attr_unit = val_el.get("unit")
        if attr_val is not None:
            # "68.0" + "K" → "68K"; trim ".0" tail for cosmetic cleanliness.
            num = attr_val.rstrip("0").rstrip(".") if "." in attr_val else attr_val
            unit = attr_unit or ""
            return f"{num}{unit}".strip()
        # Pure-text value (rare): return as-is.
        if val_el.text and val_el.text.strip():
            return val_el.text.strip()

    # Pots use <resistance>.
    res_el = el.find("resistance")
    if res_el is not None and res_el.get("value") is not None:
        num = (res_el.get("value") or "").rstrip("0").rstrip(".")
        unit = res_el.get("unit") or ""
        out = f"{num}{unit}".strip()
        # Append taper if present (LOG/LIN/REVLOG).
        taper = el.findtext("taper")
        if taper:
            out = f"{_strip_underscore_enum(taper)} {out}".strip()
        return out

    if kind == "ic":
        # Try pinCount as a hint — "8-pin DIP IC".
        pc = el.findtext("pinCount")
        if pc:
            return f"{_strip_underscore_enum(pc)}-pin"

    return ""


def _local_tag(elem: ET.Element) -> str:
    """Get tag without leading namespace decoration. ElementTree gives us
    the literal tag string for non-namespaced XML, which is what XStream
    produces, so this is mostly a passthrough — but defensive for future-
    proofing if anyone adds namespaces.
    """
    t = elem.tag
    return t.rsplit("}", 1)[-1] if "}" in t else t


_LOC_PATTERN = re.compile(r"^[A-Za-z]+\d*$")


def parse_diylc(content: bytes | str) -> DIYLCExtractResult:
    """Parse a .diy file's bytes into a DIYLCExtractResult.

    Raises ValueError if the file isn't valid XML or doesn't look like a
    DIYLC project.
    """
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    else:
        text = content

    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"Not valid XML: {e}") from e

    root_tag = _local_tag(root)
    if root_tag not in ("project", "org.diylc.core.Project"):
        raise ValueError(
            f"Unexpected root element <{root_tag}>; expected <project> "
            f"(DIYLC v4) or <org.diylc.core.Project> (legacy)."
        )

    title = root.findtext("title") or None

    components_el = root.find("components")
    if components_el is None:
        return DIYLCExtractResult(
            title=title,
            bom=[],
            skipped_count=0,
            warnings=["No <components> element in file."],
        )

    bom: list[BOMItem] = []
    skipped = 0
    warnings: list[str] = []
    seen_locations: set[str] = set()

    for child in components_el:
        tag = _local_tag(child)
        kind = _classify_tag(tag)
        if kind is None:
            skipped += 1
            continue

        loc = (child.findtext("name") or "").strip()
        # DIYLC sometimes has duplicate names (multiple symbol drops). Keep
        # the first; merge quantities for subsequent.
        value = _extract_value(child, kind)

        if not loc:
            # Without a refdes we can't dedupe sensibly. Skip and warn once.
            if "missing-refdes" not in warnings:
                warnings.append("missing-refdes")
            skipped += 1
            continue

        if loc in seen_locations:
            # Bump quantity on the existing row.
            for item in bom:
                if item.location == loc:
                    item.quantity += 1
                    break
            continue

        seen_locations.add(loc)
        type_str = _KIND_TYPE_LABELS.get(kind, "")

        bom.append(
            BOMItem(
                location=loc,
                value=value,
                type=type_str,
                quantity=1,
                polarity_sensitive=is_polarity_sensitive(type_str),
                orientation_hint=None,
            )
        )

    if "missing-refdes" in warnings:
        warnings = [w for w in warnings if w != "missing-refdes"]
        warnings.append("Some components had no reference designator and were skipped.")

    return DIYLCExtractResult(
        title=title,
        bom=_sorted_by_refdes(bom),
        skipped_count=skipped,
        warnings=warnings,
    )


def _refdes_sort_key(loc: str) -> tuple[str, int]:
    m = re.match(r"^([A-Za-z]+)(\d+)?$", loc)
    if not m:
        return (loc, 0)
    return (m.group(1).upper(), int(m.group(2) or 0))


def _sorted_by_refdes(bom: list[BOMItem]) -> list[BOMItem]:
    return sorted(bom, key=lambda b: _refdes_sort_key(b.location))


__all__ = ["parse_diylc", "DIYLCExtractResult"]
