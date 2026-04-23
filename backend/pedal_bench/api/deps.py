"""FastAPI dependency providers.

Keeps request-scoped wiring explicit and mockable. Singletons (catalog,
stores) are cached at module load.
"""

from __future__ import annotations

import json
from functools import lru_cache

from fastapi import Header

from pedal_bench import config
from pedal_bench.core.hints import HintLibrary
from pedal_bench.core.inventory_store import InventoryStore
from pedal_bench.core.models import Enclosure
from pedal_bench.core.project_store import ProjectStore


def get_request_api_key(
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
) -> str | None:
    """Per-request Anthropic API key from the browser (BYOK).

    Frontend's apiKey module attaches X-Anthropic-Key on every fetch when
    the user has set one in Settings. None means "no header sent" — the AI
    modules will fall back to ANTHROPIC_API_KEY env var (self-host pattern).
    """
    return (x_anthropic_key or "").strip() or None


def get_tayda_token(
    x_tayda_token: str | None = Header(default=None, alias="X-Tayda-Token"),
) -> str | None:
    """Per-request Tayda Kits API token (second BYOK axis, mirrors the
    Anthropic-key pattern). Only attached to the Tayda push route; the
    frontend doesn't send it on unrelated calls. None means no token —
    the Tayda push route responds with 400 + a nudge to Settings."""
    return (x_tayda_token or "").strip() or None


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
