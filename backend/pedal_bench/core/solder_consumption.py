"""Inventory bookkeeping driven by solder-progress changes.

When the user marks a refdes soldered on the bench, the corresponding part
should come off owned-stock — that's what the user means when they say "I
just used this." When they uncheck a refdes, the part goes back. This module
diffs the old vs new soldered set and applies the resulting consumption.

Design choices:
- We consume from the project's own reservation first (decrementing both
  reservation and on_hand together) so `reserved ≤ on_hand` stays true.
- If the part has no inventory row, we skip silently — enclosure hardware
  and BOM rows that classify as 'other' won't match anything, and that's
  fine. The bench still records the solder regardless.
- If on_hand is 0, we don't block the solder mark. The physical bench is
  the source of truth; the database is best-effort. This is documented
  via the returned warnings list so the UI can flash a hint.
"""

from __future__ import annotations

from dataclasses import dataclass

from .inventory_index import classify, normalize_value
from .inventory_store import InventoryStore
from .models import BOMItem, Project, inventory_key


@dataclass
class ConsumptionResult:
    consumed: list[tuple[str, int]]   # (key, qty) pairs decremented
    restored: list[tuple[str, int]]   # (key, qty) pairs incremented (unsolder)
    warnings: list[str]               # human-readable, e.g. "10k stock was 0"


def _bom_part_key(item: BOMItem) -> tuple[str, str, int] | None:
    """Return (kind, value_norm, quantity) for a BOM row, or None if it's
    not trackable (enclosure parts, mystery rows)."""
    kind = classify(item.location, item.type)
    if kind == "other":
        return None
    value_norm = normalize_value(item.value, kind)
    if not value_norm:
        return None
    return kind, value_norm, max(1, int(item.quantity or 1))


def apply_solder_delta(
    project: Project,
    old_soldered: set[str],
    new_soldered: set[str],
    inventory: InventoryStore,
) -> ConsumptionResult:
    """Compute the diff between two soldered-location sets and update stock.

    Newly-soldered locations decrement inventory; newly-un-soldered locations
    restore it. Saves the inventory store on each mutation (atomic JSON write).
    The caller is responsible for persisting the project itself.
    """
    consumed: list[tuple[str, int]] = []
    restored: list[tuple[str, int]] = []
    warnings: list[str] = []

    by_loc = {b.location: b for b in project.bom}

    added = new_soldered - old_soldered
    removed = old_soldered - new_soldered

    for loc in added:
        bom = by_loc.get(loc)
        if bom is None:
            continue
        parsed = _bom_part_key(bom)
        if parsed is None:
            continue
        kind, value_norm, qty = parsed
        key = inventory_key(kind, value_norm)
        item = inventory.get(key)
        if item is None:
            continue  # part not in personal stock — silently ignore

        # Consume from this project's own reservation first so the invariant
        # `reserved ≤ on_hand` keeps holding. Anything left over comes off
        # raw on_hand. We allow on_hand to go negative as honest tracking:
        # if you solder a part you didn't have logged, you owe inventory N
        # parts until you restock. Surface a warning either way so the UI
        # can flash a hint.
        own_reserved = item.reservations.get(project.slug, 0)
        from_reservation = min(qty, own_reserved)
        from_stock = qty - from_reservation

        if from_reservation > 0:
            item.reservations[project.slug] = own_reserved - from_reservation
            if item.reservations[project.slug] == 0:
                del item.reservations[project.slug]
        before = item.on_hand
        item.on_hand -= (from_reservation + from_stock)
        if before > 0 and item.on_hand <= 0:
            # Just crossed zero — alert the user once on transition.
            warnings.append(
                f"{bom.value} ({loc}): stock now {item.on_hand} — order more"
            )
        elif item.on_hand < 0 and before <= 0:
            # Already in deficit, going deeper — quieter but still flagged.
            warnings.append(
                f"{bom.value} ({loc}): stock at {item.on_hand} (deficit)"
            )
        inventory.put(item)  # persists
        consumed.append((key, from_reservation + from_stock))

    for loc in removed:
        bom = by_loc.get(loc)
        if bom is None:
            continue
        parsed = _bom_part_key(bom)
        if parsed is None:
            continue
        kind, value_norm, qty = parsed
        key = inventory_key(kind, value_norm)
        item = inventory.get(key)
        if item is None:
            # No row to restore to. Skip — the user may have removed it from
            # inventory entirely, in which case we don't want to recreate it.
            continue
        item.on_hand += qty
        inventory.put(item)
        restored.append((key, qty))

    return ConsumptionResult(consumed=consumed, restored=restored, warnings=warnings)


__all__ = ["ConsumptionResult", "apply_solder_delta"]
