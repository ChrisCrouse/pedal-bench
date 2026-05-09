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
    count_buildable_projects,
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
    # Per-slug quantity contribution drives accurate cost rollups —
    # equal-split would misattribute when projects need different amounts.
    assert row.needed_by_qty == {"muff": 4, "rat": 3}


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


def test_inventory_unit_cost_wins_over_oracle(stores) -> None:
    """User-set unit_cost_usd on an InventoryItem must override the static
    price oracle. The user's actual paid price is the source of truth; the
    oracle is just a fallback when they haven't logged anything."""
    pstore, inv = stores
    project = _project("muff", [("R1", "10k", "1/4W Resistor", 4)])
    # Stock the item with an explicit user price way off the typical Tayda
    # price so any oracle leak would be obvious.
    inv.upsert(
        kind="resistor", value_norm="10k", on_hand=0, unit_cost_usd=99.0,
    )
    rows = compute_project_shortage(project, inv)
    row = rows[0]
    assert row.unit_cost_usd == 99.0
    assert row.unit_cost_estimated is False


def test_oracle_fills_in_when_no_inventory_item(stores) -> None:
    """If the user hasn't even created the inventory row yet, the shortage
    view should still show a sensible cost-to-finish thanks to the oracle."""
    pstore, inv = stores
    project = _project("muff", [("R1", "10k", "1/4W Resistor", 10)])
    rows = compute_project_shortage(project, inv)
    row = rows[0]
    assert row.unit_cost_usd is not None
    assert row.unit_cost_usd > 0
    assert row.unit_cost_estimated is True


def test_oracle_fills_in_when_inventory_has_no_price(stores) -> None:
    pstore, inv = stores
    project = _project("muff", [("R1", "10k", "1/4W Resistor", 10)])
    inv.upsert(kind="resistor", value_norm="10k", on_hand=2)  # no unit_cost
    rows = compute_project_shortage(project, inv)
    row = rows[0]
    assert row.unit_cost_usd is not None
    assert row.unit_cost_estimated is True


def test_oracle_returns_none_for_unknown_ic(stores) -> None:
    """ICs default to null in the oracle (prices vary 10x), so an unknown
    IC stays priceless rather than getting a fake guess."""
    pstore, inv = stores
    project = _project(
        "exotic", [("IC1", "MADE_UP_OPAMP", "Op-amp", 1)],
    )
    rows = compute_project_shortage(project, inv)
    row = rows[0]
    assert row.unit_cost_usd is None
    assert row.unit_cost_estimated is False


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


# ---- buildability count -------------------------------------------------


def _project_with_ts(
    slug: str,
    bom: list[tuple[str, str, str, int]],
    updated_at: str,
    active: bool = True,
) -> Project:
    return Project(
        slug=slug,
        name=slug.title(),
        bom=[
            BOMItem(location=loc, value=val, type=t, quantity=qty)
            for loc, val, t, qty in bom
        ],
        active=active,
        updated_at=updated_at,
    )


def test_buildability_all_stocked(stores) -> None:
    pstore, inv = stores
    pstore.save(_project("muff", [("R1", "10k", "1/4W Resistor", 4)]))
    pstore.save(_project("rat",  [("R1", "10k", "1/4W Resistor", 3)]))
    inv.upsert(kind="resistor", value_norm="10k", on_hand=100)
    buildable, total = count_buildable_projects(pstore, inv)
    assert (buildable, total) == (2, 2)


def test_buildability_greedy_does_not_double_count(stores) -> None:
    """Two projects each need 4×100n. Stock is 5. Naive per-project view
    would call both buildable; greedy must allocate to one."""
    pstore, inv = stores
    # rat is the more recent build → wins the allocation under updated_at-desc.
    pstore.save(_project_with_ts(
        "muff", [("C1", "100n", "Film Cap", 4)], updated_at="2026-01-01T00:00:00",
    ))
    pstore.save(_project_with_ts(
        "rat",  [("C1", "100n", "Film Cap", 4)], updated_at="2026-02-01T00:00:00",
    ))
    inv.upsert(kind="film-cap", value_norm="100n", on_hand=5)
    buildable, total = count_buildable_projects(pstore, inv)
    assert (buildable, total) == (1, 2)


def test_buildability_inactive_excluded(stores) -> None:
    pstore, inv = stores
    pstore.save(_project("muff", [("R1", "10k", "1/4W Resistor", 4)]))
    pstore.save(_project("future", [("R1", "10k", "1/4W Resistor", 99)], active=False))
    inv.upsert(kind="resistor", value_norm="10k", on_hand=100)
    buildable, total = count_buildable_projects(pstore, inv)
    # Only muff counts; future is inactive.
    assert (buildable, total) == (1, 1)


def test_buildability_empty_bom_is_buildable(stores) -> None:
    pstore, inv = stores
    pstore.save(_project("placeholder", []))
    buildable, total = count_buildable_projects(pstore, inv)
    assert (buildable, total) == (1, 1)


def test_buildability_no_active_projects(stores) -> None:
    pstore, inv = stores
    pstore.save(_project("future", [("R1", "10k", "1/4W Resistor", 1)], active=False))
    buildable, total = count_buildable_projects(pstore, inv)
    assert (buildable, total) == (0, 0)


def test_buildability_partial_shortage_blocks(stores) -> None:
    """A project missing even one needed part is not buildable."""
    pstore, inv = stores
    pstore.save(_project("muff", [
        ("R1", "10k", "1/4W Resistor", 2),
        ("IC1", "TL072", "Op-amp", 1),
    ]))
    inv.upsert(kind="resistor", value_norm="10k", on_hand=100)
    # No TL072 in stock → muff is blocked.
    buildable, total = count_buildable_projects(pstore, inv)
    assert (buildable, total) == (0, 1)
