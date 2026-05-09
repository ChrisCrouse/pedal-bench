"""PCB-layout image + per-component refdes map.

  GET  /api/v1/projects/{slug}/pcb-layout.png
       Serves the project's PCB layout image. Prefers a user-uploaded
       custom image; falls back to the cached page rendered from the
       attached PDF.

  POST /api/v1/projects/{slug}/pcb-layout-image
       Upload a custom PCB layout image (PNG/JPG/WebP). Useful for
       manually-created projects that don't have a PedalPCB PDF.

  DELETE /api/v1/projects/{slug}/pcb-layout-image
       Remove the custom image. The PDF-rendered cache (if any) takes
       over again on the next GET.

  PUT  /api/v1/projects/{slug}/refdes-map
       Replace the whole refdes→(x_pct, y_pct) map. The frontend uses this
       when the user click-tags component positions on the BOM tab.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from pedal_bench.api.deps import get_project_store
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.io.pdf_page_image import render_page_to_png

router = APIRouter(prefix="/projects/{slug}", tags=["pcb-layout"])

CUSTOM_IMAGE_NAME = "pcb_layout_custom.png"
CACHED_IMAGE_NAME = "pcb_layout.png"
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


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

    # User-uploaded image wins over the PDF-rendered cache.
    custom: Path = pdir / CUSTOM_IMAGE_NAME
    if custom.is_file():
        media = "image/png"
        # We always normalize the extension to .png on upload, but the
        # original mime may have been jpg/webp — sniff a couple bytes so
        # the browser doesn't complain.
        with custom.open("rb") as f:
            head = f.read(12)
        if head.startswith(b"\xff\xd8\xff"):
            media = "image/jpeg"
        elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            media = "image/webp"
        return FileResponse(custom, media_type=media, filename=f"{slug}_pcb_layout.png")

    path: Path = pdir / CACHED_IMAGE_NAME
    # Lazy-render for projects attached before the cache was introduced.
    if not path.is_file():
        pdf_path = pdir / "source.pdf"
        if not pdf_path.is_file():
            raise HTTPException(404, "No PCB layout available. Attach a PDF or upload a custom image.")
        try:
            render_page_to_png(pdf_path, page_index=0, output_path=path, dpi=180)
        except Exception as exc:
            raise HTTPException(500, f"Failed to render PCB layout: {type(exc).__name__}: {exc}")
    return FileResponse(path, media_type="image/png", filename=f"{slug}_pcb_layout.png")


@router.post("/pcb-layout-image")
async def upload_pcb_layout_image(
    slug: str,
    file: Annotated[UploadFile, File()],
    store: ProjectStore = Depends(get_project_store),
) -> dict[str, str]:
    """Upload a custom PCB layout image (PNG/JPG/WebP, max 10 MB).

    The file is stored as-is at ``pcb_layout_custom.png``. Re-uploading
    overwrites the previous custom image.
    """
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    if not file.filename:
        raise HTTPException(400, "Missing filename.")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            400,
            f"Unsupported image type {ext!r}. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTS))}.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty upload.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, f"Image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit.")

    pdir: Path = store.project_dir(slug)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / CUSTOM_IMAGE_NAME).write_bytes(data)
    return {"status": "ok"}


@router.delete("/pcb-layout-image", status_code=204)
def delete_pcb_layout_image(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
) -> Response:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    custom = store.project_dir(slug) / CUSTOM_IMAGE_NAME
    custom.unlink(missing_ok=True)
    return Response(status_code=204)


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
