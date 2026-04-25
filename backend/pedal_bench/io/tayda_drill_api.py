"""Fetch a drill template directly from the Tayda Manufacturing Center API.

When a build page (Taydakits instructions or PedalPCB product page) links to
``drill.taydakits.com/box-designs/new?public_key=<key>``, the SPA at that URL
loads its data from a public JSON endpoint:

    GET https://api.taydakits.com/api/v4/box_designs/new?public_key=<key>

The response carries every hole's side / diameter / x / y in millimeters —
the exact shape pedal-bench's `Hole` model uses. No OCR, no AI, no scraping.
This turns "Taydakits doesn't publish drill coords" into a one-step import.

The endpoint requires `Origin: https://drill.taydakits.com` and `Accept:
application/json` to avoid a 500. CORS allows it; we identify ourselves
politely via User-Agent.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import httpx

from pedal_bench.core.models import Hole, IconKind, Side, VALID_SIDE

USER_AGENT = "pedal-bench/0.2 (+https://github.com/ccrouse/pedal-bench)"
API_BASE = "https://api.taydakits.com/api/v4/box_designs/new"
REQUEST_TIMEOUT = 15.0


class TaydaDrillAPIError(Exception):
    """User-presentable error; the message is safe to show verbatim."""


def public_key_from_url(drill_tool_url: str) -> str | None:
    """Pull the public_key query param from a drill.taydakits.com URL.

    Accepts both forms we've seen in the wild — the bare query string
    appended to ``/box-designs/new`` and any tracking suffix.
    """
    if not drill_tool_url:
        return None
    try:
        parsed = urlparse(drill_tool_url)
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    if "drill.taydakits.com" not in host:
        return None
    params = parse_qs(parsed.query)
    keys = params.get("public_key")
    if not keys:
        return None
    return keys[0] or None


def fetch_holes(drill_tool_url: str) -> list[Hole]:
    """Fetch the hole list from the public Tayda API. Returns [] if the URL
    isn't a drill-tool URL or doesn't carry a public_key. Raises
    TaydaDrillAPIError on network/parse failure."""
    public_key = public_key_from_url(drill_tool_url)
    if not public_key:
        return []

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        # Required — without an Origin header from the drill subdomain the
        # API responds 500. CORS on the API explicitly allows any origin,
        # so this is a deliberate gate, not a security boundary.
        "Origin": "https://drill.taydakits.com",
        "Referer": "https://drill.taydakits.com/",
    }
    params = {"public_key": public_key}

    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers=headers,
            follow_redirects=True,
        ) as client:
            resp = client.get(API_BASE, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.TimeoutException as exc:
        raise TaydaDrillAPIError(
            f"Timed out fetching Tayda drill data: {exc}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise TaydaDrillAPIError(
            f"Tayda drill API returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise TaydaDrillAPIError(
            f"Network error fetching Tayda drill data: {exc}"
        ) from exc
    except ValueError as exc:
        raise TaydaDrillAPIError(
            f"Tayda drill API returned non-JSON: {exc}"
        ) from exc

    return _parse_box_design(payload)


def _parse_box_design(payload: dict) -> list[Hole]:
    """Materialize {box_design: {box_design_holes: [...]}} into Hole objects.

    Drops malformed rows silently rather than failing the whole import —
    one bad row in the middle shouldn't lose the rest of the template.
    """
    if not isinstance(payload, dict):
        return []
    box = payload.get("box_design")
    if not isinstance(box, dict):
        return []
    raw_holes = box.get("box_design_holes")
    if not isinstance(raw_holes, list):
        return []

    holes: list[Hole] = []
    for raw in raw_holes:
        if not isinstance(raw, dict):
            continue
        try:
            side_raw = (raw.get("box_side") or "").strip().upper()
            if side_raw not in VALID_SIDE:
                continue
            side: Side = side_raw  # type: ignore[assignment]
            x_mm = float(raw["position_x"])
            y_mm = float(raw["position_y"])
            d_mm = float(raw["diameter"])
            if d_mm <= 0 or d_mm > 40:
                continue
            icon = _icon_from_diameter(side, d_mm)
            holes.append(
                Hole(
                    side=side,
                    x_mm=round(x_mm, 2),
                    y_mm=round(y_mm, 2),
                    diameter_mm=round(d_mm, 2),
                    label=_default_label(icon),
                    powder_coat_margin=True,
                    icon=icon,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    return holes


# Mirrors the heuristic in drill_template_extract.py so AI-extracted, PDF-
# vector-extracted, and Tayda-API-extracted holes all classify the same way.
def _icon_from_diameter(side: Side, diameter_mm: float) -> IconKind:
    if side == "A":
        if diameter_mm >= 10.5:
            return "footswitch"
        if diameter_mm <= 5.5:
            return "led"
        if diameter_mm <= 6.5:
            return "toggle"
        return "pot"
    if side == "B":
        if diameter_mm <= 8.5:
            return "dc-jack"
        return "jack"
    return "jack"


def _default_label(icon: IconKind) -> str | None:
    return {
        "pot": "POT",
        "led": "LED",
        "footswitch": "FOOTSWITCH",
        "jack": "JACK",
        "dc-jack": "DC",
        "toggle": "TOGGLE",
        "chicken-head": "KNOB",
        "expression": "EXP",
    }.get(icon)


__all__ = [
    "TaydaDrillAPIError",
    "fetch_holes",
    "public_key_from_url",
]
