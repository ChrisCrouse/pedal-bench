"""Cross-project inventory queries backed by SQLite index.

Index is rebuilt on every request — projects are small enough that staleness
isn't worth solving with cache invalidation. If this gets slow with hundreds
of projects, we'll add a watchdog or hash-based skip.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pedal_bench import config
from pedal_bench.api.deps import get_project_store
from pedal_bench.core.inventory_index import InventoryIndex
from pedal_bench.core.project_store import ProjectStore

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _index(store: ProjectStore) -> InventoryIndex:
    idx = InventoryIndex(config.REPO_ROOT / "pedal_bench_index.sqlite", store)
    idx.refresh()
    return idx


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
