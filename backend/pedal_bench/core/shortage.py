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
from .price_oracle import lookup as price_lookup
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
    # True when unit_cost_usd came from the static price oracle rather than
    # the user's own InventoryItem.unit_cost_usd. UI surfaces this as a "~"
    # prefix and an "estimated" tooltip so user-set prices and oracle
    # estimates never get visually confused.
    unit_cost_estimated: bool
    supplier: str | None
    needed_by: list[str]      # project slugs (global view); for per-project view, [slug]
    # Per-project quantity contribution. Drives cost-split rollups like
    # "which build is driving this $X order" — splitting by count alone
    # would misattribute when one project wants 10× and another wants 1×.
    needed_by_qty: dict[str, int]


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
        # Oracle fallback: when the user hasn't logged a unit cost on the
        # inventory item, drop in a ballpark estimate so cost-to-finish has
        # something to work with. The flag tells the UI to render a "~".
        unit_cost_estimated = False
        if unit_cost is None:
            estimate = price_lookup(kind, value_norm)
            if estimate is not None:
                unit_cost = estimate
                unit_cost_estimated = True
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
                unit_cost_estimated=unit_cost_estimated,
                supplier=supplier,
                needed_by=[project.slug],
                needed_by_qty={project.slug: needed},
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
    # Quantity contribution per slug — drives accurate per-project cost
    # rollups on the shopping list.
    needed_by_qty: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)

    for project in project_store.iter_projects():
        if not project.active:
            continue
        for (kind, value_norm), (qty, display, type_hint) in _aggregate_bom(project).items():
            key = (kind, value_norm)
            totals[key] += qty
            displays.setdefault(key, display)
            type_hints.setdefault(key, type_hint)
            needed_by[key].append(project.slug)
            needed_by_qty[key][project.slug] = (
                needed_by_qty[key].get(project.slug, 0) + qty
            )

    rows: list[ShortageRow] = []
    for (kind, value_norm), needed in totals.items():
        item = inventory.get(inventory_key(kind, value_norm))
        on_hand = item.on_hand if item else 0
        unit_cost = item.unit_cost_usd if item else None
        supplier = item.supplier if item else None
        # Oracle fallback identical to compute_project_shortage — keep
        # global-view costs in lockstep with per-project view.
        unit_cost_estimated = False
        if unit_cost is None:
            estimate = price_lookup(kind, value_norm)
            if estimate is not None:
                unit_cost = estimate
                unit_cost_estimated = True
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
                unit_cost_estimated=unit_cost_estimated,
                supplier=supplier,
                needed_by=needed_by[(kind, value_norm)],
                needed_by_qty=needed_by_qty[(kind, value_norm)],
            )
        )
    rows.sort(key=lambda r: (-r.shortfall, r.kind, r.value_norm))
    return rows


def count_buildable_projects(
    project_store: ProjectStore, inventory: InventoryStore
) -> tuple[int, int]:
    """Greedy buildability count across active projects.

    Returns (buildable_count, total_active_count).

    Sorts active projects by updated_at desc, then walks the list deducting
    each project's needs from a running copy of inventory on-hand. A project
    counts as buildable if every required (kind, value_norm) has enough free
    stock at the moment it's evaluated; if so, its needs are subtracted before
    the next project is evaluated.

    This prevents the naive per-project-independence bug where two projects
    that each need the last 4×100n caps would both report "buildable" — only
    one of them actually can be, given shared stock.

    Allocation order is updated_at desc so the most recently touched project
    gets first dibs. That's a hobbyist heuristic, not an optimal solver — the
    knapsack version of "max projects buildable" isn't worth it at this scale.
    """
    active = [p for p in project_store.iter_projects() if p.active]
    total_active = len(active)
    if total_active == 0:
        return (0, 0)

    # Sort: most recently updated first. Stable on ties.
    active.sort(key=lambda p: p.updated_at, reverse=True)

    # Running on-hand: copy of inventory we mutate locally. Never touches
    # the real InventoryStore.
    running: dict[str, int] = {}
    for item in inventory.items():
        running[item.key] = item.on_hand

    buildable = 0
    for project in active:
        needs = _aggregate_bom(project)
        # Two-pass: first verify every need is satisfiable, then deduct.
        # Without the verify pass we'd partially deduct for a project that
        # turns out to be unbuildable and starve the next one.
        ok = True
        for (kind, value_norm), (qty, _, _) in needs.items():
            key = inventory_key(kind, value_norm)
            if running.get(key, 0) < qty:
                ok = False
                break
        if not ok:
            continue
        for (kind, value_norm), (qty, _, _) in needs.items():
            key = inventory_key(kind, value_norm)
            running[key] = running.get(key, 0) - qty
        buildable += 1

    return (buildable, total_active)


__all__ = [
    "ShortageRow",
    "compute_project_shortage",
    "compute_global_shortage",
    "count_buildable_projects",
]
