"""Push a project's drill layout into a Tayda Kits Box Designer draft.

    POST /api/v1/projects/{slug}/tayda/push

Headers:
    X-Tayda-Token: <user's Tayda API token>

Body (optional):
    {
      "is_public": false,
      "name_override": "..."     # leaves project.name alone if absent
    }

The token is per-user, never persisted — same BYOK pattern as the
Anthropic key. Tayda's errors pass through verbatim on 4xx so the user
can see exactly what their server complained about; helpful since we're
calling an undocumented API and field-name drift is the main long-term
risk.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pedal_bench.api.deps import get_project_store, get_tayda_token
from pedal_bench.core.project_store import ProjectStore
from pedal_bench.io.tayda_export import (
    TaydaPushError,
    build_tayda_payload,
    push_to_tayda,
)

router = APIRouter(prefix="/projects/{slug}/tayda", tags=["tayda"])


class TaydaPushIn(BaseModel):
    is_public: bool = False
    name_override: str | None = Field(default=None, max_length=80)


class TaydaPushOut(BaseModel):
    design_id: str | None
    design_url: str | None
    status_code: int
    tayda_response: dict | list | str | int | float | bool | None


@router.post("/push", response_model=TaydaPushOut)
def push_project_to_tayda(
    slug: str,
    payload: TaydaPushIn | None = None,
    store: ProjectStore = Depends(get_project_store),
    token: str | None = Depends(get_tayda_token),
) -> TaydaPushOut:
    if not store.exists(slug):
        raise HTTPException(404, f"Unknown project {slug!r}")
    if not token:
        raise HTTPException(
            400,
            "No Tayda token — paste one into Settings to enable Send-to-Tayda.",
        )

    project = store.load(slug)
    if not project.holes:
        raise HTTPException(
            400,
            "This project has no holes to send. Place some on the Drill tab first.",
        )

    body = payload or TaydaPushIn()

    try:
        tayda_payload = build_tayda_payload(
            project,
            is_public=body.is_public,
            name_override=body.name_override,
        )
    except TaydaPushError as exc:
        # Configuration-style errors (unsupported enclosure): 400.
        raise HTTPException(400, str(exc)) from exc

    try:
        result = push_to_tayda(tayda_payload, token)
    except TaydaPushError as exc:
        # Forward Tayda's status + body verbatim so the frontend can show
        # the user exactly what Tayda complained about. Echo our sent
        # payload too — if Tayda's error is unhelpful (e.g. a bare 500),
        # the user can compare what we sent vs. a known-good capture.
        status = exc.status_code or 502
        detail = {
            "message": str(exc),
            "tayda_status": exc.status_code,
            "tayda_body": exc.body,
            "sent_payload": tayda_payload,
        }
        raise HTTPException(status_code=_client_status(status), detail=detail) from exc

    return TaydaPushOut(
        design_id=result.design_id,
        design_url=result.design_url,
        status_code=result.status_code,
        tayda_response=result.raw_response if isinstance(
            result.raw_response, (dict, list, str, int, float, bool, type(None))
        ) else str(result.raw_response),
    )


def _client_status(tayda_status: int) -> int:
    """Map a Tayda status to what we return to our frontend.

    Auth failures (401/403) pass through so the UI can prompt the user to
    re-check their token. Everything else → 502 Bad Gateway, which is the
    correct shape: our upstream failed, not our server.
    """
    if tayda_status in (401, 403):
        return tayda_status
    return 502
