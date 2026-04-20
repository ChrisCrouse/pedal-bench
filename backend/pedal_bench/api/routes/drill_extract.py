"""Project-scoped drill-template re-extraction.

Runs the same vector extractor used by /pdf/extract, but against the
already-attached source.pdf of an existing project. Returns the
extracted holes WITHOUT saving — the frontend presents them in a
review dialog and lets the user accept (replace / append) before
writing back via the existing PUT /projects/{slug}/holes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pedal_bench.api.deps import get_enclosure_catalog, get_project_store
from pedal_bench.api.schemas import HoleIO
from pedal_bench.core.models import Enclosure
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.io.drill_template_extract import extract_drill_holes

router = APIRouter(prefix="/projects/{slug}", tags=["drill-extract"])


@router.post("/extract-holes", response_model=list[HoleIO])
def extract_holes_from_attached_pdf(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
) -> list[HoleIO]:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    project = store.load(slug)
    pdir = store.project_dir(slug)
    pdf_path = pdir / "source.pdf"
    if not pdf_path.is_file():
        raise HTTPException(
            400,
            "No PDF attached to this project. Re-create the project via "
            "the drop-zone on the home page, or attach a PDF first.",
        )
    encl = catalog.get(project.enclosure) if project.enclosure else None
    try:
        holes = extract_drill_holes(pdf_path, enclosure=encl)
    except Exception as exc:
        raise HTTPException(500, f"Extraction failed: {type(exc).__name__}: {exc}")
    if not holes:
        raise HTTPException(
            422,
            "Couldn't extract holes from this PDF. The drill-template "
            "page may be rendered differently than expected — try "
            "pasting Tayda coords or placing holes manually.",
        )
    return [HoleIO(**h.to_dict()) for h in holes]
