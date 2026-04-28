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
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pedal_bench.api.deps import (
    get_enclosure_catalog,
    get_project_store,
    get_request_api_key,
)
from pedal_bench.api.schemas import BOMItemIO, HoleIO, ProjectOut
from pedal_bench.core.models import Enclosure
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.io.aionfx_extract import (
    extract_build_package as extract_aionfx_build_package,
    is_aionfx_pdf,
)
from pedal_bench.io.aionfx_fetch import AionFXFetchError, fetch_from_url as fetch_aionfx_url
from pedal_bench.io.aionfx_pdf import AionFXBOMParseError, extract_bom as extract_aionfx_bom
from pedal_bench.io.ai_bom_extract import extract_bom_with_ai
from pedal_bench.io.ai_drill_extract import extract_drill_holes_with_ai
from pedal_bench.io.build_import import ExtractedBuildPackage
from pedal_bench.io.drill_template_extract import extract_drill_holes as extract_pedalpcb_drill_holes
from pedal_bench.io.pedalpcb_pdf import BOMParseError, extract_bom
from pedal_bench.io.tayda_drill_api import (
    TaydaDrillAPIError,
    fetch_holes as fetch_tayda_drill_holes,
)
from pedal_bench.io.pdf_page_image import render_page_to_png
from pedal_bench.io.pedalpcb_extract import extract_build_package as extract_pedalpcb_build_package
from pedal_bench.io.pedalpcb_fetch import PedalPCBFetchError, fetch_from_product_url
from pedal_bench.io.taydakits_extract import (
    TaydakitsBuildPackage,
    extract_build_package_from_url,
)
from pedal_bench.io.taydakits_fetch import TaydakitsFetchError, USER_AGENT as TAYDAKITS_UA


def _ai_bom_fallback(pkg, tmp_path, api_key=None):
    """Invoke the AI BOM extractor when the deterministic table parser
    came up empty (older PedalPCB PDFs use a multi-column Parts List
    layout the heuristic doesn't handle). No-op if pkg.bom is non-empty
    or the AI path fails.

    When deterministic parse came up empty AND no AI key is configured,
    append a clear warning so the user knows their options (manual entry
    or add a key) instead of getting a blank BOM with no explanation.
    """
    if pkg.bom:
        return
    if api_key is None:
        pkg.warnings.append(
            "BOM couldn't be auto-extracted from this PDF. Open the BOM "
            "tab to enter parts manually, or add an Anthropic API key in "
            "Settings to enable AI extraction as a fallback."
        )
        return
    try:
        ai_bom = extract_bom_with_ai(tmp_path, api_key=api_key)
    except Exception:
        ai_bom = None
    if ai_bom:
        pkg.bom = ai_bom
        pkg.warnings.append(
            f"BOM extracted via AI fallback ({len(ai_bom)} rows). "
            "Review on the BOM tab before trusting."
        )


def _ai_drill_fallback(pkg, tmp_path, catalog, enclosure_override=None, api_key=None):
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
    if api_key is None:
        pkg.warnings.append(
            "Drill holes couldn't be auto-extracted from this PDF (likely "
            "an image-only or unusual drill template). Use the Drill tab "
            "to place holes manually, or add an Anthropic API key in "
            "Settings to enable AI extraction."
        )
        return
    try:
        ai_holes = extract_drill_holes_with_ai(
            tmp_path, page_index, encl, api_key=api_key
        )
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


def _extract_pdf_build_package(
    pdf_path: Path,
    enclosure: Enclosure | None = None,
) -> ExtractedBuildPackage:
    if is_aionfx_pdf(pdf_path):
        return extract_aionfx_build_package(pdf_path, enclosure=enclosure)
    return extract_pedalpcb_build_package(pdf_path, enclosure=enclosure)


def _render_pdf_page_if_known(pdf_path: Path, page_index: int | None, output_path: Path, dpi: int | None = None) -> None:
    if page_index is None:
        return
    try:
        kwargs = {"dpi": dpi} if dpi is not None else {}
        render_page_to_png(pdf_path, page_index=page_index, output_path=output_path, **kwargs)
    except Exception:
        pass


