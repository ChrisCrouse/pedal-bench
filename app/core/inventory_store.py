"""Global inventory — a single JSON file at the repo root.

Schema:
    {
      "items": {
        "<key>": { InventoryItem dict, minus the redundant key field }
        ...
      }
    }
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

from .models import InventoryItem


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
        for key, entry in raw.items():
            item_dict = dict(entry)
            item_dict.setdefault("key", key)
            items[key] = InventoryItem.from_dict(item_dict)
        self._items = items
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def get(self, key: str) -> InventoryItem | None:
        self._ensure_loaded()
        return self._items.get(key)

    def put(self, item: InventoryItem) -> None:
        self._ensure_loaded()
        self._items[item.key] = item

    def remove(self, key: str) -> None:
        self._ensure_loaded()
        self._items.pop(key, None)

    def __iter__(self) -> Iterator[InventoryItem]:
        self._ensure_loaded()
        return iter(self._items.values())

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._items)

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
