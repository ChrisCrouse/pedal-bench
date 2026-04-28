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
    drill_tool_url: str | None = None
    source_supplier: str | None = None
    source_url: str | None = None
    active: bool = True


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
    active: bool | None = None


class HolesReplace(BaseModel):
    holes: list[HoleIO]


class TaydaParseIn(BaseModel):
    text: str = Field(min_length=1)


TemplateMode = Literal["pilot", "mark", "full"]


class STLExportIn(BaseModel):
    """Optional STL export options. All fields default to sensible values
    so existing clients can POST an empty body.
    """

    template_mode: TemplateMode = "pilot"
    pilot_diameter_mm: float = Field(default=3.0, gt=0, le=10.0)
    show_final_size_ring: bool = True


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


class InventoryItemIn(BaseModel):
    """Body for creating or updating a single owned-stock entry.

    `kind` and `value` together identify the part. The server normalizes
    `value` (e.g. "100K Ohm" → "100k") before storing — clients can send
    the raw string from the UI.
    """

    kind: str = Field(min_length=1)
    value: str = Field(min_length=1)
    on_hand: int = Field(ge=0)
    display_value: str = ""
    supplier: str | None = None
    unit_cost_usd: float | None = Field(default=None, ge=0)
    notes: str = ""


class InventoryItemPatch(BaseModel):
    on_hand: int | None = Field(default=None, ge=0)
    display_value: str | None = None
    supplier: str | None = None
    unit_cost_usd: float | None = Field(default=None, ge=0)
    notes: str | None = None


class InventoryItemOut(BaseModel):
    key: str
    kind: str
    value_norm: str
    value_magnitude: float | None = None
    display_value: str
    on_hand: int
    reservations: dict[str, int]
    reserved_total: int
    available: int
    supplier: str | None = None
    unit_cost_usd: float | None = None
    notes: str = ""


class ReservationIn(BaseModel):
    slug: str = Field(min_length=1)
    qty: int = Field(ge=0)


class ShortageRowOut(BaseModel):
    kind: str
    value_norm: str
    value_magnitude: float | None = None
    display_value: str
    type_hint: str
    needed: int
    on_hand: int
    reserved_for_others: int
    reserved_for_self: int
    available: int
    shortfall: int
    unit_cost_usd: float | None = None
    supplier: str | None = None
    needed_by: list[str]


class ShortageOut(BaseModel):
    rows: list[ShortageRowOut]
    estimated_total_cost_usd: float | None = None


class ConsumeReservationsOut(BaseModel):
    consumed: list[tuple[str, int]]


class ProgressUpdateOut(BaseModel):
    """Response from PUT /projects/{slug}/progress.

    Carries the canonical progress plus the inventory side-effects so the
    UI can surface "two parts came off stock" or "10k stock was 0" hints
    without a follow-up fetch.
    """

    progress: BuildProgressIO
    consumed: list[tuple[str, int]] = []
    restored: list[tuple[str, int]] = []
    warnings: list[str] = []