class PDFExtractOut(BaseModel):
    suggested_name: str | None
    suggested_enclosure: str | None
    enclosure_in_catalog: bool
    bom: list[BOMItemIO]
    holes: list[HoleIO]
    wiring_page_index: int | None
    drill_template_page_index: int | None
    warnings: list[str]
    # Workflow hand-offs (e.g. "drill coords aren't auto-imported, do X").
    # Distinct from `warnings`, which means something went wrong.
    next_steps: list[str] = []
    source_supplier: str | None = None
    source_url: str | None = None


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
    api_key: str | None = Depends(get_request_api_key),
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
        pkg = _extract_pdf_build_package(tmp_path)
        if (
            pkg.source_supplier != "aionfx"
            and pkg.enclosure
            and pkg.enclosure in catalog
            and not pkg.holes
        ):
            scaled_holes = extract_pedalpcb_drill_holes(tmp_path, enclosure=catalog[pkg.enclosure])
            if scaled_holes:
                pkg.holes = scaled_holes
        _ai_drill_fallback(pkg, tmp_path, catalog, api_key=api_key)
        _ai_bom_fallback(pkg, tmp_path, api_key=api_key)
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
        next_steps=pkg.next_steps,
        source_supplier=pkg.source_supplier,
        source_url=pkg.source_url,
    )


