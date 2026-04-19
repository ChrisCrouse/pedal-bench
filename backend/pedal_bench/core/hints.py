"""Load orientation hints for bench mode.

Two sources, in priority order:
  1. `pedals.<slug>.<location>` \u2014 a per-pedal override from the seed file.
  2. `defaults` \u2014 a keyword \u2192 hint map, matched against BOMItem.type.

The BOMItem's own `orientation_hint` field (set via the bench-view UI)
always wins over both of these; the loader just supplies fallbacks.
"""

from __future__ import annotations

import json
from pathlib import Path


class HintLibrary:
    """Read-only view of orientation_hints.json."""

    def __init__(
        self,
        defaults: dict[str, str],
        pedals: dict[str, dict[str, str]],
    ) -> None:
        # Sort default keys longest-first so "schottky diode" beats "diode"
        # on a type containing both words.
        self._defaults: list[tuple[str, str]] = sorted(
            ((k.lower(), v) for k, v in defaults.items()),
            key=lambda kv: -len(kv[0]),
        )
        self._pedals = {
            slug: {loc: hint for loc, hint in entries.items() if not loc.startswith("_")}
            for slug, entries in pedals.items()
            if not slug.startswith("_")
        }

    @classmethod
    def load(cls, path: Path | str) -> "HintLibrary":
        path = Path(path)
        if not path.exists():
            return cls({}, {})
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(
            defaults=data.get("defaults", {}),
            pedals=data.get("pedals", {}),
        )

    def for_item(self, slug: str, location: str, bom_type: str) -> str | None:
        """Return the best fallback hint for a polarity-sensitive BOM row.

        Falls back through per-pedal overrides → keyword-matched defaults → None.
        """
        pedal_entries = self._pedals.get(slug, {})
        if location in pedal_entries:
            return pedal_entries[location]
        t = bom_type.lower()
        for keyword, hint in self._defaults:
            if keyword in t:
                return hint
        return None


__all__ = ["HintLibrary"]
