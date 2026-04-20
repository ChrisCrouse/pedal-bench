"""/layout-presets — drill-layout preset library + snap-guide sets.

Read-only catalog shipped as JSON in app/data/layout_presets.json. Lazily
loaded and lru-cached. Frontend fetches this once and caches in-memory;
presets declare which enclosure they apply to, so the UI hides options
that don't fit the project's current enclosure.
"""

from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel

from pedal_bench import config
from pedal_bench.api.schemas import HoleIO

router = APIRouter(prefix="/layout-presets", tags=["layout-presets"])


class SnapGuide(BaseModel):
    vertical_lines_mm: list[float] = []
    horizontal_lines_mm: list[float] = []


class Preset(BaseModel):
    id: str
    enclosure: str
    category: str            # "jacks" | "controls" | "combined"
    name: str
    description: str = ""
    holes: list[HoleIO]


class LayoutPresetsOut(BaseModel):
    presets: list[Preset]
    snap_guides: dict[str, dict[str, SnapGuide]]


@lru_cache(maxsize=1)
def _load() -> LayoutPresetsOut:
    path = config.DATA_DIR / "layout_presets.json"
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    snap_raw = {
        k: v for k, v in raw.get("snap_guides", {}).items() if not k.startswith("_")
    }
    snap: dict[str, dict[str, SnapGuide]] = {}
    for encl_key, faces in snap_raw.items():
        snap[encl_key] = {side: SnapGuide(**g) for side, g in faces.items()}
    presets = [Preset(**p) for p in raw.get("presets", [])]
    return LayoutPresetsOut(presets=presets, snap_guides=snap)


@router.get("", response_model=LayoutPresetsOut)
def get_layout_presets() -> LayoutPresetsOut:
    return _load()
