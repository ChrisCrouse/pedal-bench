"""Core data model for the DIY pedal build assistant.

All user data persists as JSON. Every dataclass here defines `to_dict` and
`from_dict` so persistence is explicit (not reflection-based) — keeps the
on-disk format stable when fields evolve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

Status = Literal["planned", "ordered", "building", "finishing", "done"]
BuildPhase = Literal["pcb", "drill", "finish", "wiring", "test"]
Side = Literal["A", "B", "C", "D", "E"]

VALID_STATUS: tuple[Status, ...] = (
    "planned", "ordered", "building", "finishing", "done",
)
VALID_PHASE: tuple[BuildPhase, ...] = (
    "pcb", "drill", "finish", "wiring", "test",
)
VALID_SIDE: tuple[Side, ...] = ("A", "B", "C", "D", "E")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# Strings in BOMItem.type that imply the part is orientation-sensitive
# during soldering. Match is case-insensitive substring.
_POLARITY_MARKERS = (
    "diode",
    "electrolytic",
    "transistor",
    "op-amp",
    "opamp",
    "operational amplifier",
    "led",
    "tantalum",
    "integrated circuit",
)


def is_polarity_sensitive(bom_type: str) -> bool:
    """Heuristically tag a BOM `type` string as orientation-sensitive.

    Exposed so UI code can recompute the flag when the user edits a Type cell.
    """
    t = bom_type.lower()
    return any(marker in t for marker in _POLARITY_MARKERS)


# Backwards-compat alias for the old private name used inside this module.
_is_polarity_sensitive = is_polarity_sensitive


@dataclass
class BOMItem:
    location: str
    value: str
    type: str
    notes: str = ""
    quantity: int = 1
    polarity_sensitive: bool = False
    orientation_hint: Optional[str] = None

    @classmethod
    def from_pdf_row(
        cls,
        location: str,
        value: str,
        type_: str,
        notes: str = "",
    ) -> "BOMItem":
        return cls(
            location=location.strip(),
            value=value.strip(),
            type=type_.strip(),
            notes=notes.strip(),
            polarity_sensitive=_is_polarity_sensitive(type_),
        )

    def to_dict(self) -> dict[str, Any]:
        d = {
            "location": self.location,
            "value": self.value,
            "type": self.type,
            "notes": self.notes,
            "quantity": self.quantity,
            "polarity_sensitive": self.polarity_sensitive,
        }
        if self.orientation_hint is not None:
            d["orientation_hint"] = self.orientation_hint
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BOMItem":
        return cls(
            location=d["location"],
            value=d["value"],
            type=d["type"],
            notes=d.get("notes", ""),
            quantity=int(d.get("quantity", 1)),
            polarity_sensitive=bool(d.get("polarity_sensitive", False)),
            orientation_hint=d.get("orientation_hint"),
        )


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
VALID_ICONS: tuple[IconKind, ...] = (
    "pot",
    "chicken-head",
    "footswitch",
    "toggle",
    "led",
    "jack",
    "dc-jack",
    "expression",
)


@dataclass
class Hole:
    side: Side
    x_mm: float
    y_mm: float
    diameter_mm: float
    label: Optional[str] = None
    powder_coat_margin: bool = True
    icon: Optional[IconKind] = None
    # Mirror-group linkage. When two or more holes share a mirror_group,
    # the UI keeps their positions in sync on drag. The three bool flags
    # describe this hole's relationship to the group's canonical seed:
    # mirror_x_flipped → x sign is negated relative to seed, etc.
    mirror_group: Optional[str] = None
    mirror_x_flipped: bool = False
    mirror_y_flipped: bool = False
    mirror_ce_flipped: bool = False

    def __post_init__(self) -> None:
        if self.side not in VALID_SIDE:
            raise ValueError(
                f"Hole.side must be one of {VALID_SIDE}, got {self.side!r}"
            )
        if self.diameter_mm <= 0:
            raise ValueError(f"Hole.diameter_mm must be positive, got {self.diameter_mm}")
        if self.icon is not None and self.icon not in VALID_ICONS:
            raise ValueError(
                f"Hole.icon must be one of {VALID_ICONS} or None, got {self.icon!r}"
            )

    def effective_diameter_mm(self) -> float:
        return self.diameter_mm + (0.4 if self.powder_coat_margin else 0.0)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "side": self.side,
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
            "diameter_mm": self.diameter_mm,
            "powder_coat_margin": self.powder_coat_margin,
        }
        if self.label is not None:
            d["label"] = self.label
        if self.icon is not None:
            d["icon"] = self.icon
        if self.mirror_group is not None:
            d["mirror_group"] = self.mirror_group
            if self.mirror_x_flipped:
                d["mirror_x_flipped"] = True
            if self.mirror_y_flipped:
                d["mirror_y_flipped"] = True
            if self.mirror_ce_flipped:
                d["mirror_ce_flipped"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Hole":
        icon = d.get("icon")
        if icon is not None and icon not in VALID_ICONS:
            # Ignore unknown icons rather than fail load — lets newer icon
            # values survive round-trip through older backends. Log-worthy.
            icon = None
        return cls(
            side=d["side"],
            x_mm=float(d["x_mm"]),
            y_mm=float(d["y_mm"]),
            diameter_mm=float(d["diameter_mm"]),
            label=d.get("label"),
            powder_coat_margin=bool(d.get("powder_coat_margin", True)),
            icon=icon,
            mirror_group=d.get("mirror_group"),
            mirror_x_flipped=bool(d.get("mirror_x_flipped", False)),
            mirror_y_flipped=bool(d.get("mirror_y_flipped", False)),
            mirror_ce_flipped=bool(d.get("mirror_ce_flipped", False)),
        )


@dataclass
class BuildProgress:
    soldered_locations: set[str] = field(default_factory=set)
    current_phase: BuildPhase = "pcb"
    phase_notes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "soldered_locations": sorted(self.soldered_locations),
            "current_phase": self.current_phase,
            "phase_notes": dict(self.phase_notes),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BuildProgress":
        phase = d.get("current_phase", "pcb")
        if phase not in VALID_PHASE:
            phase = "pcb"
        return cls(
            soldered_locations=set(d.get("soldered_locations", [])),
            current_phase=phase,
            phase_notes=dict(d.get("phase_notes", {})),
        )


@dataclass
class Project:
    slug: str
    name: str
    status: Status = "planned"
    enclosure: str = ""
    source_pdf: Optional[str] = None
    bom: list[BOMItem] = field(default_factory=list)
    holes: list[Hole] = field(default_factory=list)
    progress: BuildProgress = field(default_factory=BuildProgress)
    notes: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    # Per-component positions on the cached pcb_layout.png image.
    # Keyed by BOMItem.location (R1, C2, IC1, CLR, LEVEL, …).
    # Each value is [x_pct, y_pct] with 0 ≤ pct ≤ 1 in SVG orientation.
    # Set manually by the user via click-to-tag on the BOM tab.
    refdes_map: dict[str, list[float]] = field(default_factory=dict)
    # Pre-loaded Tayda Manufacturing Center drill-template URL captured at
    # import time. Both PedalPCB product pages and Taydakits instruction
    # pages link to drill.taydakits.com/box-designs/new?public_key=... — we
    # surface this on the Drill tab so users can order a custom-drilled
    # enclosure with one click instead of re-entering coordinates by hand.
    drill_tool_url: Optional[str] = None
    # Source identity captured at import time. Optional for backwards
    # compatibility with existing project JSON files.
    source_supplier: Optional[str] = None
    source_url: Optional[str] = None
    # When False, this project is excluded from the global shopping list.
    # Lets Chris stash future-build ideas without them inflating shortages.
    active: bool = True

    def touch(self) -> None:
        self.updated_at = now_iso()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "slug": self.slug,
            "name": self.name,
            "status": self.status,
            "enclosure": self.enclosure,
            "source_pdf": self.source_pdf,
            "bom": [b.to_dict() for b in self.bom],
            "holes": [h.to_dict() for h in self.holes],
            "progress": self.progress.to_dict(),
            "notes": self.notes,
            "refdes_map": {k: list(v) for k, v in self.refdes_map.items()},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "active": self.active,
        }
        if self.drill_tool_url is not None:
            d["drill_tool_url"] = self.drill_tool_url
        if self.source_supplier is not None:
            d["source_supplier"] = self.source_supplier
        if self.source_url is not None:
            d["source_url"] = self.source_url
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Project":
        status = d.get("status", "planned")
        if status not in VALID_STATUS:
            status = "planned"
        raw_refdes = d.get("refdes_map", {}) or {}
        refdes_map: dict[str, list[float]] = {}
        for k, v in raw_refdes.items():
            try:
                refdes_map[str(k)] = [float(v[0]), float(v[1])]
            except (TypeError, ValueError, IndexError):
                continue
        return cls(
            slug=d["slug"],
            name=d["name"],
            status=status,
            enclosure=d.get("enclosure", ""),
            source_pdf=d.get("source_pdf"),
            bom=[BOMItem.from_dict(x) for x in d.get("bom", [])],
            holes=[Hole.from_dict(x) for x in d.get("holes", [])],
            progress=BuildProgress.from_dict(d.get("progress", {})),
            notes=d.get("notes", ""),
            refdes_map=refdes_map,
            created_at=d.get("created_at", now_iso()),
            updated_at=d.get("updated_at", now_iso()),
            drill_tool_url=d.get("drill_tool_url"),
            source_supplier=d.get("source_supplier"),
            source_url=d.get("source_url"),
            active=bool(d.get("active", True)),
        )


def inventory_key(kind: str, value_norm: str) -> str:
    """Canonical join key — must match how BOM rows are classified."""
    return f"{kind}::{value_norm}"


@dataclass
class InventoryItem:
    """A single physical-stock entry in the global inventory.

    Identity is `(kind, value_norm)`, encoded as `key = "<kind>::<value_norm>"`.
    Reservations are integer holds tied to a project slug — `available` is
    `on_hand - sum(reservations.values())`. Reservations are always manual:
    the user clicks "reserve for this build" and later "consume" to draw down.
    """

    key: str
    kind: str
    value_norm: str
    on_hand: int
    reservations: dict[str, int] = field(default_factory=dict)
    display_value: str = ""
    supplier: Optional[str] = None
    unit_cost_usd: Optional[float] = None
    notes: str = ""

    def __post_init__(self) -> None:
        # on_hand may be negative — see solder_consumption.apply_solder_delta
        # for the case where the bench tab pulls more parts than were tracked.
        # A negative value means "the database thinks you've used N more than
        # you logged" and serves as a visible deficit until you restock.
        if not isinstance(self.on_hand, int):
            raise ValueError(f"on_hand must be an int, got {type(self.on_hand).__name__}")
        for slug, qty in self.reservations.items():
            if not isinstance(qty, int) or qty < 0:
                raise ValueError(
                    f"reservation for {slug!r} must be non-negative int, got {qty!r}"
                )

    @property
    def reserved_total(self) -> int:
        return sum(self.reservations.values())

    @property
    def available(self) -> int:
        return max(0, self.on_hand - self.reserved_total)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "key": self.key,
            "kind": self.kind,
            "value_norm": self.value_norm,
            "on_hand": self.on_hand,
            "reservations": dict(self.reservations),
        }
        if self.display_value:
            d["display_value"] = self.display_value
        if self.supplier is not None:
            d["supplier"] = self.supplier
        if self.unit_cost_usd is not None:
            d["unit_cost_usd"] = self.unit_cost_usd
        if self.notes:
            d["notes"] = self.notes
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InventoryItem":
        # Migration: old records had `tracking` ("per_value" or "bucket") and
        # could store on_hand as a string ("plenty"/"low"/"out"). Drop the
        # mode and coerce non-int on_hand to 0 so legacy bucket items become
        # editable rather than crashing the load.
        raw_on_hand = d.get("on_hand", 0)
        on_hand = raw_on_hand if isinstance(raw_on_hand, int) else 0
        notes = d.get("notes", "")
        if not isinstance(raw_on_hand, int):
            note_msg = f"(migrated from bucket level {raw_on_hand!r})"
            notes = f"{notes} {note_msg}".strip()

        key = d["key"]
        kind = d.get("kind", "")
        value_norm = d.get("value_norm", "")
        # Migration: derive kind/value_norm from the legacy key format
        # ("kind:subtype:value", or just "kind:value"). We take the first
        # segment as kind and the last as value_norm. Imperfect but the user
        # can fix any oddballs in the UI; better than dropping data.
        if not kind or not value_norm:
            parts = key.split("::") if "::" in key else key.split(":")
            if len(parts) >= 2:
                kind = kind or parts[0]
                value_norm = value_norm or parts[-1]

        return cls(
            key=key,
            kind=kind,
            value_norm=value_norm,
            on_hand=on_hand,
            reservations={k: int(v) for k, v in (d.get("reservations") or {}).items()},
            display_value=d.get("display_value", ""),
            supplier=d.get("supplier"),
            unit_cost_usd=d.get("unit_cost_usd"),
            notes=notes,
        )


@dataclass(frozen=True)
class FaceDims:
    width_mm: float
    height_mm: float
    label: str


@dataclass(frozen=True)
class Enclosure:
    """Read-only enclosure spec loaded from app/data/enclosures.json."""

    key: str                           # "125B"
    name: str                          # "Hammond 125B (1590N1)"
    length_mm: float
    width_mm: float
    height_mm: float
    wall_thickness_mm: float
    faces: dict[Side, FaceDims]
    notes: str = ""

    @classmethod
    def from_json(cls, key: str, entry: dict[str, Any]) -> "Enclosure":
        outer = entry["outer_mm"]
        faces: dict[Side, FaceDims] = {}
        for side_key, face_entry in entry.get("faces", {}).items():
            if side_key not in VALID_SIDE:
                raise ValueError(f"Unknown side key {side_key!r} for enclosure {key!r}")
            faces[side_key] = FaceDims(  # type: ignore[index]
                width_mm=float(face_entry["width_mm"]),
                height_mm=float(face_entry["height_mm"]),
                label=face_entry.get("label", side_key),
            )
        return cls(
            key=key,
            name=entry.get("name", key),
            length_mm=float(outer["length"]),
            width_mm=float(outer["width"]),
            height_mm=float(outer["height"]),
            wall_thickness_mm=float(entry.get("wall_thickness_mm", 2.5)),
            faces=faces,
            notes=entry.get("notes", ""),
        )

    def face(self, side: Side) -> FaceDims:
        if side not in self.faces:
            raise KeyError(f"Enclosure {self.key!r} has no face {side!r}")
        return self.faces[side]
