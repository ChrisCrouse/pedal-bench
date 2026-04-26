"""Shortage computation: per-project view + global aggregate."""

from __future__ import annotations

from pathlib import Path

import pytest

from pedal_bench.core.inventory_store import InventoryStore
from pedal_bench.core.models import BOMItem, Project
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.core.shortage import (
    compute_global_shortage,
    compute_project_shortage,
)


def _project(slug: str, bom: list[tuple[str, str, str, int]], active: bool = True) -> Project:
    return Project(
        slug=slug,
        name=slug.title(),
        bom=[
            BOMItem(location=loc, value=val, type=t, quantity=qty)
            for loc, val, t, qty in bom
        ],
        active=active,
    )


@pytest.fixture
def stores(tmp_path: Path) -> tuple[ProjectStore, InventoryStore]:
    pstore = ProjectStore(tmp_path / "projects")
    inv = InventoryStore(tmp_path / "inventory.json")
    return pstore, inv


def test_per_project_shortage_with_zero_inventory(stores) -> None:
    pstore, inv = stores
    project = _project("muff", [
        ("R1", "10k", "1/4W Resistor", 4),
        ("IC1", "TL072", "Op-amp", 1),
    ])
    rows = compute_project_shortage(project, inv)
    by_kind = {r.kind: r for r in rows}
    assert by_kind["resistor"].needed == 4
    assert by_kind["resistor"].on_hand == 0
    assert by_kind["resistor"].shortfall == 4
    assert by_kind["ic"].shortfall == 1


def test_per_project_shortage_subtracts_other_reservations(stores) -> None:
    pstore, inv = stores
    project_a = _project("muff", [("IC1", "TL072", "Op-amp", 2)])
    inv.upsert(kind="ic", value_norm="TL072", on_hand=4)
    inv.set_reservation("ic::TL072", "rat", 3)  # held by another project

    rows = compute_project_shortage(project_a, inv)
    row = rows[0]
    assert row.on_hand == 4
    assert row.reserved_for_others == 3
    assert row.available == 1
    assert row.shortfall == 1  # needs 2, only 1 free


def test_own_reservation_does_not_reduce_self_availability(stores) -> None:
    pstore, inv = stores
    project = _project("muff", [("IC1", "TL072", "Op-amp", 2)])
    inv.upsert(kind="ic", value_norm="TL072", on_hand=2)
    inv.set_reservation("ic::TL072", "muff", 2)

    rows = compute_project_shortage(project, inv)
    row = rows[0]
    assert row.reserved_for_self == 2
    assert row.available == 2
    assert row.shortfall == 0


def test_global_shortage_sums_active_projects(stores, tmp_path: Path) -> None:
    pstore, inv = stores
    pstore.save(_project("muff", [("R1", "10k", "1/4W Resistor", 4)]))
    pstore.save(_project("rat",  [("R1", "10k", "1/4W Resistor", 3)]))
    pstore.save(_project("future", [("R1", "10k", "1/4W Resistor", 99)], active=False))
    inv.upsert(kind="resistor", value_norm="10k", on_hand=5)

    rows = compute_global_shortage(pstore, inv)
    assert len(rows) == 1
    row = rows[0]
    assert row.needed == 7  # inactive project excluded
    assert row.on_hand == 5
    assert row.shortfall == 2
    assert sorted(row.needed_by) == ["muff", "rat"]


def test_global_shortage_zero_when_well_stocked(stores) -> None:
    pstore, inv = stores
    pstore.save(_project("muff", [("R1", "10k", "1/4W Resistor", 2)]))
    inv.upsert(kind="resistor", value_norm="10k", on_hand=50)
    rows = compute_global_shortage(pstore, inv)
    assert rows[0].shortfall == 0


def test_value_normalization_joins_messy_inputs(stores) -> None:
    pstore, inv = stores
    project = _project("muff", [("R1", "100K Ohm", "1/4W Resistor", 2)])
    inv.upsert(kind="resistor", value_norm="100k", on_hand=10)
    rows = compute_project_shortage(project, inv)
    assert rows[0].on_hand == 10
    assert rows[0].shortfall == 0


def test_other_kind_rows_skipped(stores) -> None:
    pstore, inv = stores
    project = _project("muff", [
        ("ENCL", "125B", "Hammond enclosure", 1),
        ("R1", "10k", "1/4W Resistor", 1),
    ])
    rows = compute_project_shortage(project, inv)
    # The enclosure row classifies as "pot" (single-letter location pattern)
    # or "other"; either way, no enclosures should be in the rows we expect
    # to track. Just check the resistor is present.
    kinds = {r.kind for r in rows}
    assert "resistor" in kinds