@projects_router.post("/from-pdf", response_model=ProjectOut, status_code=201)
async def create_project_from_pdf(
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
    enclosure: Annotated[str | None, Form()] = None,
    store: ProjectStore = Depends(get_project_store),
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
    api_key: str | None = Depends(get_request_api_key),
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
        pkg = _extract_pdf_build_package(tmp_path)
        enclosure_key = (
            enclosure
            or (pkg.enclosure if pkg.enclosure in catalog else "")
            or ""
        ).strip()
        if pkg.source_supplier != "aionfx" and enclosure_key in catalog:
            scaled_holes = extract_pedalpcb_drill_holes(tmp_path, enclosure=catalog[enclosure_key])
            if scaled_holes:
                pkg.holes = scaled_holes
        _ai_drill_fallback(
            pkg, tmp_path, catalog,
            enclosure_override=enclosure_key, api_key=api_key,
        )
        _ai_bom_fallback(pkg, tmp_path, api_key=api_key)
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
        project.source_supplier = pkg.source_supplier
        project.source_url = pkg.source_url

        # Attach pre-parsed BOM + drill holes.
        project.bom = list(pkg.bom)
        project.holes = list(pkg.holes)

        # Cache the wiring-diagram page as a PNG if we can figure out which
        # page it is. PedalPCB typically has it at page 4 (0-indexed = 3).
        wiring_page = pkg.wiring_page_index if pkg.wiring_page_index is not None else 3
        _render_pdf_page_if_known(dest_pdf, wiring_page, pdir / "wiring.png")

        # Also cache the PCB layout page (page 1, index 0) for the BOM
        # visualizer. Non-fatal if it fails.
        pcb_page = pkg.pcb_layout_page_index if pkg.pcb_layout_page_index is not None else 0
        _render_pdf_page_if_known(dest_pdf, pcb_page, pdir / "pcb_layout.png", dpi=180)

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
    api_key: str | None = Depends(get_request_api_key),
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
    pkg_preview = _extract_pdf_build_package(dest_pdf)
    project.source_supplier = pkg_preview.source_supplier
    project.source_url = pkg_preview.source_url

    # Cache wiring diagram + PCB/layout pages when the supplier parser can identify them.
    wiring_page = pkg_preview.wiring_page_index if pkg_preview.wiring_page_index is not None else 3
    _render_pdf_page_if_known(dest_pdf, wiring_page, pdir / "wiring.png")
    pcb_page = pkg_preview.pcb_layout_page_index if pkg_preview.pcb_layout_page_index is not None else 0
    _render_pdf_page_if_known(dest_pdf, pcb_page, pdir / "pcb_layout.png", dpi=180)

    # Try to extract drill holes using the project's enclosure spec.
    encl = catalog.get(project.enclosure) if project.enclosure else None
    try:
        extracted = (
            pkg_preview.holes
            if pkg_preview.source_supplier == "aionfx"
            else extract_pedalpcb_drill_holes(dest_pdf, enclosure=encl)
        )
        if extracted:
            project.holes = extracted
    except Exception:
        pass

    # AI fallback for image-only or unusually laid-out drill templates.
    if not project.holes and encl is not None:
        try:
            if pkg_preview.drill_template_page_index is not None:
                ai_holes = extract_drill_holes_with_ai(
                    dest_pdf, pkg_preview.drill_template_page_index, encl,
                    api_key=api_key,
                )
                if ai_holes:
                    project.holes = ai_holes
        except Exception:
            pass

    store.save(project)
    from pedal_bench.api.routes.projects import _project_to_out

    return _project_to_out(project)


class ReextractBOMOut(BaseModel):
    """Preview of a BOM re-extraction. Frontend confirms with PUT /bom."""

    bom: list[BOMItemIO]
    previous_count: int
    warnings: list[str]


@projects_router.post("/{slug}/reextract-bom", response_model=ReextractBOMOut)
def reextract_bom_from_source(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
    api_key: str | None = Depends(get_request_api_key),
) -> ReextractBOMOut:
    """Re-run the BOM extractor against a project's cached source.pdf.

    Doesn't write anything — the user confirms via the existing PUT /bom
    flow after reviewing the preview. Useful when a project was created
    against an older buggier extractor and ended up with a partial BOM.
    """
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    project = store.load(slug)
    if not project.source_pdf:
        raise HTTPException(
            400,
            "This project has no attached PDF — re-extraction needs a source.pdf. "
            "Use 'Attach PDF' on the project first.",
        )
    pdf_path = store.project_dir(slug) / project.source_pdf
    if not pdf_path.is_file():
        raise HTTPException(
            404,
            "PDF is referenced by the project but the file is missing on disk.",
        )

    warnings: list[str] = []
    new_bom = []
    try:
        if project.source_supplier == "aionfx" or is_aionfx_pdf(pdf_path):
            new_bom = extract_aionfx_bom(pdf_path)
        else:
            new_bom = extract_bom(pdf_path)
    except (AionFXBOMParseError, BOMParseError) as exc:
        warnings.append(f"BOM extraction failed: {exc}")
    except Exception as exc:
        warnings.append(f"BOM extraction error: {type(exc).__name__}: {exc}")

    if not new_bom and api_key is not None:
        try:
            ai_bom = extract_bom_with_ai(pdf_path, api_key=api_key)
        except Exception:
            ai_bom = None
        if ai_bom:
            new_bom = ai_bom
            warnings.append(
                f"BOM extracted via AI fallback ({len(ai_bom)} rows). "
                "Review before saving."
            )

    return ReextractBOMOut(
        bom=[BOMItemIO(**b.to_dict()) for b in new_bom],
        previous_count=len(project.bom),
        warnings=warnings,
    )


class ReextractHolesOut(BaseModel):
    """Preview of a hole re-extraction via the Tayda public API."""

    holes: list[HoleIO]
    previous_count: int
    source: str  # human-readable: "tayda-api" / "none"
    warnings: list[str]


@projects_router.post("/{slug}/reextract-holes", response_model=ReextractHolesOut)
def reextract_holes_from_tayda(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
) -> ReextractHolesOut:
    """Re-fetch the drill template via Tayda's public box-design API.

    Uses the project's stored ``drill_tool_url`` (captured at import) to
    pull canonical hole coordinates straight from
    ``api.taydakits.com``. Doesn't save — the frontend confirms via the
    existing PUT /holes flow after the user reviews the preview.

    Useful when:
      - A project was created before the auto-import existed.
      - The user clicked "Order drilled enclosure" on Tayda's site,
        edited the template there, and wants the changes pulled back.
    """
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    project = store.load(slug)
    if not project.drill_tool_url:
        raise HTTPException(
            400,
            "This project has no Tayda drill-tool URL on file. Re-extract "
            "needs a public_key link from the original build page.",
        )

    warnings: list[str] = []
    new_holes = []
    try:
        new_holes = fetch_tayda_drill_holes(project.drill_tool_url)
    except TaydaDrillAPIError as exc:
        warnings.append(f"Tayda API error: {exc}")

    return ReextractHolesOut(
        holes=[HoleIO(**h.to_dict()) for h in new_holes],
        previous_count=len(project.holes),
        source="tayda-api" if new_holes else "none",
        warnings=warnings,
    )


def _fallback_name(filename: str) -> str:
    stem = Path(filename).stem
    # PedalPCB naming: "Sherwood-Overdrive.pdf" → "Sherwood Overdrive"
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled Build"


def _is_taydakits_url(url: str) -> bool:
    """Hostname check for the URL routes. Cheap and string-only — never
    raises; the proper validation happens inside the Taydakits fetcher."""
    from urllib.parse import urlparse

    if not url:
        return False
    raw = url.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        host = (urlparse(raw).hostname or "").lower()
    except Exception:
        return False
    return host in {"taydakits.com", "www.taydakits.com"}


def _is_aionfx_url(url: str) -> bool:
    from urllib.parse import urlparse

    if not url:
        return False
    raw = url.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        host = (urlparse(raw).hostname or "").lower()
    except Exception:
        return False
    return host in {"aionfx.com", "www.aionfx.com"}


def _taydakits_pkg_to_response(
    pkg: TaydakitsBuildPackage,
    catalog: dict[str, Enclosure],
) -> PDFExtractOut:
    return PDFExtractOut(
        suggested_name=pkg.title,
        suggested_enclosure=pkg.enclosure,
        enclosure_in_catalog=(pkg.enclosure in catalog) if pkg.enclosure else False,
        bom=[BOMItemIO(**b.to_dict()) for b in pkg.bom],
        holes=[HoleIO(**h.to_dict()) for h in pkg.holes],
        wiring_page_index=None,
        drill_template_page_index=None,
        warnings=pkg.warnings,
        next_steps=pkg.next_steps,
        source_supplier="taydakits",
        source_url=pkg.source_url,
    )


def _cache_remote_image(url: str, dest: Path) -> bool:
    """Download a public image URL to dest. Returns True on success.

    Only used for Taydakits ckeditor_assets — no auth, no large files.
    Silent on failure so a transient image-host hiccup doesn't break
    project creation.
    """
    import httpx

    try:
        with httpx.Client(
            timeout=15.0,
            headers={"User-Agent": TAYDAKITS_UA},
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
            if not data or len(data) > 10 * 1024 * 1024:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return True
    except Exception:
        return False


@projects_router.get("/{slug}/source.pdf")
def serve_source_pdf(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
) -> FileResponse:
    """Serve the cached PedalPCB build doc inline so the browser opens it
    in a new tab (instead of forcing a download). Builders without a 3D
    printer use this to print specific pages — usually the drill template —
    via the browser's print dialog."""
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    project = store.load(slug)
    if not project.source_pdf:
        raise HTTPException(404, "No PDF attached to this project.")
    pdf_path = store.project_dir(slug) / project.source_pdf
    if not pdf_path.is_file():
        raise HTTPException(
            404,
            "PDF is referenced by the project but the file is missing on disk.",
        )
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{slug}.pdf",
        headers={"Content-Disposition": f'inline; filename="{slug}.pdf"'},
    )


@router.post("/from-url", response_model=PDFExtractOut)
async def pdf_extract_from_url(
    payload: URLExtractIn,
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
    api_key: str | None = Depends(get_request_api_key),
) -> PDFExtractOut:
    """Preview-only: fetch a build URL and run the appropriate extractor.

    Dispatches by hostname: pedalpcb.com → PDF flow, taydakits.com → HTML flow.
    Returns the same shape regardless of source so the frontend dialog can
    handle both transparently."""
    if _is_taydakits_url(payload.url):
        try:
            pkg = extract_build_package_from_url(payload.url)
        except TaydakitsFetchError as exc:
            raise HTTPException(400, str(exc)) from exc
        return _taydakits_pkg_to_response(pkg, catalog)

    if _is_aionfx_url(payload.url):
        try:
            fetched = fetch_aionfx_url(payload.url)
        except AionFXFetchError as exc:
            raise HTTPException(400, str(exc)) from exc

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(fetched.pdf_bytes)
            tmp_path = Path(tmp.name)
        try:
            pkg = extract_aionfx_build_package(tmp_path)
            pkg.source_url = fetched.source_url
            _ai_drill_fallback(pkg, tmp_path, catalog, api_key=api_key)
            _ai_bom_fallback(pkg, tmp_path, api_key=api_key)
        finally:
            tmp_path.unlink(missing_ok=True)

        return PDFExtractOut(
            suggested_name=pkg.title or fetched.suggested_name,
            suggested_enclosure=pkg.enclosure,
            enclosure_in_catalog=(pkg.enclosure in catalog) if pkg.enclosure else False,
            bom=[BOMItemIO(**b.to_dict()) for b in pkg.bom],
            holes=[HoleIO(**h.to_dict()) for h in pkg.holes],
            wiring_page_index=pkg.wiring_page_index,
            drill_template_page_index=pkg.drill_template_page_index,
            warnings=pkg.warnings,
            next_steps=pkg.next_steps,
            source_supplier="aionfx",
            source_url=fetched.source_url,
        )

    try:
        fetched = fetch_from_product_url(payload.url)
    except PedalPCBFetchError as exc:
        raise HTTPException(400, str(exc)) from exc

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(fetched.pdf_bytes)
        tmp_path = Path(tmp.name)
    try:
        pkg = extract_pedalpcb_build_package(tmp_path)
        if pkg.enclosure and pkg.enclosure in catalog and not pkg.holes:
            scaled_holes = extract_pedalpcb_drill_holes(tmp_path, enclosure=catalog[pkg.enclosure])
            if scaled_holes:
                pkg.holes = scaled_holes
        # If the product page advertises a Tayda drill-tool URL, prefer that
        # over the PDF-vector / AI extractors — it's the canonical source.
        # Skip when we already have holes from the PDF (vector parser is
        # still our most accurate path when it works).
        pkg.drill_tool_url = fetched.drill_tool_url
        if not pkg.holes and fetched.drill_tool_url:
            try:
                api_holes = fetch_tayda_drill_holes(fetched.drill_tool_url)
                if api_holes:
                    pkg.holes = api_holes
            except TaydaDrillAPIError:
                pass
        _ai_drill_fallback(pkg, tmp_path, catalog, api_key=api_key)
        _ai_bom_fallback(pkg, tmp_path, api_key=api_key)
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
        next_steps=pkg.next_steps,
        source_supplier=pkg.source_supplier,
        source_url=fetched.product_url,
    )


