"""PCB-layout image + per-component refdes map.

  GET  /api/v1/projects/{slug}/pcb-layout.png
       Serves the cached PCB-layout page rendered from the attached PDF.

  PUT  /api/v1/projects/{slug}/refdes-map
       Replace the whole refdes→(x_pct, y_pct) map. The frontend uses this
       when the user click-tags component positions on the BOM tab.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pedal_bench.api.deps import get_project_store
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.io.pdf_page_image import render_page_to_png

router = APIRouter(prefix="/projects/{slug}", tags=["pcb-layout"])


class RefdesMapIn(BaseModel):
    refdes_map: dict[str, list[float]] = Field(default_factory=dict)


class RefdesMapOut(BaseModel):
    refdes_map: dict[str, list[float]]


@router.get("/pcb-layout.png")
def get_pcb_layout_image(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
) -> FileResponse:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    pdir: Path = store.project_dir(slug)
    path: Path = pdir / "pcb_layout.png"
    # Lazy-render for projects attached before the cache was introduced.
    if not path.is_file():
        pdf_path = pdir / "source.pdf"
        if not pdf_path.is_file():
            raise HTTPException(404, "No PDF attached to this project, so no PCB layout available.")
        try:
            render_page_to_png(pdf_path, page_index=0, output_path=path, dpi=180)
        except Exception as exc:
            raise HTTPException(500, f"Failed to render PCB layout: {type(exc).__name__}: {exc}")
    return FileResponse(path, media_type="image/png", filename=f"{slug}_pcb_layout.png")


@router.put("/refdes-map", response_model=RefdesMapOut)
def replace_refdes_map(
    slug: str,
    payload: RefdesMapIn,
    store: ProjectStore = Depends(get_project_store),
) -> RefdesMapOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    project = store.load(slug)
    clean: dict[str, list[float]] = {}
    for refdes, coord in payload.refdes_map.items():
        if not isinstance(coord, (list, tuple)) or len(coord) != 2:
            continue
        try:
            x = max(0.0, min(1.0, float(coord[0])))
            y = max(0.0, min(1.0, float(coord[1])))
        except (TypeError, ValueError):
            continue
        clean[refdes] = [x, y]
    project.refdes_map = clean
    store.save(project)
    return RefdesMapOut(refdes_map=clean)
