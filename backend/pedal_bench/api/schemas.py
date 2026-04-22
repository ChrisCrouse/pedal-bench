"""Pydantic schemas for the API transport layer.

Distinct from the core dataclasses in `pedal_bench.core.models` so we can
evolve the wire format and the domain model independently.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Status = Literal["planned", "ordered", "building", "finishing", "done"]
BuildPhase = Literal["pcb", "drill", "finish", "wiring", "test"]
Side = Literal["A", "B", "C", "D", "E"]
Tracking = Literal["per_value", "bucket"]
IconKind = Literal[
    "pot",
    "chicken-head",
    "footswitch",
    "toggle",
    "led",
    "jack",
    "dc-jack",
    "expression",
]


class FaceDimsOut(BaseModel):
    width_mm: float
    height_mm: float
    label: str


class EnclosureOut(BaseModel):
    key: str
    name: str
    length_mm: float
    width_mm: float
    height_mm: float
    wall_thickness_mm: float
    faces: dict[str, FaceDimsOut]
    notes: str = ""


class BOMItemIO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    location: str
    value: str
    type: str
    notes: str = ""
    quantity: int = 1
    polarity_sensitive: bool = False
    orientation_hint: str | None = None


class HoleIO(BaseModel):
    side: Side
    x_mm: float
    y_mm: float
    diameter_mm: float = Field(gt=0)
    label: str | None = None
    powder_coat_margin: bool = True
    icon: IconKind | None = None
    mirror_group: str | None = None
    mirror_x_flipped: bool = False
    mirror_y_flipped: bool = False
    mirror_ce_flipped: bool = False


class BuildProgressIO(BaseModel):
    soldered_locations: list[str] = []
    current_phase: BuildPhase = "pcb"
    phase_notes: dict[str, str] = {}


class ProjectOut(BaseModel):
    slug: str
    name: str
    status: Status
    enclosure: str = ""
    source_pdf: str | None = None
    bom: list[BOMItemIO] = []
    holes: list[HoleIO] = []
    progress: BuildProgressIO = BuildProgressIO()
    notes: str = ""
    refdes_map: dict[str, list[float]] = {}
    created_at: str
    updated_at: str


class ProjectSummary(BaseModel):
    slug: str
    name: str
    status: Status
    enclosure: str = ""
    updated_at: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    enclosure: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    status: Status | None = None
    enclosure: str | None = None
    notes: str | None = None


class HolesReplace(BaseModel):
    holes: list[HoleIO]


class TaydaParseIn(BaseModel):
    text: str = Field(min_length=1)


class STLExportOut(BaseModel):
    side: Side
    path: str
    size_bytes: int


class PhotoOut(BaseModel):
    filename: str
    url: str
    uploaded_at: str
    caption: str = ""
    size_bytes: int