@projects_router.post("/from-url", response_model=ProjectOut, status_code=201)
async def create_project_from_url(
    payload: URLCreateIn,
    store: ProjectStore = Depends(get_project_store),
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
    api_key: str | None = Depends(get_request_api_key),
) -> ProjectOut:
    """Atomic: fetch a build URL, extract, create project with cached assets.

    Dispatches by hostname: pedalpcb.com → PDF flow, taydakits.com → HTML flow."""
    if _is_taydakits_url(payload.url):
        return _create_project_from_taydakits(payload, store, catalog)

    if _is_aionfx_url(payload.url):
        return _create_project_from_aionfx(payload, store, catalog, api_key)

    try:
        fetched = fetch_from_product_url(payload.url)
    except PedalPCBFetchError as exc:
        raise HTTPException(400, str(exc)) from exc

    pdf_bytes = fetched.pdf_bytes

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = Path(tmp.name)
    try:
        pkg = extract_pedalpcb_build_package(tmp_path)
        enclosure_key = (
            payload.enclosure
            or (pkg.enclosure if pkg.enclosure in catalog else "")
            or ""
        ).strip()
        if enclosure_key in catalog:
            scaled_holes = extract_pedalpcb_drill_holes(tmp_path, enclosure=catalog[enclosure_key])
            if scaled_holes:
                pkg.holes = scaled_holes
        # Tayda drill-API fallback before AI — same rationale as the preview
        # route: the API is canonical and free, AI is paid + best-effort.
        pkg.drill_tool_url = fetched.drill_tool_url
        if not pkg.holes and fetched.drill_tool_url:
            try:
                api_holes = fetch_tayda_drill_holes(fetched.drill_tool_url)
                if api_holes:
                    pkg.holes = api_holes
            except TaydaDrillAPIError:
                pass
        _ai_drill_fallback(
            pkg, tmp_path, catalog,
            enclosure_override=enclosure_key, api_key=api_key,
        )
        _ai_bom_fallback(pkg, tmp_path, api_key=api_key)

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
        project.drill_tool_url = fetched.drill_tool_url
        project.source_supplier = "pedalpcb"
        project.source_url = fetched.product_url

        wiring_page = (
            pkg.wiring_page_index if pkg.wiring_page_index is not None else 3
        )
        _render_pdf_page_if_known(dest_pdf, wiring_page, pdir / "wiring.png")
        _render_pdf_page_if_known(dest_pdf, 0, pdir / "pcb_layout.png", dpi=180)

        store.save(project)

        from pedal_bench.api.routes.projects import _project_to_out

        return _project_to_out(project)
    finally:
        tmp_path.unlink(missing_ok=True)


