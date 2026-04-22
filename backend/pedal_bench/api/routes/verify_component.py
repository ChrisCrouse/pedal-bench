"""Component-photo verification endpoint.

Builder takes a photo of the part they're about to stuff. Backend runs it
past Claude vision + the BOM row's expected value/type and returns a
verdict. Used from the BOM tab as a sanity check before soldering.

Endpoint:
    POST /api/v1/projects/{slug}/bom/verify-component
        multipart/form-data:
          file      — jpeg / png / webp image
          location  — BOM row location (e.g. "R7"). Used to look up
                      expected value + type from the stored BOM.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from pedal_bench.api.deps import get_project_store, get_request_api_key
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.io.ai_component_verify import verify_component_photo

router = APIRouter(prefix="/projects/{slug}/bom", tags=["verify"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB — plenty for a component photo
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


class VerifyOut(BaseModel):
    verdict: str              # match | mismatch | unsure | error
    explanation: str
    guess_value: str | None = None
    guess_type: str | None = None
    expected_value: str
    expected_type: str
    location: str


@router.post("/verify-component", response_model=VerifyOut)
async def verify_component(
    slug: str,
    file: Annotated[UploadFile, File()],
    location: Annotated[str, Form()],
    store: ProjectStore = Depends(get_project_store),
    api_key: str | None = Depends(get_request_api_key),
) -> VerifyOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_TYPES:
        # Allow 'image/jpg' which some clients send.
        if content_type == "image/jpg":
            content_type = "image/jpeg"
        else:
            raise HTTPException(
                400, f"Unsupported image type: {content_type!r}. Use JPEG, PNG, or WebP."
            )

    blob = await file.read()
    if not blob:
        raise HTTPException(400, "Empty upload.")
    if len(blob) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image too large (10 MB limit).")

    project = store.load(slug)
    location_norm = location.strip()
    if not location_norm:
        raise HTTPException(400, "Missing BOM location.")

    row = next(
        (b for b in project.bom if b.location.lower() == location_norm.lower()),
        None,
    )
    if row is None:
        raise HTTPException(
            404,
            f"BOM has no row for location {location_norm!r}.",
        )

    result = verify_component_photo(
        image_bytes=blob,
        image_media_type=content_type,
        expected_value=row.value,
        expected_type=row.type,
        expected_location=row.location,
        api_key=api_key,
    )

    return VerifyOut(
        verdict=result.verdict,
        explanation=result.explanation,
        guess_value=result.guess_value,
        guess_type=result.guess_type,
        expected_value=row.value,
        expected_type=row.type,
        location=row.location,
    )
