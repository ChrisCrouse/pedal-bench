"""/enclosures — read-only catalog of Hammond enclosures."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pedal_bench.api.deps import get_enclosure_catalog
from pedal_bench.api.schemas import EnclosureOut, FaceDimsOut
from pedal_bench.core.models import Enclosure

router = APIRouter(prefix="/enclosures", tags=["enclosures"])


def _to_out(encl: Enclosure) -> EnclosureOut:
    return EnclosureOut(
        key=encl.key,
        name=encl.name,
        length_mm=encl.length_mm,
        width_mm=encl.width_mm,
        height_mm=encl.height_mm,
        wall_thickness_mm=encl.wall_thickness_mm,
        faces={
            side: FaceDimsOut(
                width_mm=fd.width_mm,
                height_mm=fd.height_mm,
                label=fd.label,
            )
            for side, fd in encl.faces.items()
        },
        notes=encl.notes,
    )


@router.get("", response_model=list[EnclosureOut])
def list_enclosures(
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
) -> list[EnclosureOut]:
    return [_to_out(e) for e in catalog.values()]


@router.get("/{key}", response_model=EnclosureOut)
def get_enclosure(
    key: str,
    catalog: dict[str, Enclosure] = Depends(get_enclosure_catalog),
) -> EnclosureOut:
    if key not in catalog:
        raise HTTPException(404, f"Unknown enclosure {key!r}")
    return _to_out(catalog[key])
