"""Static price oracle — fallback unit costs for parts the user hasn't
priced themselves yet.

Lookup chain at every call site (see core/shortage.py):
    1. InventoryItem.unit_cost_usd   — user's actual paid price (wins always)
    2. price_oracle.lookup(...)      — this module
    3. None                          — UI shows "—"

Prices live in `pedal_bench/data/default_prices.json`, calibrated against
typical Tayda Electronics retail. Numbers from the oracle are flagged in
ShortageRow.unit_cost_estimated so the UI can render them with a "~"
prefix and an "estimated" tooltip — they should never be confused with
prices the user actually logged.

Refresh strategy: rewrite the JSON once a year against current Tayda
listings. Bias slightly conservative-high so cost-to-finish doesn't lull
you into ordering before checking the cart total.
"""

from __future__ import annotations

import json
from typing import Any

from pedal_bench import config


_PRICES: dict[str, Any] | None = None
_PATH = config.DATA_DIR / "default_prices.json"


def _load() -> dict[str, Any]:
    global _PRICES
    if _PRICES is None:
        if not _PATH.exists():
            _PRICES = {}
        else:
            with open(_PATH, encoding="utf-8") as fh:
                _PRICES = json.load(fh)
    return _PRICES


def lookup(kind: str, value_norm: str) -> float | None:
    """Return an estimated unit price in USD, or None when the oracle has
    nothing useful to say about this part.

    Order:
      1. Exact `(kind, value_norm)` hit in the values table
      2. The kind's default price (if defined)
      3. None
    """
    if not kind or not value_norm:
        return None
    table = _load()
    by_kind = table.get(kind)
    if not by_kind or not isinstance(by_kind, dict):
        return None
    values = by_kind.get("values", {})
    if value_norm in values:
        v = values[value_norm]
        return float(v) if v is not None else None
    default = by_kind.get("default")
    return float(default) if default is not None else None


def reload() -> None:
    """Drop the in-memory cache so the next lookup re-reads the JSON.
    Used by tests that rewrite the data file mid-run."""
    global _PRICES
    _PRICES = None


__all__ = ["lookup", "reload"]
