"""Cross-project inventory index — classification, normalization, queries."""

from __future__ import annotations

from pathlib import Path

import pytest

from pedal_bench.core.inventory_index import (
    InventoryIndex,
    classify,
    normalize_value,
    value_magnitude,
)
from pedal_bench.core.models import BOMItem, Project
from pedal_bench.core.project_store import ProjectStore


# --- classify ---------------------------------------------------------------


@pytest.mark.parametrize(
    "loc, type_str, expected",
    [
        ("R1", "Resistor 1/4W", "resistor"),
        ("R12", "", "resistor"),
        ("CLR", "", "resistor"),  # current-limit resistor convention
        ("C1", "Ceramic", "film-cap"),
        ("C2", "Electrolytic", "electrolytic"),
        ("C3", "Tantalum", "electrolytic"),
        ("D1", "1N4148", "diode"),
        ("Q1", "2N3904", "transistor"),
        ("IC1", "TL072", "ic"),
        ("L1", "", "inductor"),
        ("SW1", "", "switch"),
        ("S2", "", "switch"),
        ("LEVEL", "", "pot"),  # pure-letter location => pot
        ("", "Op-amp", "ic"),
        ("", "Polypropylene cap", "film-cap"),
        ("", "JFET transistor", "transistor"),
        ("", "Random thing", "other"),
    ],
)
def test_classify(loc: str, type_str: str, expected: str) -> None:
    assert classify(loc, type_str) == expected


# --- normalize_value --------------------------------------------------------


@pytest.mark.parametrize(
    "raw, kind, expected",
    [
        ("100K", "resistor", "100k"),
        ("100k", "resistor", "100k"),
        ("100 K", "resistor", "100k"),
        ("100K Ohm", "resistor", "100k"),
        ("100k 1/4W", "resistor", "100k"),
        ("1uF", "film-cap", "1uf"),
        ("1µF", "film-cap", "1uf"),
        ("1 uF", "film-cap", "1uf"),
        ("TL072", "ic", "TL072"),
        ("tl072", "ic", "TL072"),
        ("TL072 CP", "ic", "TL072CP"),
        ("1N4148", "diode", "1N4148"),
        ("", "resistor", ""),
    ],
)
def test_normalize_value(raw: str, kind: str, expected: str) -> None:
    assert normalize_value(raw, kind) == expected


# --- InventoryIndex end-to-end ---------------------------------------------


@pytest.fixture
def store_with_projects(tmp_path: Path) -> ProjectStore:
    store = ProjectStore(tmp_path / "projects")
    p1 = store.create("Sherwood", enclosure="1590B")
    p1.bom = [
        BOMItem(location="R1", value="100K", type="Resistor", quantity=1),
        BOMItem(location="R2", value="100k", type="Resistor", quantity=2),
        BOMItem(location="C1", value="100nF", type="Ceramic", quantity=1),
        BOMItem(location="IC1", value="TL072", type="Op-amp", quantity=1),
    ]
    store.save(p1)

    p2 = store.create("Awful Waffle", enclosure="1590A")
    p2.bom = [
        BOMItem(location="R1", value="100K Ohm", type="Resistor 1/4W", quantity=3),
        BOMItem(location="IC1", value="TL072", type="Op-amp", quantity=1),
        BOMItem(location="Q1", value="2N3904", type="Transistor", quantity=2),
    ]
    store.save(p2)
    return store


def test_part_totals_groups_across_projects(
    store_with_projects: ProjectStore, tmp_path: Path
) -> None:
    idx = InventoryIndex(tmp_path / "idx.sqlite", store_with_projects)
    idx.refresh()

    parts = idx.part_totals()
    by_key = {(p.kind, p.value_norm): p for p in parts}

    # 1 + 2 + 3 = 6 across both projects, despite "100K" / "100k" / "100K Ohm"
    r100k = by_key[("resistor", "100k")]
    assert r100k.total_qty == 6
    assert r100k.project_count == 2

    # TL072 appears in both projects, 1 + 1 = 2
    tl072 = by_key[("ic", "TL072")]
    assert tl072.total_qty == 2
    assert tl072.project_count == 2

    # 2N3904 only in Awful Waffle
    q = by_key[("transistor", "2N3904")]
    assert q.total_qty == 2
    assert q.project_count == 1


