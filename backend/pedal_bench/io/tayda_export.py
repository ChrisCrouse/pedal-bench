"""Push a pedal-bench drill layout into a Tayda Kits Box Designer draft.

Third-party integration using an UNDOCUMENTED API — may break without
notice. We reverse-engineered the payload shape from the network tab of
taydakits.com's online box drill tool:

    POST https://api.taydakits.com/api/v4/box_designs
    Authorization: Bearer <user-scoped token from their site>
    Content-Type: application/json

    {
      "name": "...",
      "enclosure_type": "125B",
      "is_public": 0,
      "is_archived": 0,
      "holes": [
        {"box_side": "A", "diameter": "3", "positionX": "0", "positionY": "0"},
        ...
      ],
      "lines": [],
      "shapes": []
    }

Coordinate convention: face-local mm, origin at face center, x+ right,
y+ up — identical to pedal-bench's Hole model (because both tools
converged on Tayda's convention). Values are sent as strings.

The token is per-user (BYOK, mirrors the Anthropic-key pattern). The
backend extracts it from ``X-Tayda-Token`` and forwards to Tayda without
persisting — same no-liability story as the Anthropic key.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from pedal_bench.core.models import Enclosure, Hole, Project

log = logging.getLogger(__name__)

TAYDA_ENDPOINT = "https://api.taydakits.com/api/v4/box_designs"
USER_AGENT = "pedal-bench/0.2 (+https://github.com/ChrisCrouse/pedal-bench)"
REQUEST_TIMEOUT = 30.0

# Tayda's tool supports these enclosure keys. Any pedal-bench project
# whose enclosure isn't in this set will produce a user-facing error
# rather than silently sending something Tayda will reject.
TAYDA_ENCLOSURES: frozenset[str] = frozenset(
    {"125B", "1590A", "1590B", "1590BB", "1590BB2", "1590DD", "1590XX", "1590N1"}
)


@dataclass(frozen=True)
class TaydaPushResult:
    """Outcome of a push attempt. ``design_url`` may be None if Tayda's
    response didn't include enough info to build one — we still show
    ``raw_response`` so users can see exactly what Tayda said."""

    design_id: str | None
    design_url: str | None
    status_code: int
    raw_response: Any  # JSON-decoded if possible, else str


class TaydaPushError(Exception):
    """User-presentable error. The message is safe to show verbatim."""

    def __init__(self, message: str, status_code: int = 0, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# -- Payload building (pure, unit-testable) ---------------------------------


def build_tayda_payload(
    project: Project,
    *,
    is_public: bool = False,
    name_override: str | None = None,
) -> dict[str, Any]:
    """Translate a Project into Tayda's box_designs POST body.

    Raises TaydaPushError if the project's enclosure isn't supported by
    Tayda's tool (rather than silently sending a request Tayda will reject
    with an unhelpful error).
    """
    enclosure_key = (project.enclosure or "").strip()
    if enclosure_key not in TAYDA_ENCLOSURES:
        raise TaydaPushError(
            f"Tayda's box tool doesn't support enclosure {enclosure_key!r}. "
            f"Supported: {', '.join(sorted(TAYDA_ENCLOSURES))}.",
        )

    name = (name_override or project.name or "pedal-bench").strip() or "pedal-bench"

    return {
        "name": name[:80],  # Tayda's UI shows a relatively short name
        "enclosure_type": enclosure_key,
        "is_public": 1 if is_public else 0,
        "is_archived": 0,
        "holes": [_hole_to_tayda(h) for h in project.holes],
        "lines": [],
        "shapes": [],
    }


def _hole_to_tayda(hole: Hole) -> dict[str, str]:
    """Single hole → Tayda's shape. Values are strings per their API."""
    return {
        "box_side": hole.side,
        "diameter": _fmt_number(hole.diameter_mm),
        "positionX": _fmt_number(hole.x_mm),
        "positionY": _fmt_number(hole.y_mm),
    }


