"""Global inventory — a single JSON file at the repo root.

Schema:
    {
      "items": {
        "<key>": { InventoryItem dict, minus the redundant key field }
        ...
      }
    }

Persistence is atomic: temp file in the same directory, then os.replace.
Mutations call save() automatically so callers don't have to remember.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

from .models import InventoryItem, inventory_key


class InventoryStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._items: dict[str, InventoryItem] = {}
        self._loaded = False

    def load(self) -> None:
        if not self.path.exists():
            self._items = {}
            self._loaded = True
            return
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        raw = data.get("items", {})
        items: dict[str, InventoryItem] = {}
        migrated = False
        for key, entry in raw.items():
            item_dict = dict(entry)
            item_dict.setdefault("key", key)
            # Detect legacy schema so we resave once after load.
            if "tracking" in item_dict:
                migrated = True
            item = InventoryItem.from_dict(item_dict)
            # Re-key by canonical (kind, value_norm) so legacy keys collapse
            # onto the new format. If two legacy keys collide, sum their
            # on_hand and merge reservations.
            canonical = inventory_key(item.kind, item.value_norm) if item.kind and item.value_norm else item.key
            if canonical in items:
                existing = items[canonical]
                existing.on_hand += item.on_hand
                for slug, qty in item.reservations.items():
                    existing.reservations[slug] = existing.reservations.get(slug, 0) + qty
                migrated = True
            else:
                item.key = canonical
                items[canonical] = item
        self._items = items
        self._loaded = True
        if migrated:
            self.save()

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def get(self, key: str) -> InventoryItem | None:
        self._ensure_loaded()
        return self._items.get(key)

    def get_by_kind_value(self, kind: str, value_norm: str) -> InventoryItem | None:
        return self.get(inventory_key(kind, value_norm))

    def put(self, item: InventoryItem) -> None:
        self._ensure_loaded()
        self._items[item.key] = item
        self.save()

    def upsert(
        self,
        *,
        kind: str,
        value_norm: str,
        on_hand: int,
        display_value: str = "",
        supplier: str | None = None,
        unit_cost_usd: float | None = None,
        notes: str = "",
    ) -> InventoryItem:
        """Create or update an item by (kind, value_norm). Preserves existing
        reservations on update."""
        self._ensure_loaded()
        key = inventory_key(kind, value_norm)
        existing = self._items.get(key)
        reservations = existing.reservations if existing else {}
        item = InventoryItem(
            key=key,
            kind=kind,
            value_norm=value_norm,
            on_hand=on_hand,
            reservations=reservations,
            display_value=display_value or (existing.display_value if existing else ""),
            supplier=supplier if supplier is not None else (existing.supplier if existing else None),
            unit_cost_usd=unit_cost_usd if unit_cost_usd is not None else (existing.unit_cost_usd if existing else None),
            notes=notes if notes else (existing.notes if existing else ""),
        )
        self._items[key] = item
        self.save()
        return item

    def remove(self, key: str) -> None:
        self._ensure_loaded()
        if self._items.pop(key, None) is not None:
            self.save()

    def adjust_on_hand(self, key: str, delta: int) -> InventoryItem:
        """Add `delta` (which may be negative) to on_hand. Allows the result
        to go negative — see InventoryItem.__post_init__ for rationale."""
        self._ensure_loaded()
        item = self._items.get(key)
        if item is None:
            raise KeyError(key)
        item.on_hand = item.on_hand + delta
        self.save()
        return item

    def set_reservation(self, key: str, slug: str, qty: int) -> InventoryItem:
        """Set the reservation for `slug` on this item. Caps at available + own
        existing reservation; raises if even that's insufficient. qty=0 clears.
        """
        self._ensure_loaded()
        item = self._items.get(key)
        if item is None:
            raise KeyError(key)
        if qty < 0:
            raise ValueError(f"qty must be >= 0, got {qty}")
        own_existing = item.reservations.get(slug, 0)
        # Reservations elsewhere cannot be touched.
        reserved_elsewhere = item.reserved_total - own_existing
        max_for_this_slug = item.on_hand - reserved_elsewhere
        if qty > max_for_this_slug:
            raise ValueError(
                f"cannot reserve {qty} of {key!r} for {slug!r}: "
                f"only {max_for_this_slug} available "
                f"(on_hand={item.on_hand}, reserved_elsewhere={reserved_elsewhere})"
            )
        if qty == 0:
            item.reservations.pop(slug, None)
        else:
            item.reservations[slug] = qty
        self.save()
        return item

    def clear_reservations(self, slug: str) -> int:
        """Drop all reservations belonging to `slug`. Returns how many items
        were touched."""
        self._ensure_loaded()
        touched = 0
        for item in self._items.values():
            if item.reservations.pop(slug, None) is not None:
                touched += 1
        if touched:
            self.save()
        return touched

    def consume_reservations(self, slug: str) -> list[tuple[str, int]]:
        """Subtract every reservation for `slug` from its item's on_hand,
        clear those reservations, and return [(key, consumed_qty), …].

        Used when the user marks a project built — converts "promised" into
        "spent". If a reservation somehow exceeds on_hand (shouldn't happen
        since set_reservation clamps), we cap at on_hand and warn via notes.
        """
        self._ensure_loaded()
        consumed: list[tuple[str, int]] = []
        for item in self._items.values():
            qty = item.reservations.pop(slug, None)
            if qty is None or qty == 0:
                continue
            actual = min(qty, item.on_hand)
            item.on_hand -= actual
            consumed.append((item.key, actual))
        if consumed:
            self.save()
        return consumed

    def __iter__(self) -> Iterator[InventoryItem]:
        self._ensure_loaded()
        return iter(self._items.values())

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._items)

    def items(self) -> list[InventoryItem]:
        self._ensure_loaded()
        return list(self._items.values())

    def save(self) -> None:
        self._ensure_loaded()
        payload = {
            "items": {
                key: {k: v for k, v in item.to_dict().items() if k != "key"}
                for key, item in sorted(self._items.items())
            }
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)


__all__ = ["InventoryStore"]
