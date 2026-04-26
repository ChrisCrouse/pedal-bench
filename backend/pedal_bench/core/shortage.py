"""Shortage computation: BOM needs minus owned inventory.

Two views:
- Per-project: "to finish THIS pedal given my current stock and what's already
  reserved for other builds, what do I still need to buy?"
- Global:    "to finish all my active projects, what do I still need to buy?"

Both use the same canonical join key — `(kind, value_norm)` derived from the
classifier and value normalizer in `inventory_index`. Inventory rows whose
key doesn't match any BOM are simply not surfaced in the shortage views; they
remain visible on the Owned tab.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .inventory_index import classify, normalize_value
from .inventory_store import InventoryStore
from .models import Project, inventory_key
from .project_store import ProjectStore


@dataclass
class ShortageRow:
    kind: str
    value_norm: str
    display_value: str       # most representative original BOM value
    type_hint: str           # one BOM `type` string for context (e.g. "1/4W Resistor")
    needed: int
    on_hand: int
    reserved_for_others: int  # reservations belonging to other projects
    reserved_for_self: int    # reservations belonging to THIS project (per-project view only)
    available: int            # on_hand - reservations to other projects (per-project view)
    shortfall: int            # max(0, needed - available)
    unit_cost_usd: float | None
    supplier: str | None
    needed_by: list[str]      # project slugs (global view); for per-project view, [slug]


def _aggregate_bom(project: Project) -> dict[tuple[str, str], tuple[int, str, str]]:
    """Group a project's BOM into {(kind, value_norm): (qty, display_value, type_hint)}.

    Skips rows that classify as `other` or have an empty normalized value —
    these are unmappable to inventory (e.g. enclosures, hardware).
    """
    out: dict[tuple[str, str], tuple[int, str, str]] = {}
    for item in project.bom:
        kind = classify(item.location, item.type)
        if kind == "other":
            continue
        value_norm = normalize_value(item.value, kind)
        if not value_norm:
            continue
        key = (kind, value_norm)
        prev_qty, prev_display, prev_type = out.get(key, (0, "", ""))
        out[key] = (
            prev_qty + int(item.quantity or 1),
            prev_display or item.value,
            prev_type or item.type,
        )
    return out


def compute_project_shortage(
    project: Project, inventory: InventoryStore
) -> list[ShortageRow]:
    """Per-project shortage view.

    `available` here counts on_hand minus reservations held by *other*
    projects — own reservations don't reduce what this project can use.
    """
    needs = _aggregate_bom(project)
    rows: list[ShortageRow] = []
    for (kind, value_norm), (needed, display, type_hint) in needs.items():
        item = inventory.get(inventory_key(kind, value_norm))
        if item is None:
            on_hand = 0
            reserved_others = 0
            reserved_self = 0
            unit_cost = None
            supplier = None
        else:
            on_hand = item.on_hand
            reserved_self = item.reservations.get(project.slug, 0)
            reserved_others = item.reserved_total - reserved_self
            unit_cost = item.unit_cost_usd
            supplier = item.supplier
        available = max(0, on_hand - reserved_others)
        shortfall = max(0, needed - available)
        rows.append(
            ShortageRow(
                kind=kind,
                value_norm=value_norm,
                display_value=display,
                type_hint=type_hint,
                needed=needed,
                on_hand=on_hand,
                reserved_for_others=reserved_others,
                reserved_for_self=reserved_self,
                available=available,
                shortfall=shortfall,
                unit_cost_usd=unit_cost,
                supplier=supplier,
                needed_by=[project.slug],
            )
        )
    rows.sort(key=lambda r: (-r.shortfall, r.kind, r.value_norm))
    return rows


def compute_global_shortage(
    project_store: ProjectStore, inventory: InventoryStore
) -> list[ShortageRow]:
    """Aggregate needs across all `active` projects, subtract inventory.

    Reservations are intentionally ignored here — every active project's full
    BOM is summed, so reservations would double-count what's already accounted
    for in the totals. The global list answers "if I started fresh and bought
    only what I'm missing, what's the order?"
    """
    totals: dict[tuple[str, str], int] = defaultdict(int)
    displays: dict[tuple[str, str], str] = {}
    type_hints: dict[tuple[str, str], str] = {}
    needed_by: dict[tuple[str, str], list[str]] = defaultdict(list)

    for project in project_store.iter_projects():
        if not project.active:
            continue
        for (kind, value_norm), (qty, display, type_hint) in _aggregate_bom(project).items():
            key = (kind, value_norm)
            totals[key] += qty
            displays.setdefault(key, display)
            type_hints.setdefault(key, type_hint)
            needed_by[key].append(project.slug)

    rows: list[ShortageRow] = []
    for (kind, value_norm), needed in totals.items():
        item = inventory.get(inventory_key(kind, value_norm))
        on_hand = item.on_hand if item else 0
        unit_cost = item.unit_cost_usd if item else None
        supplier = item.supplier if item else None
        shortfall = max(0, needed - on_hand)
        rows.append(
            ShortageRow(
                kind=kind,
                value_norm=value_norm,
                display_value=displays[(kind, value_norm)],
                type_hint=type_hints[(kind, value_norm)],
                needed=needed,
                on_hand=on_hand,
                reserved_for_others=0,
                reserved_for_self=0,
                available=on_hand,
                shortfall=shortfall,
                unit_cost_usd=unit_cost,
                supplier=supplier,
                needed_by=needed_by[(kind, value_norm)],
            )
        )
    rows.sort(key=lambda r: (-r.shortfall, r.kind, r.value_norm))
    return rows


__all__ = ["ShortageRow", "compute_project_shortage", "compute_global_shortage"]
