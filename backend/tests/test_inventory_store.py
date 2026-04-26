"""Owned-stock inventory store: CRUD, reservations, consumption, migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pedal_bench.core.inventory_store import InventoryStore
from pedal_bench.core.models import InventoryItem, inventory_key


def _make_store(tmp_path: Path) -> InventoryStore:
    return InventoryStore(tmp_path / "inventory.json")


def test_upsert_creates_and_updates(tmp_path: Path) -> None:
    inv = _make_store(tmp_path)
    item = inv.upsert(kind="resistor", value_norm="10k", on_hand=50, display_value="10K")
    assert item.key == "resistor::10k"
    assert item.on_hand == 50

    # Update preserves reservations and missing fields
    inv.set_reservation(item.key, "big-muff", 5)
    updated = inv.upsert(kind="resistor", value_norm="10k", on_hand=80)
    assert updated.on_hand == 80
    assert updated.reservations == {"big-muff": 5}
    assert updated.display_value == "10K"  # preserved


def test_set_reservation_caps_at_available(tmp_path: Path) -> None:
    inv = _make_store(tmp_path)
    item = inv.upsert(kind="ic", value_norm="TL072", on_hand=4)
    inv.set_reservation(item.key, "alpha", 3)
    # Other-project reservation pinches available for beta
    with pytest.raises(ValueError):
        inv.set_reservation(item.key, "beta", 2)
    inv.set_reservation(item.key, "beta", 1)
    refreshed = inv.get(item.key)
    assert refreshed.reservations == {"alpha": 3, "beta": 1}
    assert refreshed.available == 0


def test_set_reservation_zero_clears(tmp_path: Path) -> None:
    inv = _make_store(tmp_path)
    item = inv.upsert(kind="ic", value_norm="TL072", on_hand=4)
    inv.set_reservation(item.key, "alpha", 2)
    inv.set_reservation(item.key, "alpha", 0)
    assert inv.get(item.key).reservations == {}


def test_consume_reservations_decrements_on_hand(tmp_path: Path) -> None:
    inv = _make_store(tmp_path)
    a = inv.upsert(kind="resistor", value_norm="10k", on_hand=50)
    b = inv.upsert(kind="ic", value_norm="TL072", on_hand=4)
    inv.set_reservation(a.key, "muff", 7)
    inv.set_reservation(b.key, "muff", 2)
    inv.set_reservation(b.key, "rat", 1)

    consumed = inv.consume_reservations("muff")
    assert dict(consumed) == {a.key: 7, b.key: 2}
    assert inv.get(a.key).on_hand == 43
    assert inv.get(a.key).reservations == {}
    assert inv.get(b.key).on_hand == 2
    assert inv.get(b.key).reservations == {"rat": 1}  # other project untouched


def test_clear_reservations_drops_one_project(tmp_path: Path) -> None:
    inv = _make_store(tmp_path)
    a = inv.upsert(kind="resistor", value_norm="10k", on_hand=50)
    inv.set_reservation(a.key, "muff", 7)
    inv.set_reservation(a.key, "rat", 3)
    inv.clear_reservations("muff")
    assert inv.get(a.key).reservations == {"rat": 3}
    assert inv.get(a.key).on_hand == 50  # not consumed


def test_patch_on_hand_below_reservations_blocked_at_route_level() -> None:
    # Store-level adjust_on_hand only blocks negatives, not below-reservation
    # drops — that policy lives in the route. Document the split here.
    item = InventoryItem(key="x", kind="ic", value_norm="A", on_hand=5)
    assert item.available == 5


def test_remove(tmp_path: Path) -> None:
    inv = _make_store(tmp_path)
    item = inv.upsert(kind="resistor", value_norm="10k", on_hand=50)
    inv.remove(item.key)
    assert inv.get(item.key) is None


def test_persistence_roundtrip(tmp_path: Path) -> None:
    inv = _make_store(tmp_path)
    item = inv.upsert(
        kind="ic", value_norm="TL072", on_hand=4,
        display_value="TL072", supplier="Tayda", unit_cost_usd=0.42,
        notes="DIP-8",
    )
    inv.set_reservation(item.key, "muff", 1)

    inv2 = InventoryStore(inv.path)
    inv2.load()
    reloaded = inv2.get(item.key)
    assert reloaded is not None
    assert reloaded.on_hand == 4
    assert reloaded.reservations == {"muff": 1}
    assert reloaded.supplier == "Tayda"
    assert reloaded.unit_cost_usd == 0.42
    assert reloaded.notes == "DIP-8"


def test_legacy_per_value_migration(tmp_path: Path) -> None:
    """Old inventory.json with `tracking: per_value` loads without exploding."""
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({
        "items": {
            "resistor:1/4W:10k": {
                "tracking": "per_value",
                "on_hand": 25,
                "supplier": "Tayda",
            }
        }
    }))
    inv = InventoryStore(path)
    inv.load()
    items = inv.items()
    assert len(items) == 1
    assert items[0].on_hand == 25
    # Key is canonicalized to kind::value_norm
    assert items[0].key == inventory_key(items[0].kind, items[0].value_norm)


def test_legacy_bucket_migrates_to_zero_with_note(tmp_path: Path) -> None:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({
        "items": {
            "bucket:resistor:1/4W": {
                "tracking": "bucket",
                "on_hand": "plenty",
            }
        }
    }))
    inv = InventoryStore(path)
    inv.load()
    items = inv.items()
    assert len(items) == 1
    assert items[0].on_hand == 0
    assert "plenty" in items[0].notes
