"""/projects/{slug}/stl — generate and serve drill-guide STL files per face."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from pedal_bench.api.deps import get_enclosure_catalog, get_project_store
from pedal_bench.api.schemas import STLExportOut
from pedal_bench.core.models import Enclosure
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.io.stl_builder import export_all_face_guides

router = APIRouter(prefix="/projects/{slug}/stl", tags=["stl"])


@router.post("/export", response_model=list[STLExportOut])
def export_all(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
) -> list[STLExportOut]:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    project = store.load(slug)
    if project.enclosure not in catalog:
        raise HTTPException(
            400,
            f"Project {slug!r} has enclosure {project.enclosure!r} which is not in the catalog",
        )
    if not project.holes:
        raise HTTPException(400, f"Project {slug!r} has no holes to export")

    drill_dir = store.project_dir(slug) / "drill"
    try:
        results = export_all_face_guides(catalog[project.enclosure], project.holes, drill_dir)
    except Exception as exc:  # OCP/build123d can raise odd things
        raise HTTPException(500, f"STL export failed: {type(exc).__name__}: {exc}")
    return [
        STLExportOut(side=side, path=str(path), size_bytes=path.stat().st_size)
        for side, path in sorted(results.items())
    ]


@router.get("/{side}.stl")
def download_stl(
    slug: str,
    side: str,
    store: ProjectStore = Depends(get_project_store),
) -> FileResponse:
    side = side.upper()
    path: Path = store.project_dir(slug) / "drill" / f"guide_{side}.stl"
    if not path.is_file():
        raise HTTPException(404, f"No STL generated yet for side {side!r}")
    return FileResponse(
        path,
        media_type="model/stl",
        filename=f"{slug}_guide_{side}.stl",
    )