def _fmt_number(n: float) -> str:
    """Format a number cleanly: '3' not '3.0', '4.5' not '4.500000'."""
    if n == int(n):
        return str(int(n))
    # Trim trailing zeros but keep at least one digit after the point.
    return f"{n:.4f}".rstrip("0").rstrip(".")


# -- Push (network-bound, mocked in tests) ----------------------------------


def push_to_tayda(payload: dict[str, Any], bearer_token: str) -> TaydaPushResult:
    """POST the payload to Tayda's box_designs endpoint.

    Raises TaydaPushError on any non-2xx response, with Tayda's response
    body attached so the frontend can show the user exactly what Tayda
    complained about.
    """
    if not bearer_token or not bearer_token.strip():
        raise TaydaPushError("No Tayda API token provided.", status_code=401)

    # Tayda's endpoint is a Rails API that normally receives calls from
    # their own SPA. Missing Origin/Referer has been observed to trigger
    # 500s rather than clean 4xx errors — include them so the controller
    # doesn't crash before it can tell us what's actually wrong.
    headers = {
        "Authorization": f"Bearer {bearer_token.strip()}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.taydakits.com",
        "Referer": "https://www.taydakits.com/",
        "User-Agent": USER_AGENT,
    }

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.post(TAYDA_ENDPOINT, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise TaydaPushError(f"Timed out talking to Tayda: {exc}") from exc
    except httpx.HTTPError as exc:
        raise TaydaPushError(f"Network error talking to Tayda: {exc}") from exc

    # Try to parse body as JSON; fall back to raw text for error surfacing.
    try:
        body: Any = resp.json()
    except Exception:
        body = resp.text

    if resp.status_code < 200 or resp.status_code >= 300:
        raise TaydaPushError(
            _summarize_error(resp.status_code, body),
            status_code=resp.status_code,
            body=body,
        )

    design_id = _extract_design_id(body)
    design_url = _build_design_url(design_id) if design_id else None

    return TaydaPushResult(
        design_id=design_id,
        design_url=design_url,
        status_code=resp.status_code,
        raw_response=body,
    )


def _extract_design_id(body: Any) -> str | None:
    """Best-effort extraction of the new design's ID from Tayda's response.

    We don't know the exact field name for sure (we only have the request
    shape, not a successful response). Try the plausible options and
    degrade gracefully — even without an ID, the push itself succeeded.
    """
    if not isinstance(body, dict):
        return None
    for key in ("id", "design_id", "uuid", "slug"):
        v = body.get(key)
        if v:
            return str(v)
    # Some REST APIs nest the created object under "data" or similar.
    nested = body.get("data")
    if isinstance(nested, dict):
        for key in ("id", "design_id", "uuid", "slug"):
            v = nested.get(key)
            if v:
                return str(v)
    return None


def _build_design_url(design_id: str) -> str:
    # Educated guess at Tayda's public-facing URL for a saved design.
    # If Tayda's actual URL pattern differs, users can still find the
    # design via their account page — the ID is shown in our UI regardless.
    return f"https://www.taydakits.com/box-designer/{design_id}"


def _summarize_error(status: int, body: Any) -> str:
    if status == 401:
        return "Tayda rejected the token (401). Check it in Settings — it may have expired."
    if status == 403:
        return "Tayda returned 403 — the token is valid but lacks permission for this action."
    if status == 404:
        return "Tayda returned 404 — the box_designs endpoint may have moved."
    if status == 422 or status == 400:
        return f"Tayda rejected the payload ({status}). Details below."
    if 500 <= status < 600:
        return f"Tayda's server returned {status}. Try again in a moment."
    return f"Tayda returned HTTP {status}."


__all__ = [
    "TAYDA_ENCLOSURES",
    "TaydaPushError",
    "TaydaPushResult",
    "build_tayda_payload",
    "push_to_tayda",
]
