"""FastAPI dependency providers.

Keeps request-scoped wiring explicit and mockable. Singletons (catalog,
stores) are cached at module load.
"""

from __future__ import annotations

import json
from functools import lru_cache

from pedal_bench import config
from pedal_bench.core.hints import HintLibrary
from pedal_bench.core.inventory_store import InventoryStore
from pedal_bench.core.models import Enclosure
from pedal_bench.core.project_store import ProjectStore


@lru_cache(maxsize=1)
def get_enclosure_catalog() -> dict[str, Enclosure]:
    with open(config.enclosures_path(), encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        key: Enclosure.from_json(key, entry)
        for key, entry in data.items()
        if not key.startswith("_")
    }


@lru_cache(maxsize=1)
def get_hint_library() -> HintLibrary:
    return HintLibrary.load(config.orientation_hints_path())


@lru_cache(maxsize=1)
def get_project_store() -> ProjectStore:
    return ProjectStore(config.PROJECTS_DIR)


@lru_cache(maxsize=1)
def get_inventory_store() -> InventoryStore:
    return InventoryStore(config.INVENTORY_FILE)
