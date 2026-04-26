"""/projects/{slug}/bom and /progress — BOM + build progress mutations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pedal_bench.api.deps import get_inventory_store, get_project_store
from pedal_bench.api.schemas import BOMItemIO, BuildProgressIO, ProgressUpdateOut
from pedal_bench.core.inventory_store import InventoryStore
from pedal_bench.core.models import BOMItem, BuildProgress, is_polarity_sensitive
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.core.solder_consumption import apply_solder_delta
from pydantic import BaseModel

router = APIRouter(prefix="/projects/{slug}", tags=["bom", "progress"])


class BOMReplaceIn(BaseModel):
    bom: list[BOMItemIO]


@router.put("/bom", response_model=list[BOMItemIO])
def replace_bom(
    slug: str,
    payload: BOMReplaceIn,
    store: ProjectStore = Depends(get_project_store),
) -> list[BOMItemIO]:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    project = store.load(slug)
    project.bom = [
        BOMItem(
            location=b.location,
            value=b.value,
            type=b.type,
            notes=b.notes,
            quantity=b.quantity,
            polarity_sensitive=is_polarity_sensitive(b.type),
            orientation_hint=b.orientation_hint,
        )
        for b in payload.bom
    ]
    store.save(project)
    return [BOMItemIO(**b.to_dict()) for b in project.bom]


@router.put("/progress", response_model=ProgressUpdateOut)
def replace_progress(
    slug: str,
    payload: BuildProgressIO,
    store: ProjectStore = Depends(get_project_store),
    inv: InventoryStore = Depends(get_inventory_store),
) -> ProgressUpdateOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    project = store.load(slug)
    old_soldered = set(project.progress.soldered_locations)
    new_soldered = set(payload.soldered_locations)

    # Apply inventory consumption based on what just got toggled. This
    # decrements stock for newly-soldered refdes and restores stock for
    # ones that were unchecked.
    delta = apply_solder_delta(project, old_soldered, new_soldered, inv)

    project.progress = BuildProgress(
        soldered_locations=new_soldered,
        current_phase=payload.current_phase,
        phase_notes=dict(payload.phase_notes),
    )
    store.save(project)
    return ProgressUpdateOut(
        progress=BuildProgressIO(**project.progress.to_dict()),
        consumed=delta.consumed,
        restored=delta.restored,
        warnings=delta.warnings,
    )
