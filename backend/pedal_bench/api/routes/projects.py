"""/projects — CRUD on pedal build projects (JSON-backed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pedal_bench.api.deps import get_project_store
from pedal_bench.api.schemas import (
    BOMItemIO,
    BuildProgressIO,
    HoleIO,
    ProjectCreate,
    ProjectOut,
    ProjectSummary,
    ProjectUpdate,
)
from pedal_bench.core.models import (
    VALID_STATUS,
    BOMItem,
    BuildProgress,
    Hole,
    Project,
)
from pedal_bench.core.project_store import ProjectStore

router = APIRouter(prefix="/projects", tags=["projects"])


# ---- conversion helpers (core dataclass <-> API schema) -----------------

def _project_to_out(p: Project) -> ProjectOut:
    return ProjectOut(
        slug=p.slug,
        name=p.name,
        status=p.status,
        enclosure=p.enclosure,
        source_pdf=p.source_pdf,
        bom=[_bom_to_out(b) for b in p.bom],
        holes=[_hole_to_out(h) for h in p.holes],
        progress=BuildProgressIO(
            soldered_locations=sorted(p.progress.soldered_locations),
            current_phase=p.progress.current_phase,
            phase_notes=dict(p.progress.phase_notes),
        ),
        notes=p.notes,
        refdes_map={k: list(v) for k, v in p.refdes_map.items()},
        created_at=p.created_at,
        updated_at=p.updated_at,
        drill_tool_url=p.drill_tool_url,
    )


def _project_to_summary(p: Project) -> ProjectSummary:
    return ProjectSummary(
        slug=p.slug, name=p.name, status=p.status,
        enclosure=p.enclosure, updated_at=p.updated_at,
    )


def _bom_to_out(b: BOMItem) -> BOMItemIO:
    return BOMItemIO(
        location=b.location, value=b.value, type=b.type, notes=b.notes,
        quantity=b.quantity, polarity_sensitive=b.polarity_sensitive,
        orientation_hint=b.orientation_hint,
    )


def _hole_to_out(h: Hole) -> HoleIO:
    return HoleIO(
        side=h.side, x_mm=h.x_mm, y_mm=h.y_mm, diameter_mm=h.diameter_mm,
        label=h.label, powder_coat_margin=h.powder_coat_margin,
        icon=h.icon,
        mirror_group=h.mirror_group,
        mirror_x_flipped=h.mirror_x_flipped,
        mirror_y_flipped=h.mirror_y_flipped,
        mirror_ce_flipped=h.mirror_ce_flipped,
    )


# ---- routes -------------------------------------------------------------

@router.get("", response_model=list[ProjectSummary])
def list_projects(
    store: ProjectStore = Depends(get_project_store),
) -> list[ProjectSummary]:
    return [_project_to_summary(p) for p in store.iter_projects()]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectOut:
    try:
        p = store.create(payload.name, enclosure=payload.enclosure)
    except FileExistsError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return _project_to_out(p)


@router.get("/{slug}", response_model=ProjectOut)
def get_project(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    return _project_to_out(store.load(slug))


@router.patch("/{slug}", response_model=ProjectOut)
def update_project(
    slug: str,
    payload: ProjectUpdate,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    p = store.load(slug)
    if payload.name is not None and payload.name != p.name:
        try:
            p = store.rename(slug, payload.name)
            slug = p.slug
        except FileExistsError as exc:
            raise HTTPException(409, str(exc))
    if payload.status is not None:
        if payload.status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status {payload.status!r}")
        p.status = payload.status
    if payload.enclosure is not None:
        p.enclosure = payload.enclosure
    if payload.notes is not None:
        p.notes = payload.notes
    store.save(p)
    return _project_to_out(p)


@router.delete("/{slug}", status_code=204)
def delete_project(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
) -> None:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    store.delete(slug)
