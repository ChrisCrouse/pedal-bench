"""/projects — CRUD on pedal build projects (JSON-backed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pedal_bench.api.deps import get_inventory_store, get_project_store
from pedal_bench.api.routes.inventory import (
    consume_reservations_for,
    project_shortage_for,
)
from pedal_bench.core.shortage import compute_project_shortage
from pedal_bench.api.schemas import (
    BOMItemIO,
    BuildProgressIO,
    ConsumeReservationsOut,
    HoleIO,
    ProjectCreate,
    ProjectOut,
    ProjectSummary,
    ProjectUpdate,
    ShortageOut,
)
from pedal_bench.core.inventory_store import InventoryStore
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

def _project_to_out(p: Project, store: ProjectStore | None = None) -> ProjectOut:
    has_custom_pcb_image = False
    if store is not None:
        try:
            has_custom_pcb_image = (
                store.project_dir(p.slug) / "pcb_layout_custom.png"
            ).is_file()
        except Exception:
            has_custom_pcb_image = False
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
        source_supplier=p.source_supplier,
        source_url=p.source_url,
        active=p.active,
        has_custom_pcb_image=has_custom_pcb_image,
    )


def _project_to_summary(
    p: Project, inv: InventoryStore | None = None
) -> ProjectSummary:
    """Build a ProjectSummary with readiness stats baked in.

    `inv` is optional so callers that don't need readiness (e.g. raw create
    response) can skip the inventory load. When supplied, we run the same
    shortage compute the per-project endpoint uses, which keeps the
    "covered" math identical across the UI.
    """
    bom_count = len(p.bom)
    soldered_count = len(p.progress.soldered_locations)
    parts_needed = 0
    parts_covered = 0
    readiness_pct: int | None = None

    if inv is not None:
        rows = compute_project_shortage(p, inv)
        for row in rows:
            parts_needed += row.needed
            # Effective availability for this build = free stock + the share
            # already reserved for this project. Cap at row.needed so a row
            # over-reserved elsewhere doesn't inflate coverage.
            covered_for_row = min(
                row.needed, row.available + row.reserved_for_self
            )
            parts_covered += covered_for_row
        if parts_needed > 0:
            readiness_pct = round(100 * parts_covered / parts_needed)

    return ProjectSummary(
        slug=p.slug,
        name=p.name,
        status=p.status,
        enclosure=p.enclosure,
        updated_at=p.updated_at,
        active=p.active,
        bom_count=bom_count,
        soldered_count=soldered_count,
        readiness_pct=readiness_pct,
        parts_needed=parts_needed,
        parts_covered=parts_covered,
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
    inv: InventoryStore = Depends(get_inventory_store),
) -> list[ProjectSummary]:
    # Inventory is loaded once and reused across every per-project shortage
    # compute below, so this list endpoint stays O(projects × bom_rows) on
    # disk reads — same as iterating projects without readiness.
    return [_project_to_summary(p, inv) for p in store.iter_projects()]


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
    return _project_to_out(p, store)


@router.get("/{slug}", response_model=ProjectOut)
def get_project(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    return _project_to_out(store.load(slug), store)


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
    if payload.active is not None:
        p.active = payload.active
    store.save(p)
    return _project_to_out(p, store)


@router.delete("/{slug}", status_code=204)
def delete_project(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
    inv: InventoryStore = Depends(get_inventory_store),
) -> None:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    # Drop any reservations belonging to this project so freed inventory
    # becomes available again for other builds.
    inv.clear_reservations(slug)
    store.delete(slug)


@router.get("/{slug}/shortage", response_model=ShortageOut)
def project_shortage(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
    inv: InventoryStore = Depends(get_inventory_store),
) -> ShortageOut:
    return project_shortage_for(slug, inv, store)


@router.post(
    "/{slug}/consume-reservations",
    response_model=ConsumeReservationsOut,
)
def consume_reservations(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
    inv: InventoryStore = Depends(get_inventory_store),
) -> ConsumeReservationsOut:
    return consume_reservations_for(slug, inv, store)
