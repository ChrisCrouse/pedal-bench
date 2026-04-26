"""Inventory bookkeeping driven by solder progress."""

from __future__ import annotations

from pathlib import Path

import pytest

from pedal_bench.core.inventory_store import InventoryStore
from pedal_bench.core.models import BOMItem, BuildProgress, Project, inventory_key
from pedal_bench.core.solder_consumption import apply_solder_delta


def _project(slug: str = "muff") -> Project:
    return Project(
        slug=slug,
        name=slug.title(),
        bom=[
            BOMItem(location="R1", value="10k", type="1/4W Resistor", quantity=1),
            BOMItem(location="R2", value="10k", type="1/4W Resistor", quantity=1),
            BOMItem(location="IC1", value="TL072", type="Op-amp", quantity=1),
            BOMItem(location="ENCL", value="125B", type="Hammond enclosure", quantity=1),
        ],
    )


@pytest.fixture
def inv(tmp_path: Path) -> InventoryStore:
    return InventoryStore(tmp_path / "inventory.json")


def test_solder_decrements_on_hand(inv: InventoryStore) -> None:
    inv.upsert(kind="resistor", value_norm="10k", on_hand=20)
    project = _project()
    delta = apply_solder_delta(project, set(), {"R1"}, inv)
    assert delta.consumed == [(inventory_key("resistor", "10k"), 1)]
    assert inv.get(inventory_key("resistor", "10k")).on_hand == 19


def test_unsolder_restores_on_hand(inv: InventoryStore) -> None:
    inv.upsert(kind="resistor", value_norm="10k", on_hand=20)
    project = _project()
    apply_solder_delta(project, set(), {"R1"}, inv)
    delta = apply_solder_delta(project, {"R1"}, set(), inv)
    assert delta.restored == [(inventory_key("resistor", "10k"), 1)]
    assert inv.get(inventory_key("resistor", "10k")).on_hand == 20


def test_solder_consumes_own_reservation_first(inv: InventoryStore) -> None:
    """Reserving 2 then soldering 1 should drop both reservation and on_hand by 1
    so reserved <= on_hand stays true."""
    inv.upsert(kind="resistor", value_norm="10k", on_hand=20)
    inv.set_reservation(inventory_key("resistor", "10k"), "muff", 2)
    project = _project()
    apply_solder_delta(project, set(), {"R1"}, inv)
    item = inv.get(inventory_key("resistor", "10k"))
    assert item.on_hand == 19
    assert item.reservations == {"muff": 1}


def test_solder_does_not_touch_other_projects_reservations(inv: InventoryStore) -> None:
    inv.upsert(kind="resistor", value_norm="10k", on_hand=20)
    inv.set_reservation(inventory_key("resistor", "10k"), "rat", 5)
    project = _project()
    apply_solder_delta(project, set(), {"R1"}, inv)
    item = inv.get(inventory_key("resistor", "10k"))
    assert item.on_hand == 19
    assert item.reservations == {"rat": 5}


def test_solder_with_zero_stock_goes_negative_with_warning(inv: InventoryStore) -> None:
    """Soldering a part you didn't have logged drops on_hand below zero so
    the deficit is visible — physical bench is the source of truth."""
    inv.upsert(kind="resistor", value_norm="10k", on_hand=0)
    project = _project()
    delta = apply_solder_delta(project, set(), {"R1"}, inv)
    # Full quantity comes off, even though stock was 0.
    assert delta.consumed == [(inventory_key("resistor", "10k"), 1)]
    assert any("deficit" in w or "order more" in w for w in delta.warnings)
    assert inv.get(inventory_key("resistor", "10k")).on_hand == -1


def test_solder_pushing_stock_negative(inv: InventoryStore) -> None:
    """If you have 1 left and solder 3, you should see -2, not clamp at 0."""
    inv.upsert(kind="resistor", value_norm="10k", on_hand=1)
    project = Project(
        slug="muff",
        name="Muff",
        bom=[BOMItem(location="R1", value="10k", type="Resistor", quantity=3)],
    )
    delta = apply_solder_delta(project, set(), {"R1"}, inv)
    assert delta.consumed == [(inventory_key("resistor", "10k"), 3)]
    assert inv.get(inventory_key("resistor", "10k")).on_hand == -2


def test_solder_skips_parts_with_no_inventory_row(inv: InventoryStore) -> None:
    project = _project()
    delta = apply_solder_delta(project, set(), {"R1"}, inv)
    assert delta.consumed == []
    assert delta.warnings == []


def test_solder_skips_other_classified_rows(inv: InventoryStore) -> None:
    """Enclosure / hardware BOM rows shouldn't try to consume inventory."""
    project = _project()
    # ENCL classifies as 'pot' (alpha-only location) or 'other'; either way
    # there's no enclosure inventory item so consumption silently skips.
    delta = apply_solder_delta(project, set(), {"ENCL"}, inv)
    assert delta.consumed == []


def test_quantity_greater_than_one_decrements_by_quantity(inv: InventoryStore) -> None:
    inv.upsert(kind="resistor", value_norm="10k", on_hand=20)
    project = Project(
        slug="muff",
        name="Muff",
        bom=[BOMItem(location="R1", value="10k", type="Resistor", quantity=3)],
    )
    apply_solder_delta(project, set(), {"R1"}, inv)
    assert inv.get(inventory_key("resistor", "10k")).on_hand == 17


def test_idempotent_when_no_delta(inv: InventoryStore) -> None:
    inv.upsert(kind="resistor", value_norm="10k", on_hand=20)
    project = _project()
    apply_solder_delta(project, set(), {"R1"}, inv)
    # Same set passed again — nothing should happen
    delta = apply_solder_delta(project, {"R1"}, {"R1"}, inv)
    assert delta.consumed == []
    assert delta.restored == []
    assert inv.get(inventory_key("resistor", "10k")).on_hand == 19
