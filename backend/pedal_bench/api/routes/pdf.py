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
from pedal_bench.api.schemas import BOMItemIO, HoleIO, ProjectOut
from pedal_bench.core.models import Enclosure
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.io.ai_drill_extract import extract_drill_holes_with_ai
from pedal_bench.io.drill_template_extract import extract_drill_holes
from pedal_bench.io.pdf_page_image import render_page_to_png
from pedal_bench.io.pedalpcb_extract import extract_build_package
from pedal_bench.io.pedalpcb_fetch import PedalPCBFetchError, fetch_from_product_url


def _ai_drill_fallback(pkg, tmp_path, catalog, enclosure_override=None):
    """Invoke the AI drill extractor when vector extraction came up empty.

    Mutates ``pkg`` in-place if the AI returned usable holes. No-op if the
    AI path fails, no API key is set, or no enclosure is known.
    """
    if pkg.holes:
        return
    enclosure_key = (enclosure_override or pkg.enclosure or "").strip()
    encl = catalog.get(enclosure_key) if enclosure_key else None
    if encl is None:
        return
    page_index = pkg.drill_template_page_index
    if page_index is None:
        return
    try:
        ai_holes = extract_drill_holes_with_ai(tmp_path, page_index, encl)
    except Exception:
        ai_holes = None
    if ai_holes:
        pkg.holes = ai_holes
        pkg.warnings.append(
            f"Drill holes extracted via AI fallback ({len(ai_holes)} holes). "
            "Review on the Drill tab before trusting."
        )

router = APIRouter(prefix="/pdf", tags=["pdf"])
projects_router = APIRouter(prefix="/projects", tags=["projects"])


class PDFExtractOut(BaseModel):
    suggested_name: str | None
    suggested_enclosure: str | None
    enclosure_in_catalog: bool
    bom: list[BOMItemIO]
    holes: list[HoleIO]
    wiring_page_index: int | None
    drill_template_page_index: int | None
    warnings: list[str]


class URLExtractIn(BaseModel):
    url: str


