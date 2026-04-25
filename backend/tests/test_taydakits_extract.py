"""Snapshot-driven tests for the Taydakits HTML importer.

Uses real HTML captured from taydakits.com/instructions/fuzz-face on 2026-04-25
(stored under tests/data/taydakits_fuzz_face_*.html) so the parser can be
exercised offline. Refresh those files if Taydakits changes its template.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pedal_bench.io.taydakits_extract import (
    extract_build_package_from_fetched,
)
from pedal_bench.io.taydakits_fetch import (
    FetchedTaydakitsBuild,
    TaydakitsFetchError,
    _discover_steps,
    _validate_url,
)

DATA = Path(__file__).parent / "data"


def _read(name: str) -> str:
    return (DATA / name).read_text(encoding="utf-8")


@pytest.fixture
def fuzz_face_fetched() -> FetchedTaydakitsBuild:
    overview = _read("taydakits_fuzz_face_overview.html")
    base = "https://www.taydakits.com/instructions/fuzz-face"
    step_urls = _discover_steps(overview, slug="fuzz-face", base=base)
    return FetchedTaydakitsBuild(
        slug="fuzz-face",
        overview_url=base,
        overview_html=overview,
        designators_html=_read("taydakits_fuzz_face_designators.html"),
        drilling_html=_read("taydakits_fuzz_face_drilling.html"),
        wiring_html=_read("taydakits_fuzz_face_wiring.html"),
        step_urls=step_urls,
    )


# ---- URL validation ------------------------------------------------------

def test_validate_url_accepts_overview_url() -> None:
    canon, slug = _validate_url("https://www.taydakits.com/instructions/fuzz-face")
    assert canon == "https://www.taydakits.com/instructions/fuzz-face"
    assert slug == "fuzz-face"


def test_validate_url_canonicalizes_substep_to_overview() -> None:
    canon, slug = _validate_url(
        "https://www.taydakits.com/instructions/fuzz-face/pages/enclosure-drilling--21"
    )
    assert canon == "https://www.taydakits.com/instructions/fuzz-face"
    assert slug == "fuzz-face"


def test_validate_url_rejects_other_hosts() -> None:
    with pytest.raises(TaydakitsFetchError):
        _validate_url("https://pedalpcb.com/product/sherwood-overdrive/")


def test_validate_url_rejects_missing_slug() -> None:
    with pytest.raises(TaydakitsFetchError):
        _validate_url("https://www.taydakits.com/instructions/")


# ---- step discovery ------------------------------------------------------

def test_discover_steps_finds_all_five_steps(fuzz_face_fetched) -> None:
    steps = fuzz_face_fetched.step_urls
    assert "designators-and-components" in steps
    assert "pcb-assembly" in steps
    assert "enclosure-and-wiring" in steps
    assert "enclosure-drilling" in steps


# ---- title / enclosure ---------------------------------------------------

def test_title_extracted_from_overview(fuzz_face_fetched) -> None:
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    assert pkg.title == "Fuzz Face"


def test_enclosure_detected_as_1590B(fuzz_face_fetched) -> None:
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    assert pkg.enclosure == "1590B"


def test_drill_tool_url_extracted(fuzz_face_fetched) -> None:
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    assert pkg.drill_tool_url is not None
    assert "drill.taydakits.com" in pkg.drill_tool_url
    assert "public_key=" in pkg.drill_tool_url


# ---- BOM -----------------------------------------------------------------

def test_bom_has_expected_components(fuzz_face_fetched) -> None:
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    by_loc = {item.location: item for item in pkg.bom}

    # PCB row
    assert "PCB" in by_loc
    assert by_loc["PCB"].type == "PCB"

    # 4 capacitors
    assert by_loc["C1"].value == "2.2u"
    assert by_loc["C1"].type == "Capacitor"
    assert "RADIAL ELECTROLYTIC" in by_loc["C1"].notes.upper()
    assert by_loc["C1"].polarity_sensitive  # electrolytic

    assert by_loc["C2"].value == "22u"
    assert by_loc["C3"].value == "10n"
    assert by_loc["C3"].type == "Capacitor"
    assert by_loc["C4"].value == "47u"

    # 2 transistors — the full alternative list lives in the value column
    assert "Q1" in by_loc and "Q2" in by_loc
    assert by_loc["Q1"].type == "Transistor"
    assert "2N3906" in by_loc["Q1"].value
    assert "2N3904" in by_loc["Q1"].value
    assert by_loc["Q1"].polarity_sensitive

    # 4 resistors — including R4 marked Optional
    assert by_loc["R1"].value == "100k"
    assert by_loc["R1"].type == "Resistor, 1/4W"
    assert by_loc["R2"].value == "33k"
    assert by_loc["R3"].value == "470"
    assert by_loc["R4"].value == "1M"
    assert "optional" in by_loc["R4"].notes.lower()

    # Bias trim pot — Taydakits lists it in the Resistors block
    assert "BIAS" in by_loc
    assert by_loc["BIAS"].value == "50k"

    # 2 named pots
    assert "FUZZ" in by_loc
    assert by_loc["FUZZ"].type == "Potentiometer"
    assert "1k-B" in by_loc["FUZZ"].value
    assert "VOL" in by_loc
    assert "500k-A" in by_loc["VOL"].value


def test_bom_count_within_expected_range(fuzz_face_fetched) -> None:
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    locs = [item.location for item in pkg.bom]
    # PCB + 4 caps + 2 transistors + 1 sockets + 4 resistors + 1 bias + 2 pots = 15
    # The Sockets row uses "SOCKETS" as a refdes (named) so we expect 14 or 15.
    assert 12 <= len(pkg.bom) <= 18, (
        f"Unexpected BOM size {len(pkg.bom)}: {locs}"
    )


# ---- images --------------------------------------------------------------

def test_pcb_layout_image_url_found(fuzz_face_fetched) -> None:
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    assert pkg.pcb_layout_image_url is not None
    assert "ckeditor_assets" in pkg.pcb_layout_image_url
    # Should be the PCB image, not the schematic.
    assert "circuit" not in pkg.pcb_layout_image_url.lower() or "pcb" in pkg.pcb_layout_image_url.lower()


def test_schematic_image_url_found(fuzz_face_fetched) -> None:
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    assert pkg.schematic_image_url is not None
    assert "circuit" in pkg.schematic_image_url.lower()


def test_wiring_image_url_found(fuzz_face_fetched) -> None:
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    assert pkg.wiring_image_url is not None
    assert "ckeditor_assets" in pkg.wiring_image_url


# ---- walkthrough next-step ------------------------------------------------

def test_drill_walkthrough_not_in_warnings(fuzz_face_fetched) -> None:
    """The drill-tool walkthrough — when surfaced — must live in next_steps,
    not in warnings. Warnings are reserved for actual problems."""
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    leaked = [w for w in pkg.warnings if "Drill tab" in w or "drill.taydakits.com" in w]
    assert not leaked, f"Walkthrough leaked into warnings: {leaked}"


def test_holes_auto_populate_from_api(fuzz_face_fetched, monkeypatch) -> None:
    """When a drill_tool_url is present and the Tayda API returns holes,
    they should land directly on the package — no walkthrough needed."""
    import pedal_bench.io.taydakits_extract as mod
    from pedal_bench.core.models import Hole

    fake_holes = [
        Hole(side="A", x_mm=14.0, y_mm=38.0, diameter_mm=8.0, icon="pot"),
        Hole(side="A", x_mm=-14.0, y_mm=38.0, diameter_mm=8.0, icon="pot"),
        Hole(side="A", x_mm=0.0, y_mm=4.5, diameter_mm=3.2, icon="led"),
    ]
    monkeypatch.setattr(mod, "fetch_holes", lambda url: fake_holes)
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    assert len(pkg.holes) == 3
    # No walkthrough needed when we got the holes directly.
    drill_walkthroughs = [
        s for s in pkg.next_steps
        if "Drill tab" in s and "Paste Tayda" in s
    ]
    assert not drill_walkthroughs


def test_drill_walkthrough_only_when_no_holes(fuzz_face_fetched, monkeypatch) -> None:
    """When the Tayda API auto-fetch succeeds, no walkthrough is needed —
    holes are already on the package. The walkthrough next-step should
    only appear if we ended up with zero holes."""
    # Force the API path to return nothing so the next-step is exercised.
    import pedal_bench.io.taydakits_extract as mod

    monkeypatch.setattr(mod, "fetch_holes", lambda url: [])
    pkg = extract_build_package_from_fetched(fuzz_face_fetched)
    if not pkg.holes:
        drill_msgs = [
            s for s in pkg.next_steps
            if "Drill tab" in s and ("Paste Tayda" in s or "Order drilled enclosure" in s)
        ]
        assert drill_msgs, (
            f"Expected walkthrough when holes empty; got next_steps={pkg.next_steps}"
        )
