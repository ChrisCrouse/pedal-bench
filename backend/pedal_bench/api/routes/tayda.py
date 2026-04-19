"""/tayda — Tayda Box Tool coordinate parser.

Stateless text-in, holes-out. UI uses this in the paste dialog to preview
parsed coordinates before committing them to a project.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from pedal_bench.api.schemas import HoleIO, TaydaParseIn
from pedal_bench.io.tayda_import import TaydaParseError, parse_tayda_text

router = APIRouter(prefix="/tayda", tags=["tayda"])


@router.post("/parse", response_model=list[HoleIO])
def parse(payload: TaydaParseIn) -> list[HoleIO]:
    try:
        holes = parse_tayda_text(payload.text)
    except TaydaParseError as exc:
        raise HTTPException(400, str(exc))
    return [HoleIO(**h.to_dict()) for h in holes]
