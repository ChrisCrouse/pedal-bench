from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pedal_bench.api.app import create_app
from pedal_bench.core.models import Enclosure, FaceDims, Hole
from pedal_bench.io.aionfx_drill import (
    _apply_enclosure_transform_and_validation,
    _diameter_mm,
    extract_drill_holes,
)
from pedal_bench.io.aionfx_extract import (
    _find_exact_heading_page,
    _guess_enclosure,
    _guess_title,
    extract_build_package,
    is_aionfx_pdf,
)
from pedal_bench.io.aionfx_pdf import _parse_parts_list_words, extract_bom


# Optional local fixture (not committed): drop an Aion FX build PDF here to
# enable integration-style parser tests, matching the PedalPCB fixture pattern.
HELIOS = Path(__file__).parent / "fixtures" / "helios_documentation.pdf"
APHELION = Path(__file__).parent / "fixtures" / "aphelion_documentation.pdf"


def _word(text: str, x0: float, top: float, x1: float | None = None) -> dict:
    return {"text": text, "x0": x0, "x1": x1 if x1 is not None else x0 + 20, "top": top}


def test_parse_parts_list_words_handles_dual_value_columns() -> None:
    words = [
        _word("PART", 50, 100),
        _word("VALUE", 130, 100),
        _word("VALUE", 190, 100),
        _word("TYPE", 250, 100),
        _word("NOTES", 380, 100),
        _word("R1", 50, 120),
        _word("10k", 70, 120),  # spilled into PART column
        _word("ALT", 200, 120),  # ignored when dual value header is present
        _word("Metal", 250, 120),
        _word("film", 290, 120),
        _word("resistor", 330, 120),
    ]

    items = _parse_parts_list_words(words)
    assert len(items) == 1
    assert items[0].location == "R1"
    assert items[0].value == "10k"
    assert items[0].type == "Metal film resistor"


def test_parse_parts_list_words_merges_wrapped_continuations() -> None:
    words = [
        _word("PART", 50, 100),
        _word("VALUE", 130, 100),
        _word("TYPE", 250, 100),
        _word("NOTES", 380, 100),
        _word("RPD", 50, 120),
        _word("1M", 130, 120),
        _word("Metal", 250, 120),
        _word("film", 290, 120),
        _word("resistor", 330, 120),
        _word("Input", 380, 120),
        _word("pulldown", 430, 120),
        _word("resistor.", 500, 120),
        _word("Keep", 250, 140),  # wrapped continuation row (no part/value)
        _word("close", 300, 140),
        _word("to", 340, 140),
        _word("input.", 360, 140),
    ]

    items = _parse_parts_list_words(words)
    assert len(items) == 1
    assert items[0].location == "RPD"
    assert "Input pulldown resistor." in items[0].notes
    assert "Keep close to input." in items[0].notes


def test_apply_enclosure_transform_recenters_edge_origin_coords_and_filters() -> None:
    enclosure = Enclosure(
        key="125B",
        name="Hammond 125B",
        length_mm=120.0,
        width_mm=95.0,
        height_mm=35.0,
        wall_thickness_mm=2.0,
        faces={
            "A": FaceDims(width_mm=60.0, height_mm=110.0, label="Top"),
            "B": FaceDims(width_mm=60.0, height_mm=30.0, label="North"),
        },
    )
    holes = [
        Hole(side="A", x_mm=12.0, y_mm=20.0, diameter_mm=7.0, label="KEPT_CENTERED", icon="pot"),
        Hole(side="A", x_mm=55.0, y_mm=100.0, diameter_mm=7.0, label="RECENTERED", icon="pot"),
        Hole(side="A", x_mm=92.0, y_mm=100.0, diameter_mm=7.0, label="DROPPED", icon="pot"),
    ]

    normalized = _apply_enclosure_transform_and_validation(holes, enclosure)
    by_label = {h.label: h for h in normalized}

    assert len(normalized) == 2
    assert by_label["KEPT_CENTERED"].x_mm == pytest.approx(12.0)
    assert by_label["RECENTERED"].x_mm == pytest.approx(25.0)
    assert by_label["RECENTERED"].y_mm == pytest.approx(45.0)
    assert "DROPPED" not in by_label


