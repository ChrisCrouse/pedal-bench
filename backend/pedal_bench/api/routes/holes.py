"""/projects/{slug}/holes — list and replace the per-project hole set."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pedal_bench.api.deps import get_project_store
from pedal_bench.api.schemas import HoleIO, HolesReplace
from pedal_bench.core.models import Hole
from pedal_bench.core.project_store import ProjectStore

router = APIRouter(prefix="/projects/{slug}/holes", tags=["holes"])


@router.get("", response_model=list[HoleIO])
def list_holes(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
) -> list[HoleIO]:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    p = store.load(slug)
    return [HoleIO(**h.to_dict()) for h in p.holes]


@router.put("", response_model=list[HoleIO])
def replace_holes(
    slug: str,
    payload: HolesReplace,
    store: ProjectStore = Depends(get_project_store),
) -> list[HoleIO]:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    p = store.load(slug)
    try:
        p.holes = [
            Hole(
                side=h.side,
                x_mm=h.x_mm,
                y_mm=h.y_mm,
                diameter_mm=h.diameter_mm,
                label=h.label,
                powder_coat_margin=h.powder_coat_margin,
                icon=h.icon,
                mirror_group=h.mirror_group,
                mirror_x_flipped=h.mirror_x_flipped,
                mirror_y_flipped=h.mirror_y_flipped,
                mirror_ce_flipped=h.mirror_ce_flipped,
            )
            for h in payload.holes
        ]
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    store.save(p)
    return [HoleIO(**h.to_dict()) for h in p.holes]
