"""AI availability status endpoint.

Tells the frontend whether AI features will work, without exposing the
key itself. Returns one of:

- ``available=true, source="header"``: per-request key sent by the
  browser (BYOK — user has set one in Settings).
- ``available=true, source="env"``: ANTHROPIC_API_KEY in backend env
  (self-host pattern). Falls back to this when no header is sent.
- ``available=false, source=null``: nothing configured. AI features
  return errors / no-op.
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from pedal_bench.api.deps import get_request_api_key

router = APIRouter(prefix="/ai", tags=["ai"])


class AIStatusOut(BaseModel):
    available: bool
    source: Literal["header", "env"] | None


@router.get("/status", response_model=AIStatusOut)
def ai_status(
    api_key: str | None = Depends(get_request_api_key),
) -> AIStatusOut:
    if api_key:
        return AIStatusOut(available=True, source="header")
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AIStatusOut(available=True, source="env")
    return AIStatusOut(available=False, source=None)
