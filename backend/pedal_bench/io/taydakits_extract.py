"""Build-package extractor for Taydakits HTML instruction pages.

Mirrors the role of `pedalpcb_extract.py` but operates on the HTML pages
served by taydakits.com instead of a PDF. Returns the same
`ExtractedBuildPackage` envelope so the API/UI layer can stay unchanged.

What we extract:
  - title (from the overview page <h1 class="title">)
  - enclosure (from the drilling page prose; "1590B enclosure PCB")
  - BOM (from the designators-and-components step)
  - schematic / pcb-layout / wiring image URLs (cached as project assets)

What we *don't* extract:
  - drill hole coordinates — Taydakits embeds these as a rendered table
    *inside* the enclosure-template PNG, not as machine-readable HTML.
    Users paste/import them via the existing Tayda Box Tool flow on the
    Drill tab. A clear warning is appended to surface that hand-off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

from pedal_bench.core.models import BOMItem, is_polarity_sensitive
from pedal_bench.io.pedalpcb_extract import ExtractedBuildPackage
from pedal_bench.io.tayda_drill_api import TaydaDrillAPIError, fetch_holes
from pedal_bench.io.taydakits_fetch import (
    FetchedTaydakitsBuild,
    TaydakitsFetchError,
    fetch_build,
)


@dataclass
class TaydakitsBuildPackage(ExtractedBuildPackage):
    """Same envelope as PedalPCB, plus the source URLs we need at create-time
    to fetch and cache schematic / wiring / pcb-layout images.

    `drill_tool_url` is inherited from ExtractedBuildPackage."""

    # First image discovered on the components step — used as the PCB layout.
    pcb_layout_image_url: str | None = None
    # First image discovered on the wiring step — used as the wiring diagram.
    wiring_image_url: str | None = None
    # First image discovered on the components step that looks schematic-shaped
    # ("circuit" in the filename). Optional — falls back to None if absent.
    schematic_image_url: str | None = None
    # The build-source URL the user pasted (canonicalized).
    source_url: str | None = None
    # Page URLs by step keyword — handy for diagnostics.
    step_urls: dict[str, str] = field(default_factory=dict)


_DRILL_TOOL_RE = re.compile(
    r'href="(https?://drill\.taydakits\.com/[^"]+public_key=[^"]+)"',
    re.IGNORECASE,
)
_ENCLOSURE_RE = re.compile(
    r"\b(125\s?B|1590[A-Z0-9]{1,3}|1590N1)\s+enclosure",
    re.IGNORECASE,
)
ENCLOSURE_ALIASES: dict[str, str] = {
    "125B": "125B",
    "1590A": "1590A",
    "1590B": "1590B",
    "1590BB": "1590BB",
    "1590BB2": "1590DD",
    "1590DD": "1590DD",
    "1590XX": "1590XX",
    "1590N1": "125B",
}

# Section header → BOMItem.type string. Mirrors `pedalpcb_pdf._SECTION_TYPES`
# so Taydakits BOMs render identically in the UI.
_SECTION_TYPES: dict[str, str] = {
    "PCB": "PCB",
    "CAPACITORS": "Capacitor",
    "RESISTORS": "Resistor, 1/4W",
    "TRANSISTORS": "Transistor",
    "DIODES": "Diode",
    "INTEGRATED CIRCUITS": "Integrated circuit",
    "ICS": "Integrated circuit",
    "POTENTIOMETERS": "Potentiometer",
    "TRIM POTS": "Trim pot",
    "TRIMPOTS": "Trim pot",
    "SWITCHES": "Switch",
    "INDUCTORS": "Inductor",
    "RELAYS": "Relay",
    "SOCKETS": "Socket",
    "MISC": "Miscellaneous",
    "MISCELLANEOUS": "Miscellaneous",
    "HARDWARE": "Hardware",
}

_REFDES_RE = re.compile(r"^[A-Z]{1,3}\d{1,4}(?:[-,/]\d{1,4})?$")
_NAMED_REFDES_RE = re.compile(r"^[A-Z][A-Z0-9_-]{1,20}$")
_REFDES_BLOCKLIST = {
    "OR", "AND", "SEE", "USE", "TO", "FOR", "THE", "IF", "PNP", "NPN",
}


def extract_build_package_from_url(url: str) -> TaydakitsBuildPackage:
    """Fetch a Taydakits build URL and return the parsed package."""
    fetched = fetch_build(url)
    return extract_build_package_from_fetched(fetched)


def extract_build_package_from_fetched(
    fetched: FetchedTaydakitsBuild,
) -> TaydakitsBuildPackage:
    """Parse already-fetched HTML into a build package.

    Split out so tests can run against snapshot HTML without hitting the
    network.
    """
    pkg = TaydakitsBuildPackage(
        source_url=fetched.overview_url,
        step_urls=dict(fetched.step_urls),
    )

    pkg.title = _extract_title(fetched.overview_html)

    if fetched.designators_html:
        bom, layout_url, schematic_url = _parse_designators(
            fetched.designators_html, base=fetched.overview_url,
        )
        pkg.bom = bom
        pkg.pcb_layout_image_url = layout_url
        pkg.schematic_image_url = schematic_url
    else:
        pkg.warnings.append(
            "Couldn't fetch the components step — BOM is empty."
        )

    if fetched.drilling_html:
        pkg.enclosure = _detect_enclosure(fetched.drilling_html)
        pkg.drill_tool_url = _find_drill_tool_url(fetched.drilling_html)
    if pkg.enclosure is None and fetched.designators_html:
        pkg.enclosure = _detect_enclosure(fetched.designators_html)

    if fetched.wiring_html:
        pkg.wiring_image_url = _first_content_image(
            fetched.wiring_html, base=fetched.overview_url,
            prefer_substr="wiring",
        )

    # Auto-fetch holes from Tayda's public box-design API when a drill-tool
    # URL is present. This bypasses the rendered-image table entirely —
    # the SPA at drill.taydakits.com calls the same endpoint and gets the
    # same coordinates we get here.
    if pkg.drill_tool_url and not pkg.holes:
        try:
            api_holes = fetch_holes(pkg.drill_tool_url)
            if api_holes:
                pkg.holes = api_holes
        except TaydaDrillAPIError as exc:
            pkg.warnings.append(
                f"Couldn't fetch drill holes from Tayda's API ({exc}). "
                "You can still order the drilled enclosure via the "
                '"Order drilled enclosure…" button on the Drill tab.'
            )

    # If we still don't have holes, surface the manual-paste path as a
    # next-step. This only fires when the API fetch above failed or the
    # build doesn't link to a Tayda drill template.
    if not pkg.holes:
        pkg.next_steps.append(
            "Drill coordinates aren't auto-imported for this build. After "
            'creating the project, open the Drill tab and click "Order '
            'drilled enclosure…" to open Tayda\'s drill tool with the holes '
            'pre-loaded, or "Paste Tayda…" to enter them manually.'
        )

    if not pkg.bom:
        pkg.warnings.append(
            "BOM extraction yielded zero rows — the page layout may have "
            "changed. Add parts manually on the BOM tab."
        )
    if pkg.title is None:
        pkg.warnings.append("Could not detect build title.")
    if pkg.enclosure is None:
        pkg.warnings.append("Could not detect enclosure type.")

    return pkg


# ---- title ---------------------------------------------------------------

_TITLE_RE = re.compile(
    r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h1>',
    re.IGNORECASE | re.DOTALL,
)


def _extract_title(overview_html: str) -> str | None:
    m = _TITLE_RE.search(overview_html)
    if not m:
        return None
    raw = re.sub(r"<[^>]+>", "", m.group(1))
    title = unescape(re.sub(r"\s+", " ", raw)).strip()
    return title or None


# ---- enclosure -----------------------------------------------------------

_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    return unescape(_TAG_STRIP_RE.sub(" ", s))


def _detect_enclosure(html: str) -> str | None:
    text = _strip_tags(html)
    m = _ENCLOSURE_RE.search(text)
    if not m:
        return None
    key = re.sub(r"\s+", "", m.group(1).upper())
    return ENCLOSURE_ALIASES.get(key)


def _find_drill_tool_url(html: str) -> str | None:
    m = _DRILL_TOOL_RE.search(html)
    return m.group(1) if m else None


# ---- images --------------------------------------------------------------

_IMG_SRC_RE = re.compile(
    r'<img[^>]+src="([^"]+)"',
    re.IGNORECASE,
)


def _first_content_image(
    html: str,
    base: str,
    prefer_substr: str | None = None,
) -> str | None:
    """Find the first ckeditor-uploaded image, optionally preferring filenames
    containing ``prefer_substr``. Skips Gravatar, navbar logos, and Tayda
    product thumbnails — only /ckeditor_assets/ paths are eligible."""
    candidates: list[str] = []
    for match in _IMG_SRC_RE.finditer(html):
        src = match.group(1)
        if "ckeditor_assets" not in src:
            continue
        candidates.append(urljoin(base, src))
    if not candidates:
        return None
    if prefer_substr:
        for url in candidates:
            if prefer_substr.lower() in url.lower():
                return url
    return candidates[0]


# ---- BOM parser ----------------------------------------------------------


class _ComponentListParser(HTMLParser):
    """Walk the designators step looking for the COMPONENT LIST blocks.

    Taydakits structures the BOM as a series of <p style="margin-left:40px">
    blocks. Each starts with <strong>SectionName</strong> and contains
    rows separated by <br/>. Each row has the shape:
        <designator> <value> <a>DESCRIPTION</a>
    (or just "<designator> <a>DESCRIPTION</a>" for sections like Sockets
    or PCB where there's no separate value column).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_p = False
        self._is_component_p = False
        self._in_strong = False
        self._current_section: str | None = None
        self._current_row_text = ""
        self._first_strong_consumed = False
        self.rows: list[tuple[str, str]] = []
        self.image_srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "p":
            style = (attr.get("style") or "").lower()
            self._in_p = True
            self._is_component_p = "margin-left:40px" in style.replace(" ", "")
            self._first_strong_consumed = False
            self._current_row_text = ""
            self._current_section = None
        elif tag == "strong" and self._in_p and self._is_component_p:
            self._in_strong = True
        elif tag == "br" and self._in_p and self._is_component_p:
            self._flush_row()
        elif tag == "img":
            src = attr.get("src")
            if src:
                self.image_srcs.append(src)

    def handle_endtag(self, tag: str) -> None:
        if tag == "p":
            if self._in_p and self._is_component_p:
                self._flush_row()
            self._in_p = False
            self._is_component_p = False
            self._current_section = None
        elif tag == "strong":
            self._in_strong = False

    def handle_data(self, data: str) -> None:
        if not (self._in_p and self._is_component_p):
            return
        if self._in_strong and not self._first_strong_consumed:
            cleaned = data.strip()
            if cleaned:
                self._current_section = _normalize_header(cleaned)
                self._first_strong_consumed = True
            return
        self._current_row_text += data

    def _flush_row(self) -> None:
        text = _collapse_ws(self._current_row_text)
        self._current_row_text = ""
        if not text:
            return
        if self._current_section is None:
            return
        self.rows.append((self._current_section, text))


def _normalize_header(raw: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", "", raw).strip().upper()
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _parse_designators(
    html: str, base: str
) -> tuple[list[BOMItem], str | None, str | None]:
    """Parse the designators-and-components page into BOMItems plus image URLs.

    Returns (bom, pcb_layout_image_url, schematic_image_url).
    """
    parser = _ComponentListParser()
    parser.feed(html)

    bom: list[BOMItem] = []
    for section_key, row_text in parser.rows:
        bom_type = _SECTION_TYPES.get(section_key, _humanize_section(section_key))
        item = _parse_row(row_text, section_key, bom_type)
        if item is not None:
            bom.append(item)

    ckeditor = [
        urljoin(base, s) for s in parser.image_srcs if "ckeditor_assets" in s
    ]
    schematic_url = next(
        (u for u in ckeditor if "circuit" in u.lower()), None
    )
    layout_url = next(
        (u for u in ckeditor if "pcb" in u.lower() and "circuit" not in u.lower()),
        None,
    )
    if layout_url is None and ckeditor:
        layout_url = ckeditor[0]

    return bom, layout_url, schematic_url


def _humanize_section(key: str) -> str:
    return key.title() if key else "Component"


def _parse_row(text: str, section_key: str, bom_type: str) -> BOMItem | None:
    """Turn one whitespace-collapsed row into a BOMItem.

    Heuristic:
      - Token 0 is the designator. Standard refdes (R1, C100, IC1) or named
        (FUZZ, VOL) for pots; whole row is description for PCB/SOCKETS.
      - Sections with no value column (PCB, SOCKETS, HARDWARE, MISC):
        the rest is the description, value is blank.
      - Transistors: keep the full alternative list (e.g. "PNP 2N3906 / NPN
        2N3904, BC108 or BC109") as the value.
    """
    tokens = text.split()
    if not tokens:
        return None
    refdes = tokens[0].rstrip(",.;:").upper()
    if refdes in _REFDES_BLOCKLIST:
        return None
    if not (
        _REFDES_RE.match(refdes)
        or _NAMED_REFDES_RE.match(refdes)
        or section_key == "PCB"
    ):
        return None

    rest_tokens = tokens[1:]
    rest = " ".join(rest_tokens)

    if section_key in {"PCB", "SOCKETS", "HARDWARE", "MISC", "MISCELLANEOUS"}:
        notes = _strip_optional_marker(rest)
        if not notes:
            notes = refdes
        return BOMItem(
            location=refdes,
            value="",
            type=bom_type,
            notes=notes,
            polarity_sensitive=is_polarity_sensitive(f"{bom_type} {notes}"),
            quantity=1,
        )

    if not rest_tokens:
        return BOMItem(
            location=refdes,
            value="",
            type=bom_type,
            notes="",
            polarity_sensitive=is_polarity_sensitive(bom_type),
            quantity=1,
        )

    value = rest_tokens[0]
    notes = " ".join(rest_tokens[1:])
    notes = _strip_optional_marker(notes).strip()

    if section_key == "TRANSISTORS":
        value = rest
        notes = ""

    # Description (notes) carries the dielectric type for caps — promote it
    # so electrolytics get flagged polarity_sensitive even though the section
    # header is just "Capacitors".
    return BOMItem(
        location=refdes,
        value=value,
        type=bom_type,
        notes=notes,
        polarity_sensitive=is_polarity_sensitive(f"{bom_type} {notes}"),
        quantity=1,
    )


def _strip_optional_marker(s: str) -> str:
    return re.sub(r"\s*\(\s*optional\s*\)\s*$", " (optional)", s, flags=re.IGNORECASE).strip()


__all__ = [
    "TaydakitsBuildPackage",
    "TaydakitsFetchError",
    "extract_build_package_from_url",
    "extract_build_package_from_fetched",
]
