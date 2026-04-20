"""/debug — seed dataset for the debug helper.

Read-only catalog of expected pin voltages for common pedal ICs, plus
a universal audio-probe procedure and a common-failure triage table.
"""

from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel

from pedal_bench import config

router = APIRouter(prefix="/debug", tags=["debug"])


class Pin(BaseModel):
    pin: int
    name: str
    expected_v: float | None = None
    tolerance_v: float | None = None


class DebugIC(BaseModel):
    key: str
    description: str
    family: str
    package: str
    common_in: list[str] = []
    pins: list[Pin]


class CommonFailure(BaseModel):
    symptom: str
    likely_causes: list[str]


class DebugSupply(BaseModel):
    vcc_v: float
    vref_v: float
    vref_tolerance_v: float


class DebugDataset(BaseModel):
    supply: DebugSupply
    ics: list[DebugIC]
    audio_probe_procedure: list[str]
    common_failures: list[CommonFailure]


@lru_cache(maxsize=1)
def _load_dataset() -> DebugDataset:
    path = config.DATA_DIR / "debug_topologies.json"
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    ics = [
        DebugIC(key=k, **{kk: vv for kk, vv in v.items() if not kk.startswith("_")})
        for k, v in raw["ics"].items()
    ]
    return DebugDataset(
        supply=DebugSupply(**raw["supply"]),
        ics=ics,
        audio_probe_procedure=raw["audio_probe_procedure"],
        common_failures=[CommonFailure(**c) for c in raw["common_failures"]],
    )


@router.get("/dataset", response_model=DebugDataset)
def get_debug_dataset() -> DebugDataset:
    return _load_dataset()
