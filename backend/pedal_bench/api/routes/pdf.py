"""PDF upload + ingestion endpoints.

Two routes:
  POST /api/v1/pdf/extract         — preview-only: extract title, enclosure,
                                     BOM. Doesn't write anything to disk.
  POST /api/v1/projects/from-pdf   — atomic: extract + create project with
                                     the file attached as source.pdf and
                                     page 4 cached as wiring.png.

Both accept multipart/form-data with a `file` field containing the PDF.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from pedal_bench.api.deps import get_enclosure_catalog, get_project_store
from pedal_bench.api.schemas import BOMItemIO, ProjectOut
from pedal_bench.core.models import Enclosure
from pedal_bench.core.project_store import ProjectStore, slugify
from pedal_bench.io.pdf_page_image import render_page_to_png
from pedal_bench.io.pedalpcb_extract import extract_build_package

router = APIRouter(prefix="/pdf", tags=["pdf"])
projects_router = APIRouter(prefix="/projects", tags=["projects"])


class PDFExtractOut(BaseModel):
    suggested_name: str | None
    suggested_enclosure: str | None
    enclosure_in_catalog: bool
    bom: list[BOMItemIO]
    wiring_page_index: int | None
    drill_template_page_index: int | None
    warnings: list[str]


@router.post("/extract", response_model=PDFExtractOut)
async def pdf_extract(
    file: Annotated[UploadFile, File()],
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
) -> PDFExtractOut:
    """Preview-only extraction. Writes nothing; user can review and tweak
    before committing to a project."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload must be a PDF.")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(400, "Empty upload.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = Path(tmp.name)
    try:
        pkg = extract_build_package(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return PDFExtractOut(
        suggested_name=pkg.title,
        suggested_enclosure=pkg.enclosure,
        enclosure_in_catalog=(pkg.enclosure in catalog) if pkg.enclosure else False,
        bom=[BOMItemIO(**b.to_dict()) for b in pkg.bom],
        wiring_page_index=pkg.wiring_page_index,
        drill_template_page_index=pkg.drill_template_page_index,
        warnings=pkg.warnings,
    )


@projects_router.post("/from-pdf", response_model=ProjectOut, status_code=201)
async def create_project_from_pdf(
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
    enclosure: Annotated[str | None, Form()] = None,
    store: ProjectStore = Depends(get_project_store),
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
) -> ProjectOut:
    """Atomic: extract from PDF, create a new project with the attached
    file, pre-populated BOM, and cached wiring image. User overrides for
    name / enclosure take precedence over auto-detected values."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload must be a PDF.")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(400, "Empty upload.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = Path(tmp.name)
    try:
        pkg = extract_build_package(tmp_path)
        effective_name = (name or pkg.title or _fallback_name(file.filename)).strip()
        if not effective_name:
            raise HTTPException(400, "Could not determine a project name.")
        effective_enclosure = (enclosure or (pkg.enclosure if pkg.enclosure in catalog else "") or "").strip()

        try:
            project = store.create(effective_name, enclosure=effective_enclosure)
        except FileExistsError:
            raise HTTPException(
                409,
                f"A project named {effective_name!r} already exists. Pick a different name.",
            )

        # Copy the attached PDF into the new project folder.
        pdir = store.project_dir(project.slug)
        pdir.mkdir(parents=True, exist_ok=True)
        dest_pdf = pdir / "source.pdf"
        dest_pdf.write_bytes(pdf_bytes)
        project.source_pdf = "source.pdf"

        # Attach pre-parsed BOM.
        project.bom = list(pkg.bom)

        # Cache the wiring-diagram page as a PNG if we can figure out which
        # page it is. PedalPCB typically has it at page 4 (0-indexed = 3).
        wiring_page = (
            pkg.wiring_page_index
            if pkg.wiring_page_index is not None
            else 3
        )
        try:
            render_page_to_png(dest_pdf, page_index=wiring_page, output_path=pdir / "wiring.png")
        except Exception:
            # Missing wiring render is non-fatal.
            pass

        store.save(project)

        # Re-import here to avoid circular imports at module load.
        from pedal_bench.api.routes.projects import _project_to_out

        return _project_to_out(project)
    finally:
        tmp_path.unlink(missing_ok=True)


def _fallback_name(filename: str) -> str:
    stem = Path(filename).stem
    # PedalPCB naming: "Sherwood-Overdrive.pdf" → "Sherwood Overdrive"
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled Build"
