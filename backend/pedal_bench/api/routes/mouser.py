"""Mouser Search API proxy routes.

Mouser doesn't allow CORS from arbitrary origins, so the browser sends its
BYOK key via X-Mouser-Key header and we forward the request server-side.
The key is never persisted — it lives in the user's browser localStorage
and rides on every Mouser-related fetch as a header.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pedal_bench.api.deps import get_mouser_key
from pedal_bench.io.mouser_lookup import (
    MouserAPIError,
    MouserMatch,
    search_keyword,
    search_part_numbers,
)

router = APIRouter(prefix="/mouser", tags=["mouser"])


class MouserMatchOut(BaseModel):
    mfr_part_number: str
    mouser_part_number: str
    manufacturer: str
    description: str
    in_stock: int
    availability_text: str
    lead_time: str | None
    lifecycle_status: str | None
    price_usd: float | None
    price_breaks: list[dict]
    product_url: str
    datasheet_url: str | None
    image_url: str | None

    @classmethod
    def from_match(cls, m: MouserMatch) -> "MouserMatchOut":
        return cls(**m.__dict__)


class KeywordSearchIn(BaseModel):
    keyword: str
    in_stock_only: bool = True
    records: int = 10


class PartNumberSearchIn(BaseModel):
    part_numbers: list[str]


@router.get("/status")
def status(api_key: str | None = Depends(get_mouser_key)) -> dict:
    """Tell the UI whether a key is configured.

    Mouser keys are per-user only (no env fallback), so source is always
    'header' or null.
    """
    return {"available": api_key is not None, "source": "header" if api_key else None}


@router.post("/search/keyword")
def keyword_search(
    payload: KeywordSearchIn,
    api_key: str | None = Depends(get_mouser_key),
) -> dict:
    if not api_key:
        raise HTTPException(
            400,
            "No Mouser API key. Add yours in Settings (free at mouser.com/api-hub/).",
        )
    try:
        matches = search_keyword(
            api_key,
            payload.keyword,
            in_stock_only=payload.in_stock_only,
            records=payload.records,
        )
    except MouserAPIError as e:
        raise HTTPException(502, str(e)) from e
    return {"matches": [MouserMatchOut.from_match(m).model_dump() for m in matches]}


@router.post("/search/parts")
def parts_search(
    payload: PartNumberSearchIn,
    api_key: str | None = Depends(get_mouser_key),
) -> dict:
    if not api_key:
        raise HTTPException(
            400,
            "No Mouser API key. Add yours in Settings (free at mouser.com/api-hub/).",
        )
    if not payload.part_numbers:
        return {"results": {}}
    try:
        grouped = search_part_numbers(api_key, payload.part_numbers)
    except MouserAPIError as e:
        raise HTTPException(502, str(e)) from e
    return {
        "results": {
            mpn: [MouserMatchOut.from_match(m).model_dump() for m in matches]
            for mpn, matches in grouped.items()
        }
    }