def test_aionfx_title_enclosure_and_page_roles_from_text() -> None:
    texts = [
        "PROJECT NAME\nHELIOS\nBASED ON BUILD DIFFICULTY\nPro Co RAT Easy",
        "TABLE OF CONTENTS\n8 Drill Template\n10 Wiring Diagram",
        "DRILL TEMPLATE\nCut out this drill template.",
        "WIRING DIAGRAM\n125B",
    ]

    assert _guess_title(texts) == "Helios"
    assert _guess_enclosure(texts) == "125B"
    assert _find_exact_heading_page(texts, "DRILL TEMPLATE") == 2
    assert _find_exact_heading_page(texts, "WIRING DIAGRAM") == 3


def test_diameter_fraction_conversion() -> None:
    assert _diameter_mm("ø9/32”") == pytest.approx(7.14375)
    assert _diameter_mm("ø15/32\"") == pytest.approx(11.90625)


@pytest.mark.skipif(not HELIOS.is_file(), reason="Helios fixture PDF not present in tests/fixtures")
def test_extract_bom_helios_fixture() -> None:
    items = extract_bom(HELIOS)
    by_loc = {item.location: item for item in items}

    assert len(items) == 51
    assert by_loc["R1"].value == "1M"
    assert by_loc["R1"].type == "Metal film resistor, 1/4W"
    assert by_loc["C3"].value == "OMIT"
    assert "Leave empty" in by_loc["C3"].notes
    assert by_loc["IC1"].polarity_sensitive is True
    assert by_loc["ENC"].value == "125B"


@pytest.mark.skipif(not APHELION.is_file(), reason="Aphelion fixture PDF not present in tests/fixtures")
def test_extract_bom_aphelion_fixture() -> None:
    items = extract_bom(APHELION)
    by_loc = {item.location: item for item in items}

    assert len(items) == 42
    assert by_loc["R1"].value == "10k"
    assert by_loc["RPD"].type == "Metal film resistor, 1/4W"
    assert "Input pulldown resistor." in by_loc["RPD"].notes
    assert by_loc["D2"].value == "Ge"
    assert by_loc["IC1"].polarity_sensitive is True
    assert by_loc["TREBLE"].value == "SPDT cntr off"
    assert "Toggle switch, SPDT on-off-on" in by_loc["TREBLE"].type


@pytest.mark.skipif(not HELIOS.is_file(), reason="Helios fixture PDF not present in tests/fixtures")
def test_extract_drill_holes_helios_fixture() -> None:
    holes = extract_drill_holes(HELIOS)
    assert holes is not None
    by_label = {hole.label: hole for hole in holes}

    assert len(holes) == 10
    assert by_label["VOLUME"].x_mm == pytest.approx(-16.51)
    assert by_label["DISTORTION"].y_mm == pytest.approx(43.43)
    assert by_label["MODE"].icon == "toggle"
    assert by_label["FOOTSWITCH"].diameter_mm == pytest.approx(11.91)
    assert by_label["DC"].side == "B"
    assert by_label["DC"].icon == "dc-jack"


@pytest.mark.skipif(not HELIOS.is_file(), reason="Helios fixture PDF not present in tests/fixtures")
def test_extract_build_package_helios_fixture() -> None:
    assert is_aionfx_pdf(HELIOS)
    pkg = extract_build_package(HELIOS)

    assert pkg.source_supplier == "aionfx"
    assert pkg.title == "Helios"
    assert pkg.enclosure == "125B"
    assert pkg.drill_template_page_index == 7
    assert pkg.pcb_layout_page_index == 0
    assert pkg.wiring_page_index == 9
    assert len(pkg.bom) == 51
    assert len(pkg.holes) == 10
    assert pkg.warnings == []


@pytest.mark.skipif(not HELIOS.is_file(), reason="Helios fixture PDF not present in tests/fixtures")
def test_pdf_extract_route_dispatches_aion_fixture() -> None:
    client = TestClient(create_app())
    with HELIOS.open("rb") as fh:
        response = client.post(
            "/api/v1/pdf/extract",
            files={"file": ("helios_documentation.pdf", fh, "application/pdf")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["source_supplier"] == "aionfx"
    assert data["suggested_name"] == "Helios"
    assert data["suggested_enclosure"] == "125B"
    assert len(data["bom"]) == 51
    assert len(data["holes"]) == 10
