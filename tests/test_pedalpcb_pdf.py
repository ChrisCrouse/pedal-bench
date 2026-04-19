"""Unit + integration tests for the PedalPCB BOM parser.

Unit tests exercise the internal row/header detection on synthetic tables
and don't need a real PDF.

The integration test runs against a fixture PDF if one exists at
`tests/fixtures/sherwood.pdf`. Drop a real PedalPCB PDF there to enable it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.io.pedalpcb_pdf import (
    _find_header,
    _rows_to_items,
    extract_bom,
)


# ---- synthetic-table unit tests ------------------------------------------

def test_find_header_locates_standard_columns() -> None:
    table = [
        ["LOCATION", "VALUE", "TYPE", "NOTES"],
        ["R1", "1M", "Resistor, 1/4W", ""],
    ]
    idx, col_map = _find_header(table)
    assert idx == 0
    assert col_map == {"location": 0, "value": 1, "type": 2, "notes": 3}


def test_find_header_skips_leading_junk() -> None:
    table = [
        ["Sherwood Overdrive Parts List"],
        [],
        ["LOCATION", "VALUE", "TYPE", "NOTES"],
        ["R1", "1M", "Resistor, 1/4W", ""],
    ]
    idx, _ = _find_header(table)
    assert idx == 2


def test_find_header_returns_none_for_unrelated_table() -> None:
    table = [
        ["foo", "bar", "baz"],
        ["1", "2", "3"],
    ]
    idx, col_map = _find_header(table)
    assert idx is None
    assert col_map == {}


def test_rows_to_items_tags_polarity_sensitive() -> None:
    rows = [
        ["R1", "1M", "Resistor, 1/4W", ""],
        ["D1", "1N4148", "Signal diode, DO-35", ""],
        ["C5", "10u", "Electrolytic capacitor, 5mm", ""],
        ["IC1", "OPA2134PA", "Dual op-amp, DIP8", ""],
        ["Q1", "2N5089", "BJT transistor, NPN TO-92", ""],
    ]
    col_map = {"location": 0, "value": 1, "type": 2, "notes": 3}
    items = _rows_to_items(rows, col_map)

    assert [i.location for i in items] == ["R1", "D1", "C5", "IC1", "Q1"]
    assert items[0].polarity_sensitive is False  # resistor
    assert items[1].polarity_sensitive is True   # diode
    assert items[2].polarity_sensitive is True   # electrolytic
    assert items[3].polarity_sensitive is True   # op-amp
    assert items[4].polarity_sensitive is True   # transistor


def test_rows_to_items_skips_blank_section_breaks() -> None:
    rows = [
        ["R1", "1M", "Resistor, 1/4W", ""],
        ["", "", "", ""],
        ["C1", "100p", "Ceramic capacitor", ""],
    ]
    col_map = {"location": 0, "value": 1, "type": 2, "notes": 3}
    items = _rows_to_items(rows, col_map)
    assert len(items) == 2


def test_rows_to_items_skips_repeated_header_across_pages() -> None:
    rows = [
        ["R1", "1M", "Resistor, 1/4W", ""],
        ["LOCATION", "VALUE", "TYPE", "NOTES"],  # header on the next page
        ["R2", "1K", "Resistor, 1/4W", ""],
    ]
    col_map = {"location": 0, "value": 1, "type": 2, "notes": 3}
    items = _rows_to_items(rows, col_map)
    assert [i.location for i in items] == ["R1", "R2"]


def test_rows_to_items_preserves_asterisked_notes() -> None:
    rows = [
        ["CLR", "4K7", "Resistor, 1/4W", "* LED current limiting resistor"],
    ]
    col_map = {"location": 0, "value": 1, "type": 2, "notes": 3}
    items = _rows_to_items(rows, col_map)
    assert items[0].notes == "* LED current limiting resistor"


def test_rows_to_items_collapses_embedded_newlines() -> None:
    # pdfplumber sometimes returns wrapped text with embedded newlines.
    rows = [
        ["R1", "1M", "Resistor,\n1/4W", "foo\nbar"],
    ]
    col_map = {"location": 0, "value": 1, "type": 2, "notes": 3}
    items = _rows_to_items(rows, col_map)
    assert items[0].type == "Resistor, 1/4W"
    assert items[0].notes == "foo bar"


def test_rows_to_items_none_cells() -> None:
    rows = [
        ["R1", "1M", "Resistor, 1/4W", None],
        [None, None, None, None],
    ]
    col_map = {"location": 0, "value": 1, "type": 2, "notes": 3}
    items = _rows_to_items(rows, col_map)
    assert len(items) == 1
    assert items[0].notes == ""


# ---- integration test (Sherwood PDF fixture) -----------------------------

SHERWOOD = Path(__file__).parent / "fixtures" / "sherwood.pdf"


@pytest.mark.skipif(not SHERWOOD.is_file(), reason="Sherwood fixture PDF not present")
def test_extract_bom_sherwood_smoke() -> None:
    items = extract_bom(SHERWOOD)

    # The Sherwood BOM has ~40 rows total (resistors + caps + diodes +
    # transistors + IC + pots). Tolerance for small changes across PDF revisions.
    assert 35 <= len(items) <= 50

    locations = {i.location for i in items}
    # Spot-check canonical rows.
    for expected in ("R1", "R5", "CLR", "C1", "D100", "IC1", "Q1", "Q2",
                     "LEVEL", "DRIVE", "BASS", "TREBLE"):
        assert expected in locations, f"missing {expected} in BOM"

    by_loc = {i.location: i for i in items}
    assert by_loc["R1"].value == "1M"
    assert by_loc["CLR"].value == "4K7"
    assert "LED" in by_loc["CLR"].notes  # "* LED current limiting resistor"
    assert by_loc["IC1"].value == "OPA2134PA"
    assert by_loc["IC1"].polarity_sensitive is True
    assert by_loc["Q1"].polarity_sensitive is True
    assert by_loc["R1"].polarity_sensitive is False
