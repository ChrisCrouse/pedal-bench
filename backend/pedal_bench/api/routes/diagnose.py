"""AI diagnosis endpoint for a specific project.

Combines the debug dataset (power supply, per-IC expected pin voltages),
the project's BOM, and optionally the cached wiring-diagram image, then
asks Claude to reason over it all and return a structured diagnosis.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pedal_bench.api.deps import get_project_store, get_request_api_key
from pedal_bench.api.routes.debug import _load_dataset
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.io.ai_diagnose import PinReading, diagnose

router = APIRouter(prefix="/projects/{slug}/debug", tags=["diagnose"])


class ReadingIn(BaseModel):
    pin: int
    measured_v: float | None = None


class DiagnoseIn(BaseModel):
    symptom: str = Field(min_length=1, max_length=500)
    selected_ic: str | None = None
    readings: list[ReadingIn] = Field(default_factory=list)
    include_wiring_image: bool = True


class DiagnoseOut(BaseModel):
    primary_suspect: str
    reasoning: str
    next_probe: str
    confidence: str
    alternative_suspects: list[str] = []
    caveats: list[str] = []
    used_wiring_image: bool


def _bom_highlights(project) -> list[str]:
    """Pick out rows worth surfacing to the model: polarity-sensitive parts,
    ICs, transistors — the usual suspects in debug sessions."""
    out: list[str] = []
    for row in project.bom:
        t = (row.type or "").lower()
        interesting = (
            row.polarity_sensitive
            or "transistor" in t
            or "ic" in t
            or "op-amp" in t
            or "opamp" in t
            or "diode" in t
        )
        if interesting and row.location and row.value:
            out.append(f"{row.location}: {row.value} ({row.type})")
    return out


@router.post("/diagnose", response_model=DiagnoseOut)
def diagnose_project(
    slug: str,
    payload: DiagnoseIn,
    store: ProjectStore = Depends(get_project_store),
    api_key: str | None = Depends(get_request_api_key),
) -> DiagnoseOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    project = store.load(slug)
    dataset = _load_dataset()

    # Resolve the IC row from the dataset so we can annotate the readings
    # with name + expected + tolerance for the model's convenience.
    selected_ic_record = None
    if payload.selected_ic:
        selected_ic_record = next(
            (ic for ic in dataset.ics if ic.key == payload.selected_ic), None
        )

    pin_readings: list[PinReading] = []
    if selected_ic_record:
        by_pin = {p.pin: p for p in selected_ic_record.pins}
        for r in payload.readings:
            spec = by_pin.get(r.pin)
            if spec is None:
                continue
            pin_readings.append(
                PinReading(
                    pin=r.pin,
                    name=spec.name,
                    expected_v=spec.expected_v,
                    tolerance_v=spec.tolerance_v,
                    measured_v=r.measured_v,
                )
            )
    else:
        # No selected IC; pass raw measurements so the model still has data.
        for r in payload.readings:
            pin_readings.append(
                PinReading(
                    pin=r.pin,
                    name=f"pin {r.pin}",
                    expected_v=None,
                    tolerance_v=None,
                    measured_v=r.measured_v,
                )
            )

    wiring_image_arg = None
    used_wiring_image = False
    if payload.include_wiring_image:
        wiring_path: Path = store.project_dir(slug) / "wiring.png"
        if wiring_path.is_file():
            try:
                wiring_image_arg = (wiring_path.read_bytes(), "image/png")
                used_wiring_image = True
            except OSError:
                wiring_image_arg = None

    result = diagnose(
        symptom=payload.symptom,
        supply_vcc_v=dataset.supply.vcc_v,
        supply_vref_v=dataset.supply.vref_v,
        selected_ic=payload.selected_ic,
        readings=pin_readings,
        wiring_image=wiring_image_arg,
        project_name=project.name,
        bom_highlights=_bom_highlights(project),
        api_key=api_key,
    )

    return DiagnoseOut(
        primary_suspect=result.primary_suspect,
        reasoning=result.reasoning,
        next_probe=result.next_probe,
        confidence=result.confidence,
        alternative_suspects=result.alternative_suspects,
        caveats=result.caveats,
        used_wiring_image=used_wiring_image,
    )
