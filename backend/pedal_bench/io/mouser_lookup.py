"""Mouser Search API client + small in-process cache.

Mouser caps free Search API keys at 30 req/min and 1000 req/day, so we cache
hits aggressively (per-key, in-process, 6-hour TTL). The cache is a plain
dict — restart the server and it's fresh, which is fine because the BOM tab
re-fetches lazily on demand.

Per Mouser's Search API ToS, keys are per-user and cannot be shared. The
key always comes from the request (X-Mouser-Key header) — never from env.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx


_BASE = "https://api.mouser.com/api/v1"
_TIMEOUT = 10.0
_CACHE_TTL_S = 6 * 3600


@dataclass
class MouserMatch:
    """One product result, normalized for the BOM tab."""
    mfr_part_number: str
    mouser_part_number: str
    manufacturer: str
    description: str
    in_stock: int                # parsed int, 0 if unknown
    availability_text: str       # "15,243 In Stock" or "Lead time: 42 Days"
    lead_time: str | None        # "42 Days" or None
    lifecycle_status: str | None # "Active" / "EOL" / "NRND" / None
    price_usd: float | None      # cheapest unit price for qty>=1
    price_breaks: list[dict]     # [{"qty": 1, "price": 0.66}, ...]
    product_url: str             # ProductDetailUrl, opens in browser
    datasheet_url: str | None
    image_url: str | None


@dataclass
class MouserError:
    code: str
    message: str


# --- cache ------------------------------------------------------------------
_cache_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[float, list[MouserMatch]]] = {}


def _cache_get(key: tuple[str, str]) -> list[MouserMatch] | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        ts, matches = entry
        if time.time() - ts > _CACHE_TTL_S:
            del _cache[key]
            return None
        return matches


def _cache_put(key: tuple[str, str], matches: list[MouserMatch]) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), matches)


def clear_cache() -> None:
    """For tests."""
    with _cache_lock:
        _cache.clear()


# --- response parsing -------------------------------------------------------

_PRICE_RE = re.compile(r"[\d.]+")


def _parse_price(s: str) -> float | None:
    """Mouser returns '$0.66' as a string. Strip currency, parse."""
    if not s:
        return None
    m = _PRICE_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _parse_int(s: str | None) -> int:
    if not s:
        return 0
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else 0


def _availability_text(in_stock: int, lead_time: str | None, lifecycle: str | None) -> str:
    if lifecycle and lifecycle.lower() in ("eol", "discontinued", "obsolete"):
        return "Discontinued"
    if in_stock > 0:
        return f"{in_stock:,} in stock"
    if lead_time:
        return f"Lead time: {lead_time}"
    return "Out of stock"


def _normalize_part(raw: dict[str, Any]) -> MouserMatch:
    """Map a Mouser Part dict to our MouserMatch."""
    breaks_raw = raw.get("PriceBreaks") or []
    breaks: list[dict] = []
    for b in breaks_raw:
        price = _parse_price(b.get("Price", ""))
        qty = b.get("Quantity")
        if price is not None and qty is not None:
            breaks.append({"qty": int(qty), "price": price})
    breaks.sort(key=lambda b: b["qty"])
    cheapest = breaks[0]["price"] if breaks else None

    in_stock = _parse_int(raw.get("AvailabilityInStock") or raw.get("Availability"))

    return MouserMatch(
        mfr_part_number=raw.get("ManufacturerPartNumber", "") or "",
        mouser_part_number=raw.get("MouserPartNumber", "") or "",
        manufacturer=raw.get("Manufacturer", "") or "",
        description=raw.get("Description", "") or "",
        in_stock=in_stock,
        availability_text=_availability_text(
            in_stock,
            raw.get("LeadTime") or None,
            raw.get("LifecycleStatus") or None,
        ),
        lead_time=raw.get("LeadTime") or None,
        lifecycle_status=raw.get("LifecycleStatus") or None,
        price_usd=cheapest,
        price_breaks=breaks,
        product_url=raw.get("ProductDetailUrl", "") or "",
        datasheet_url=raw.get("DataSheetUrl") or None,
        image_url=raw.get("ImagePath") or None,
    )


# --- API calls --------------------------------------------------------------


class MouserAPIError(Exception):
    """Surfaces 4xx/5xx and ToU errors with a useful message."""


def search_keyword(
    api_key: str,
    keyword: str,
    in_stock_only: bool = True,
    records: int = 10,
    *,
    client: httpx.Client | None = None,
) -> list[MouserMatch]:
    """Search by free-text keyword. Returns up to `records` matches.

    Uses cache. Raises MouserAPIError on HTTP errors or Mouser-reported errors.
    """
    cache_key = ("kw", keyword.strip().lower())
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    body = {
        "SearchByKeywordRequest": {
            "keyword": keyword,
            "records": records,
            "startingRecord": 0,
            "searchOptions": "InStock" if in_stock_only else "None",
            "searchWithYourSignUpLanguage": "false",
        }
    }
    data = _post(client, "/search/keyword", api_key, body)
    matches = [
        _normalize_part(p)
        for p in (data.get("SearchResults") or {}).get("Parts") or []
    ]
    _cache_put(cache_key, matches)
    return matches


def search_part_numbers(
    api_key: str,
    mpns: list[str],
    *,
    client: httpx.Client | None = None,
) -> dict[str, list[MouserMatch]]:
    """Resolve up to 10 manufacturer part numbers in one call.

    Returns a dict mapping each input mpn → list of matches. Empty list means
    Mouser returned nothing for that MPN.
    """
    if not mpns:
        return {}
    if len(mpns) > 10:
        # Recurse by batches of 10 (caller probably has a long BOM).
        out: dict[str, list[MouserMatch]] = {}
        for i in range(0, len(mpns), 10):
            out.update(search_part_numbers(api_key, mpns[i : i + 10], client=client))
        return out

    cache_key = ("pn", "|".join(sorted(m.lower() for m in mpns)))
    cached = _cache_get(cache_key)
    if cached is not None:
        return _group_by_mpn(mpns, cached)

    body = {
        "SearchByPartRequest": {
            "mouserPartNumber": "|".join(mpns),
            "partSearchOptions": "Exact",
        }
    }
    data = _post(client, "/search/partnumber", api_key, body)
    parts = (data.get("SearchResults") or {}).get("Parts") or []
    matches = [_normalize_part(p) for p in parts]
    _cache_put(cache_key, matches)
    return _group_by_mpn(mpns, matches)


def _group_by_mpn(
    requested: list[str], matches: list[MouserMatch]
) -> dict[str, list[MouserMatch]]:
    """Bucket Mouser results back into the input MPN keys."""
    out: dict[str, list[MouserMatch]] = {m: [] for m in requested}
    for match in matches:
        for mpn in requested:
            if mpn.lower() in match.mfr_part_number.lower() or \
               mpn.lower() in match.mouser_part_number.lower():
                out[mpn].append(match)
                break
    return out


def _post(
    client: httpx.Client | None,
    path: str,
    api_key: str,
    body: dict,
) -> dict[str, Any]:
    own_client = client is None
    c = client or httpx.Client(timeout=_TIMEOUT, headers={"Accept": "application/json"})
    try:
        r = c.post(
            _BASE + path,
            params={"apiKey": api_key},
            json=body,
        )
        if r.status_code == 401 or r.status_code == 403:
            raise MouserAPIError(
                "Mouser rejected the API key. Check it in Settings."
            )
        if r.status_code == 429:
            raise MouserAPIError(
                "Mouser rate limit hit (30/min, 1000/day). Wait a minute and retry."
            )
        if r.status_code >= 400:
            raise MouserAPIError(
                f"Mouser HTTP {r.status_code}: {r.text[:200]}"
            )
        data = r.json()
        errors = data.get("Errors") or []
        if errors:
            first = errors[0]
            msg = first.get("Message") or str(first)
            raise MouserAPIError(f"Mouser error: {msg}")
        return data
    finally:
        if own_client:
            c.close()


__all__ = [
    "MouserMatch",
    "MouserAPIError",
    "search_keyword",
    "search_part_numbers",
    "clear_cache",
]
