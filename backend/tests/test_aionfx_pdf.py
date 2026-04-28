from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pedal_bench.api.app import create_app
from pedal_bench.io.aionfx_drill import _diameter_mm, extract_drill_holes
from pedal_bench.io.aionfx_extract import (
    _find_exact_heading_page,
    _guess_enclosure,
    _guess_title,
    extract_build_package,
    is_aionfx_pdf,
)
from pedal_bench.io.aionfx_pdf import extract_bom


# Optional local fixture (not committed): drop an Aion FX build PDF here to
# enable integration-style parser tests, matching the PedalPCB fixture pattern.
HELIOS = Path(__file__).parent / "fixtures" / "helios_documentation.pdf"
APHELION = Path(__file__).parent / "fixtures" / "aphelion_documentation.pdf"


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