def test_part_totals_filter_by_kind(
    store_with_projects: ProjectStore, tmp_path: Path
) -> None:
    idx = InventoryIndex(tmp_path / "idx.sqlite", store_with_projects)
    idx.refresh()
    parts = idx.part_totals(kind_filter="resistor")
    assert all(p.kind == "resistor" for p in parts)
    assert any(p.value_norm == "100k" for p in parts)


def test_projects_using_returns_quantities(
    store_with_projects: ProjectStore, tmp_path: Path
) -> None:
    idx = InventoryIndex(tmp_path / "idx.sqlite", store_with_projects)
    idx.refresh()
    hits = idx.projects_using("resistor", "100k")
    by_slug = {h.slug: h for h in hits}
    assert by_slug["sherwood"].quantity == 3   # R1 + R2 = 1 + 2
    assert by_slug["awful-waffle"].quantity == 3


def test_stats(store_with_projects: ProjectStore, tmp_path: Path) -> None:
    idx = InventoryIndex(tmp_path / "idx.sqlite", store_with_projects)
    idx.refresh()
    s = idx.stats()
    assert s["project_count"] == 2
    # unique parts: 100k resistor, 100nF cap, TL072, 2N3904 => 4
    assert s["unique_parts"] == 4
    # total parts: 1+2+1+1 + 3+1+2 = 11
    assert s["total_parts"] == 11
    kinds = {row["kind"] for row in s["by_kind"]}
    assert kinds == {"resistor", "film-cap", "ic", "transistor"}


def test_refresh_picks_up_new_project(
    store_with_projects: ProjectStore, tmp_path: Path
) -> None:
    idx = InventoryIndex(tmp_path / "idx.sqlite", store_with_projects)
    idx.refresh()
    assert idx.stats()["project_count"] == 2

    p3 = store_with_projects.create("Third One", enclosure="1590B")
    p3.bom = [BOMItem(location="R1", value="10K", type="Resistor", quantity=4)]
    store_with_projects.save(p3)

    idx.refresh()
    assert idx.stats()["project_count"] == 3
    parts = idx.part_totals(kind_filter="resistor")
    by_norm = {p.value_norm: p for p in parts}
    assert by_norm["10k"].total_qty == 4


# --- value_magnitude --------------------------------------------------------


@pytest.mark.parametrize(
    "raw, kind, expected",
    [
        ("10k",   "resistor", 10_000.0),
        ("1.2k",  "resistor", 1_200.0),
        ("100k",  "resistor", 100_000.0),
        ("1k",    "resistor", 1_000.0),
        ("10M",   "resistor", 10_000_000.0),
        ("2.2M",  "resistor", 2_200_000.0),
        ("470",   "resistor", 470.0),
        ("10R",   "resistor", 10.0),
        ("100n",  "film-cap", 100e-9),
        ("10u",   "electrolytic", 10e-6),
        ("4u7",   "electrolytic", 4.7e-6),
        ("2k2",   "resistor", 2_200.0),
        ("",      "resistor", None),
        ("TL072", "ic", None),       # IC part numbers don't get magnitudes
        ("2N3904","transistor", None),
    ],
)
def test_value_magnitude(raw: str, kind: str, expected: float | None) -> None:
    got = value_magnitude(raw, kind)
    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected)


def test_value_magnitude_sort_order() -> None:
    """Real-world resistor-bin values must order numerically."""
    raws = ["1.2k", "1.5k", "100k", "10k", "10M", "150k", "1k", "1M", "47k", "4.7k"]
    sorted_by_mag = sorted(raws, key=lambda r: value_magnitude(r, "resistor") or 0)
    assert sorted_by_mag == ["1k", "1.2k", "1.5k", "4.7k", "10k", "47k", "100k", "150k", "1M", "10M"]