def _create_project_from_aionfx(
    payload: URLCreateIn,
    store: ProjectStore,
    catalog: dict[str, Enclosure],
    api_key: str | None,
) -> ProjectOut:
    try:
        fetched = fetch_aionfx_url(payload.url)
    except AionFXFetchError as exc:
        raise HTTPException(400, str(exc)) from exc

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(fetched.pdf_bytes)
        tmp_path = Path(tmp.name)
    try:
        pkg = extract_aionfx_build_package(tmp_path)
        pkg.source_url = fetched.source_url
        enclosure_key = (
            payload.enclosure
            or (pkg.enclosure if pkg.enclosure in catalog else "")
            or ""
        ).strip()
        _ai_drill_fallback(
            pkg, tmp_path, catalog,
            enclosure_override=enclosure_key, api_key=api_key,
        )
        _ai_bom_fallback(pkg, tmp_path, api_key=api_key)

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
        dest_pdf.write_bytes(fetched.pdf_bytes)
        project.source_pdf = "source.pdf"
        project.source_supplier = "aionfx"
        project.source_url = fetched.source_url
        project.bom = list(pkg.bom)
        project.holes = list(pkg.holes)

        _render_pdf_page_if_known(dest_pdf, pkg.wiring_page_index, pdir / "wiring.png")
        pcb_page = pkg.pcb_layout_page_index if pkg.pcb_layout_page_index is not None else 0
        _render_pdf_page_if_known(dest_pdf, pcb_page, pdir / "pcb_layout.png", dpi=180)

        store.save(project)

        from pedal_bench.api.routes.projects import _project_to_out

        return _project_to_out(project)
    finally:
        tmp_path.unlink(missing_ok=True)


