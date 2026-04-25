"""DIYLC (.diy) file ingestion.

Two routes mirror the PDF flow:
  POST /api/v1/diylc/extract      — preview-only extraction
  POST /api/v1/projects/from-diy  — create project from a .diy file

DIYLC files are XStream-serialized XML with components under <components>.
The parser is fully deterministic; no AI fallback needed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from pedal_bench.api.deps import get_project_store
from pedal_bench.api.schemas import BOMItemIO, ProjectOut
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.io.diylc_extract import parse_diylc

router = APIRouter(prefix="/diylc", tags=["diylc"])
projects_router = APIRouter(prefix="/projects", tags=["projects"])


class DIYLCExtractOut(BaseModel):
    suggested_name: str | None
    bom: list[BOMItemIO]
    skipped_count: int
    warnings: list[str]


def _read_diy(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".diy"):
        raise HTTPException(400, "Upload must be a .diy file (DIYLC project).")
    return file.file.read()


@router.post("/extract", response_model=DIYLCExtractOut)
async def diylc_extract(
    file: Annotated[UploadFile, File()],
) -> DIYLCExtractOut:
    """Preview-only — parse a DIYLC project and return a BOM. No disk writes."""
    content = _read_diy(file)
    if not content:
        raise HTTPException(400, "Empty upload.")
    try:
        result = parse_diylc(content)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return DIYLCExtractOut(
        suggested_name=result.title,
        bom=[BOMItemIO(**b.to_dict()) for b in result.bom],
        skipped_count=result.skipped_count,
        warnings=result.warnings,
    )


@projects_router.post("/from-diy", response_model=ProjectOut, status_code=201)
async def create_project_from_diy(
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
    enclosure: Annotated[str | None, Form()] = None,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectOut:
    """Atomic: parse a .diy file and create a new project with the BOM
    pre-populated. The .diy file itself isn't archived — it's the BOM we
    care about.
    """
    content = _read_diy(file)
    if not content:
        raise HTTPException(400, "Empty upload.")
    try:
        result = parse_diylc(content)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    effective_name = (name or result.title or _fallback_name(file.filename or "")).strip()
    if not effective_name:
        raise HTTPException(400, "Could not determine a project name.")

    try:
        project = store.create(effective_name, enclosure=(enclosure or "").strip())
    except FileExistsError:
        raise HTTPException(
            409,
            f"A project named {effective_name!r} already exists. Pick a different name.",
        )

    project.bom = list(result.bom)
    store.save(project)

    from pedal_bench.api.routes.projects import _project_to_out

    return _project_to_out(project)


def _fallback_name(filename: str) -> str:
    from pathlib import Path

    stem = Path(filename).stem
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled DIYLC Build"
