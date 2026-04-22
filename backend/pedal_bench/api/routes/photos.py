"""Build-log photos per project.

Layout:
  projects/<slug>/photos/<timestamp>__<sanitized-name>.<ext>
  projects/<slug>/photos/captions.json   # { filename -> caption }

No schema change on Project: photo metadata is derived from listing the
directory and reading the sidecar captions file.

Endpoints (all under /api/v1/projects/{slug}/photos):
  GET     /                          list photos (newest first)
  POST    /                          upload (multipart; accepts caption form field)
  GET     /{filename}                serve the image file
  PATCH   /{filename}                update caption
  DELETE  /{filename}                remove file + caption entry
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pedal_bench.api.deps import get_project_store
from pedal_bench.api.schemas import PhotoOut
from pedal_bench.core.project_store import ProjectStore

router = APIRouter(prefix="/projects/{slug}/photos", tags=["photos"])

CAPTIONS_FILE = "captions.json"

# Accept jpeg / png / webp. Keys are content-types; values are file extensions.
ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/pjpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

MEDIA_TYPES: dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

_TIMESTAMP_RE = re.compile(r"^(\d{8}T\d{6}Z)__")
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


class CaptionIn(BaseModel):
    caption: str = Field(default="", max_length=500)


def _validate_filename(filename: str) -> None:
    """Reject anything that could escape the photos directory."""
    if not filename:
        raise HTTPException(400, "Missing filename.")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename.")
    if filename in {".", CAPTIONS_FILE}:
        raise HTTPException(400, "Invalid filename.")


def _load_captions(photos_path: Path) -> dict[str, str]:
    cap_file = photos_path / CAPTIONS_FILE
    if not cap_file.is_file():
        return {}
    try:
        with open(cap_file, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_captions(photos_path: Path, captions: dict[str, str]) -> None:
    cap_file = photos_path / CAPTIONS_FILE
    tmp = cap_file.with_suffix(cap_file.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(captions, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    tmp.replace(cap_file)


def _photo_out(slug: str, path: Path, captions: dict[str, str]) -> PhotoOut:
    name = path.name
    uploaded_at = _parse_timestamp(name) or _mtime_iso(path)
    return PhotoOut(
        filename=name,
        url=f"/api/v1/projects/{slug}/photos/{name}",
        uploaded_at=uploaded_at,
        caption=captions.get(name, ""),
        size_bytes=path.stat().st_size,
    )


def _parse_timestamp(filename: str) -> str | None:
    """Parse our compact-UTC prefix back into an ISO-8601 string."""
    m = _TIMESTAMP_RE.match(filename)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None
    return dt.isoformat()


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _now_stamp() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sanitize(name: str) -> str:
    """Strip path noise, collapse unsafe chars, cap length."""
    stem = Path(name).stem or "photo"
    safe = _SAFE_NAME.sub("-", stem).strip("-._")
    if not safe:
        safe = "photo"
    return safe[:60]


def _list_photos(photos_path: Path) -> list[Path]:
    if not photos_path.is_dir():
        return []
    results: list[Path] = []
    for p in photos_path.iterdir():
        if not p.is_file():
            continue
        if p.name == CAPTIONS_FILE:
            continue
        if p.suffix.lower().lstrip(".") not in MEDIA_TYPES:
            continue
        results.append(p)
    return results


@router.get("", response_model=list[PhotoOut])
def list_photos(
    slug: str,
    store: ProjectStore = Depends(get_project_store),
) -> list[PhotoOut]:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    photos_path = store.photos_dir(slug)
    captions = _load_captions(photos_path)
    entries = [_photo_out(slug, p, captions) for p in _list_photos(photos_path)]
    entries.sort(key=lambda e: e.uploaded_at, reverse=True)
    return entries


@router.post("", response_model=PhotoOut, status_code=201)
async def upload_photo(
    slug: str,
    file: Annotated[UploadFile, File()],
    caption: Annotated[str, Form()] = "",
    store: ProjectStore = Depends(get_project_store),
) -> PhotoOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")

    content_type = (file.content_type or "").lower()
    ext = ALLOWED_TYPES.get(content_type)
    if ext is None:
        # Fall back on extension sniffing if the browser sent a bad Content-Type.
        raw_ext = Path(file.filename or "").suffix.lower().lstrip(".")
        if raw_ext in MEDIA_TYPES:
            ext = "jpg" if raw_ext == "jpeg" else raw_ext
        else:
            raise HTTPException(400, f"Unsupported image type: {content_type!r}")

    blob = await file.read()
    if not blob:
        raise HTTPException(400, "Empty upload.")
    if len(blob) > 25 * 1024 * 1024:
        raise HTTPException(413, "Image too large (25 MB limit).")

    photos_path = store.photos_dir(slug)
    filename = f"{_now_stamp()}__{_sanitize(file.filename or 'photo')}.{ext}"
    dest = photos_path / filename
    # Collision guard (same-second uploads); append a counter.
    counter = 1
    while dest.exists():
        filename = f"{_now_stamp()}__{_sanitize(file.filename or 'photo')}-{counter}.{ext}"
        dest = photos_path / filename
        counter += 1

    dest.write_bytes(blob)

    captions = _load_captions(photos_path)
    if caption:
        captions[filename] = caption[:500]
        _save_captions(photos_path, captions)

    return _photo_out(slug, dest, captions)


@router.get("/{filename}")
def serve_photo(
    slug: str,
    filename: str,
    store: ProjectStore = Depends(get_project_store),
) -> FileResponse:
    _validate_filename(filename)
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    photos_path = store.photos_dir(slug)
    path = photos_path / filename
    if not path.is_file():
        raise HTTPException(404, "Photo not found.")
    ext = path.suffix.lower().lstrip(".")
    return FileResponse(path, media_type=MEDIA_TYPES.get(ext, "application/octet-stream"))


@router.patch("/{filename}", response_model=PhotoOut)
def update_caption(
    slug: str,
    filename: str,
    payload: CaptionIn,
    store: ProjectStore = Depends(get_project_store),
) -> PhotoOut:
    _validate_filename(filename)
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    photos_path = store.photos_dir(slug)
    path = photos_path / filename
    if not path.is_file():
        raise HTTPException(404, "Photo not found.")

    captions = _load_captions(photos_path)
    new_caption = payload.caption.strip()[:500]
    if new_caption:
        captions[filename] = new_caption
    else:
        captions.pop(filename, None)
    _save_captions(photos_path, captions)
    return _photo_out(slug, path, captions)


@router.delete("/{filename}")
def delete_photo(
    slug: str,
    filename: str,
    store: ProjectStore = Depends(get_project_store),
) -> dict[str, bool]:
    _validate_filename(filename)
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    photos_path = store.photos_dir(slug)
    path = photos_path / filename
    if not path.is_file():
        raise HTTPException(404, "Photo not found.")

    path.unlink()
    captions = _load_captions(photos_path)
    if filename in captions:
        captions.pop(filename)
        _save_captions(photos_path, captions)
    return {"ok": True}