def _create_project_from_taydakits(
    payload: URLCreateIn,
    store: ProjectStore,
    catalog: dict[str, Enclosure],
) -> ProjectOut:
    """Atomic create from a taydakits.com instructions URL.

    Mirrors the PedalPCB URL flow but operates on HTML pages and remote
    images rather than a PDF. Holes auto-populate from Tayda's public
    box-design API when the instructions page links to a drill template;
    otherwise users can fetch them later from the Drill tab.
    """
    try:
        pkg = extract_build_package_from_url(payload.url)
    except TaydakitsFetchError as exc:
        raise HTTPException(400, str(exc)) from exc

    enclosure_key = (
        payload.enclosure
        or (pkg.enclosure if pkg.enclosure in catalog else "")
        or ""
    ).strip()

    effective_name = (payload.name or pkg.title or "Untitled Build").strip()
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

    project.bom = list(pkg.bom)
    project.holes = list(pkg.holes)
    project.source_pdf = None  # no PDF for Taydakits builds
    project.drill_tool_url = pkg.drill_tool_url
    project.source_supplier = "taydakits"
    project.source_url = pkg.source_url

    if pkg.pcb_layout_image_url:
        _cache_remote_image(pkg.pcb_layout_image_url, pdir / "pcb_layout.png")
    if pkg.wiring_image_url:
        _cache_remote_image(pkg.wiring_image_url, pdir / "wiring.png")
    if pkg.schematic_image_url:
        _cache_remote_image(pkg.schematic_image_url, pdir / "schematic.png")

    store.save(project)
    from pedal_bench.api.routes.projects import _project_to_out

    return _project_to_out(project)
