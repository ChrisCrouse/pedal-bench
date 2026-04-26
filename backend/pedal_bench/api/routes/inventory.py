"""Inventory routes — both the cross-project BOM aggregator (read-only,
backed by the SQLite index) and the personal owned-stock store (mutable,
backed by inventory.json).

The two views complement each other:
  - `/inventory/parts*` answers "what parts are used across my projects".
  - `/inventory/items*` is the personal stock the user physically owns.
  - `/inventory/shortage` and `/projects/{slug}/shortage` join them: needed
    minus owned, minus reservations.

Index is rebuilt on every request — projects are small enough that staleness
isn't worth solving with cache invalidation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pedal_bench import config
from pedal_bench.api.deps import get_inventory_store, get_project_store
from pedal_bench.api.schemas import (
    ConsumeReservationsOut,
    InventoryItemIn,
    InventoryItemOut,
    InventoryItemPatch,
    ReservationIn,
    ShortageOut,
    ShortageRowOut,
)
from pedal_bench.core.inventory_index import (
    InventoryIndex,
    classify,
    normalize_value,
    value_magnitude,
)
from pedal_bench.core.inventory_store import InventoryStore
from pedal_bench.core.models import InventoryItem, inventory_key
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.core.shortage import (
    ShortageRow,
    compute_global_shortage,
    compute_project_shortage,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


# ---- helpers ----------------------------------------------------------------


def _index(store: ProjectStore) -> InventoryIndex:
    idx = InventoryIndex(config.REPO_ROOT / "pedal_bench_index.sqlite", store)
    idx.refresh()
    return idx


def _item_to_out(item: InventoryItem) -> InventoryItemOut:
    # Magnitude must be computed from the case-preserving display_value, not
    # value_norm — normalize_value lowercases for matching, which collapses
    # 'M' (mega) and 'm' (milli) into the same character. Sort needs them
    # distinguished: 10M = 10,000,000 ohms, not 10 milliohms.
    return InventoryItemOut(
        key=item.key,
        kind=item.kind,
        value_norm=item.value_norm,
        value_magnitude=value_magnitude(item.display_value or item.value_norm, item.kind),
        display_value=item.display_value or item.value_norm,
        on_hand=item.on_hand,
        reservations=dict(item.reservations),
        reserved_total=item.reserved_total,
        available=item.available,
        supplier=item.supplier,
        unit_cost_usd=item.unit_cost_usd,
        notes=item.notes,
    )


def _row_to_out(row: ShortageRow) -> ShortageRowOut:
    return ShortageRowOut(
        **row.__dict__,
        value_magnitude=value_magnitude(row.display_value or row.value_norm, row.kind),
    )


def _shortage_payload(rows: list[ShortageRow]) -> ShortageOut:
    cost = 0.0
    has_cost = False
    for r in rows:
        if r.unit_cost_usd is not None and r.shortfall > 0:
            cost += r.unit_cost_usd * r.shortfall
            has_cost = True
    return ShortageOut(
        rows=[_row_to_out(r) for r in rows],
        estimated_total_cost_usd=round(cost, 2) if has_cost else None,
    )


# ---- read-only cross-project aggregator (existing) --------------------------


@router.get("/stats")
def stats(store: ProjectStore = Depends(get_project_store)) -> dict:
    return _index(store).stats()


@router.get("/parts")
def parts(
    kind: str | None = None,
    search: str | None = None,
    store: ProjectStore = Depends(get_project_store),
) -> dict:
    rows = _index(store).part_totals(kind_filter=kind, search=search)
    return {
        "parts": [
            {
                "kind": r.kind,
                "value_norm": r.value_norm,
                # display_value preserves case from the original BOM entry,
                # which is what we need so 'M' (mega) doesn't get read as
                # 'm' (milli) — see _item_to_out for context.
                "value_magnitude": value_magnitude(r.display_value or r.value_norm, r.kind),
                "display_value": r.display_value,
                "total_qty": r.total_qty,
                "project_count": r.project_count,
                "project_slugs": r.project_slugs,
            }
            for r in rows
        ]
    }


@router.get("/parts/{kind}/{value_norm}/projects")
def projects_using(
    kind: str,
    value_norm: str,
    store: ProjectStore = Depends(get_project_store),
) -> dict:
    hits = _index(store).projects_using(kind, value_norm)
    if not hits:
        raise HTTPException(404, f"No projects use {kind} {value_norm!r}")
    return {
        "projects": [
            {
                "slug": h.slug,
                "name": h.name,
                "status": h.status,
                "quantity": h.quantity,
            }
            for h in hits
        ]
    }


# ---- personal owned-stock CRUD ---------------------------------------------


@router.get("/items", response_model=list[InventoryItemOut])
def list_items(
    kind: str | None = None,
    search: str | None = None,
    inv: InventoryStore = Depends(get_inventory_store),
) -> list[InventoryItemOut]:
    items = inv.items()
    if kind:
        items = [i for i in items if i.kind == kind]
    if search:
        term = search.lower()
        items = [
            i for i in items
            if term in i.value_norm.lower()
            or term in (i.display_value or "").lower()
            or term in (i.notes or "").lower()
        ]
    items.sort(key=lambda i: (i.kind, i.value_norm))
    return [_item_to_out(i) for i in items]


@router.post("/items", response_model=InventoryItemOut)
def upsert_item(
    payload: InventoryItemIn,
    inv: InventoryStore = Depends(get_inventory_store),
) -> InventoryItemOut:
    value_norm = normalize_value(payload.value, payload.kind)
    if not value_norm:
        raise HTTPException(400, "value normalizes to empty string")
    item = inv.upsert(
        kind=payload.kind,
        value_norm=value_norm,
        on_hand=payload.on_hand,
        display_value=payload.display_value or payload.value,
        supplier=payload.supplier,
        unit_cost_usd=payload.unit_cost_usd,
        notes=payload.notes,
    )
    return _item_to_out(item)


@router.patch("/items/{key:path}", response_model=InventoryItemOut)
def patch_item(
    key: str,
    payload: InventoryItemPatch,
    inv: InventoryStore = Depends(get_inventory_store),
) -> InventoryItemOut:
    item = inv.get(key)
    if item is None:
        raise HTTPException(404, f"No inventory item {key!r}")
    if payload.on_hand is not None:
        # Refuse to drop on_hand below the sum of existing reservations —
        # those are commitments to specific projects.
        if payload.on_hand < item.reserved_total:
            raise HTTPException(
                400,
                f"on_hand={payload.on_hand} is less than reserved "
                f"total={item.reserved_total}; clear reservations first",
            )
        item.on_hand = payload.on_hand
    if payload.display_value is not None:
        item.display_value = payload.display_value
    if payload.supplier is not None:
        item.supplier = payload.supplier or None
    if payload.unit_cost_usd is not None:
        item.unit_cost_usd = payload.unit_cost_usd
    if payload.notes is not None:
        item.notes = payload.notes
    inv.put(item)
    return _item_to_out(item)


@router.delete("/items/{key:path}", status_code=204)
def delete_item(
    key: str,
    inv: InventoryStore = Depends(get_inventory_store),
) -> None:
    if inv.get(key) is None:
        raise HTTPException(404, f"No inventory item {key!r}")
    inv.remove(key)


@router.post("/items/{key:path}/reserve", response_model=InventoryItemOut)
def reserve_item(
    key: str,
    payload: ReservationIn,
    inv: InventoryStore = Depends(get_inventory_store),
    store: ProjectStore = Depends(get_project_store),
) -> InventoryItemOut:
    if not store.exists(payload.slug):
        raise HTTPException(404, f"Unknown project {payload.slug!r}")
    if inv.get(key) is None:
        raise HTTPException(404, f"No inventory item {key!r}")
    try:
        item = inv.set_reservation(key, payload.slug, payload.qty)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return _item_to_out(item)


# ---- shortage views ---------------------------------------------------------


@router.get("/shortage", response_model=ShortageOut)
def global_shortage(
    inv: InventoryStore = Depends(get_inventory_store),
    store: ProjectStore = Depends(get_project_store),
) -> ShortageOut:
    rows = compute_global_shortage(store, inv)
    return _shortage_payload(rows)


# ---- helper that the projects router will call (registered on this router) -


def project_shortage_for(
    slug: str, inv: InventoryStore, store: ProjectStore
) -> ShortageOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    project = store.load(slug)
    rows = compute_project_shortage(project, inv)
    return _shortage_payload(rows)


def consume_reservations_for(
    slug: str, inv: InventoryStore, store: ProjectStore
) -> ConsumeReservationsOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    consumed = inv.consume_reservations(slug)
    return ConsumeReservationsOut(consumed=consumed)


__all__ = ["router", "project_shortage_for", "consume_reservations_for"]