class URLCreateIn(BaseModel):
    url: str
    name: str | None = None
    enclosure: str | None = None


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
        # First-pass extract to detect the enclosure; if it's in our
        # catalog, re-run the drill extractor with accurate scaling.
        pkg = extract_build_package(tmp_path)
        if pkg.enclosure and pkg.enclosure in catalog and not pkg.holes:
            scaled_holes = extract_drill_holes(tmp_path, enclosure=catalog[pkg.enclosure])
            if scaled_holes:
                pkg.holes = scaled_holes
        _ai_drill_fallback(pkg, tmp_path, catalog)
    finally:
        tmp_path.unlink(missing_ok=True)

    return PDFExtractOut(
        suggested_name=pkg.title,
        suggested_enclosure=pkg.enclosure,
        enclosure_in_catalog=(pkg.enclosure in catalog) if pkg.enclosure else False,
        bom=[BOMItemIO(**b.to_dict()) for b in pkg.bom],
        holes=[HoleIO(**h.to_dict()) for h in pkg.holes],
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
        # First-pass extract to detect enclosure; then re-run drill
        # extraction with proper scaling so holes land in real mm.
        pkg = extract_build_package(tmp_path)
        enclosure_key = (
            enclosure
            or (pkg.enclosure if pkg.enclosure in catalog else "")
            or ""
        ).strip()
        if enclosure_key in catalog:
            scaled_holes = extract_drill_holes(tmp_path, enclosure=catalog[enclosure_key])
            if scaled_holes:
                pkg.holes = scaled_holes
        _ai_drill_fallback(pkg, tmp_path, catalog, enclosure_override=enclosure_key)
        effective_name = (name or pkg.title or _fallback_name(file.filename)).strip()
        if not effective_name:
            raise HTTPException(400, "Could not determine a project name.")
        effective_enclosure = enclosure_key

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

        # Attach pre-parsed BOM + drill holes.
        project.bom = list(pkg.bom)
        project.holes = list(pkg.holes)

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
            pass

        # Also cache the PCB layout page (page 1, index 0) for the BOM
        # visualizer. Non-fatal if it fails.
        try:
            render_page_to_png(dest_pdf, page_index=0, output_path=pdir / "pcb_layout.png", dpi=180)
        except Exception:
            pass

        store.save(project)

        # Re-import here to avoid circular imports at module load.
        from pedal_bench.api.routes.projects import _project_to_out

        return _project_to_out(project)
    finally:
        tmp_path.unlink(missing_ok=True)


@projects_router.post("/{slug}/attach-pdf", response_model=ProjectOut)
async def attach_pdf_to_existing(
    slug: str,
    file: Annotated[UploadFile, File()],
    store: ProjectStore = Depends(get_project_store),
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
) -> ProjectOut:
    """Attach a PDF to an existing project.

    Copies the file to source.pdf, caches the wiring page as PNG, and runs
    the drill-template extractor — replacing project.holes only if the
    extractor returns something. Leaves the BOM alone (user can import it
    separately on the BOM tab).
    """
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload must be a PDF.")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(400, "Empty upload.")

    project = store.load(slug)
    pdir = store.project_dir(slug)
    pdir.mkdir(parents=True, exist_ok=True)
    dest_pdf = pdir / "source.pdf"
    dest_pdf.write_bytes(pdf_bytes)
    project.source_pdf = "source.pdf"

    # Cache wiring diagram (page 4, 0-indexed = 3) + PCB layout (page 1).
    try:
        render_page_to_png(dest_pdf, page_index=3, output_path=pdir / "wiring.png")
    except Exception:
        pass
    try:
        render_page_to_png(dest_pdf, page_index=0, output_path=pdir / "pcb_layout.png", dpi=180)
    except Exception:
        pass

    # Try to extract drill holes using the project's enclosure spec.
    encl = catalog.get(project.enclosure) if project.enclosure else None
    try:
        extracted = extract_drill_holes(dest_pdf, enclosure=encl)
        if extracted:
            project.holes = extracted
    except Exception:
        pass

    # AI fallback for image-only or unusually laid-out drill templates.
    if not project.holes and encl is not None:
        try:
            pkg_preview = extract_build_package(dest_pdf)
            if pkg_preview.drill_template_page_index is not None:
                ai_holes = extract_drill_holes_with_ai(
                    dest_pdf, pkg_preview.drill_template_page_index, encl
                )
                if ai_holes:
                    project.holes = ai_holes
        except Exception:
            pass

    store.save(project)
    from pedal_bench.api.routes.projects import _project_to_out

    return _project_to_out(project)


def _fallback_name(filename: str) -> str:
    stem = Path(filename).stem
    # PedalPCB naming: "Sherwood-Overdrive.pdf" → "Sherwood Overdrive"
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled Build"


@router.post("/from-url", response_model=PDFExtractOut)
async def pdf_extract_from_url(
    payload: URLExtractIn,
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
) -> PDFExtractOut:
    """Preview-only: fetch a PedalPCB product-page URL, grab the build PDF,
    and run the same extractor as /pdf/extract. Nothing is written to disk."""
    try:
        fetched = fetch_from_product_url(payload.url)
    except PedalPCBFetchError as exc:
        raise HTTPException(400, str(exc)) from exc

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(fetched.pdf_bytes)
        tmp_path = Path(tmp.name)
    try:
        pkg = extract_build_package(tmp_path)
        if pkg.enclosure and pkg.enclosure in catalog and not pkg.holes:
            scaled_holes = extract_drill_holes(tmp_path, enclosure=catalog[pkg.enclosure])
            if scaled_holes:
                pkg.holes = scaled_holes
    finally:
        tmp_path.unlink(missing_ok=True)

    # Prefer the product-page <h1> if the PDF title extractor failed.
    suggested = pkg.title or fetched.suggested_name

    return PDFExtractOut(
        suggested_name=suggested,
        suggested_enclosure=pkg.enclosure,
        enclosure_in_catalog=(pkg.enclosure in catalog) if pkg.enclosure else False,
        bom=[BOMItemIO(**b.to_dict()) for b in pkg.bom],
        holes=[HoleIO(**h.to_dict()) for h in pkg.holes],
        wiring_page_index=pkg.wiring_page_index,
        drill_template_page_index=pkg.drill_template_page_index,
        warnings=pkg.warnings,
    )


@projects_router.post("/from-url", response_model=ProjectOut, status_code=201)
async def create_project_from_url(
    payload: URLCreateIn,
    store: ProjectStore = Depends(get_project_store),
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
) -> ProjectOut:
    """Atomic: fetch a PedalPCB product URL, extract, create project with
    the PDF attached and images cached."""
    try:
        fetched = fetch_from_product_url(payload.url)
    except PedalPCBFetchError as exc:
        raise HTTPException(400, str(exc)) from exc

    pdf_bytes = fetched.pdf_bytes

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = Path(tmp.name)
    try:
        pkg = extract_build_package(tmp_path)
        enclosure_key = (
            payload.enclosure
            or (pkg.enclosure if pkg.enclosure in catalog else "")
            or ""
        ).strip()
        if enclosure_key in catalog:
            scaled_holes = extract_drill_holes(tmp_path, enclosure=catalog[enclosure_key])
            if scaled_holes:
                pkg.holes = scaled_holes
        _ai_drill_fallback(pkg, tmp_path, catalog, enclosure_override=enclosure_key)

        effective_name = (
            payload.name
            or pkg.title
            or fetched.suggested_name
            or _fallback_name(Path(fetched.pdf_url).name)
        ).strip()
        if not effective_name:
            raise HTTPException(400, "Could not determine a project name.")

        try:
            project = store.create(effective_name, enclosure=enclosure_key)
        except FileExistsError:
            raise HTTPException(
                409,
                f"A project named {effective_name!r} already exists. Pick a different name.",
            )

        pdir = store.project_dir(project.slug)
        pdir.mkdir(parents=True, exist_ok=True)
        dest_pdf = pdir / "source.pdf"
        dest_pdf.write_bytes(pdf_bytes)
        project.source_pdf = "source.pdf"
        project.bom = list(pkg.bom)
        project.holes = list(pkg.holes)

        wiring_page = (
            pkg.wiring_page_index if pkg.wiring_page_index is not None else 3
        )
        try:
            render_page_to_png(dest_pdf, page_index=wiring_page, output_path=pdir / "wiring.png")
        except Exception:
            pass
        try:
            render_page_to_png(dest_pdf, page_index=0, output_path=pdir / "pcb_layout.png", dpi=180)
        except Exception:
            pass

        store.save(project)

        from pedal_bench.api.routes.projects import _project_to_out

        return _project_to_out(project)
    finally:
        tmp_path.unlink(missing_ok=True)
