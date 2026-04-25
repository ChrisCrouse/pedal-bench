"""Fetch a Taydakits build-instructions page set.

Taydakits hosts each build at ``taydakits.com/instructions/<slug>`` (overview)
with up to 5 sub-step pages at ``/instructions/<slug>/pages/<step>--<id>``.
Unlike PedalPCB there's no PDF — every piece of build data is in the HTML.

This module handles fetching the overview, discovering the sub-step URLs,
and pulling the two steps we actually parse for data: the components step
(BOM) and the drilling step (enclosure prose).

Scraping footprint:
- One GET per page (3 total in v1: overview, designators, drilling).
- Identifies ourselves via User-Agent (no cloaking).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

USER_AGENT = "pedal-bench/0.2 (+https://github.com/ccrouse/pedal-bench)"
REQUEST_TIMEOUT = 20.0
MAX_PAGE_BYTES = 5 * 1024 * 1024  # 5 MB — Taydakits pages are ~25 KB

# Sub-step links look like:
#   <a href="/instructions/fuzz-face/pages/designators-and-components--26" ...>
_STEP_LINK_RE = re.compile(
    r'href="(/instructions/[^/"]+/pages/[^"]+)"',
    re.IGNORECASE,
)
# Step name slugs we care about. Taydakits uses these names consistently
# across builds (verified against multiple kits).
_DESIGNATORS_KEYWORDS = ("designators", "components")
_DRILLING_KEYWORDS = ("drilling",)
_WIRING_KEYWORDS = ("wiring",)


@dataclass
class FetchedTaydakitsBuild:
    """Raw HTML for the pages we extract from."""

    slug: str
    overview_url: str
    overview_html: str
    designators_html: str | None = None
    drilling_html: str | None = None
    wiring_html: str | None = None
    step_urls: dict[str, str] = field(default_factory=dict)


class TaydakitsFetchError(Exception):
    """User-presentable error; the message is safe to show verbatim."""


def fetch_build(url: str) -> FetchedTaydakitsBuild:
    """Fetch the overview + relevant sub-step HTML for a Taydakits build.

    Raises TaydakitsFetchError with a user-readable message on any failure.
    """
    overview_url, slug = _validate_url(url)
    headers = {"User-Agent": USER_AGENT}

    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers=headers,
            follow_redirects=True,
        ) as client:
            overview_html = _get(client, overview_url)
            step_urls = _discover_steps(overview_html, slug, base=overview_url)

            designators_url = _pick_step(step_urls, _DESIGNATORS_KEYWORDS)
            drilling_url = _pick_step(step_urls, _DRILLING_KEYWORDS)
            wiring_url = _pick_step(step_urls, _WIRING_KEYWORDS)

            designators_html = _get(client, designators_url) if designators_url else None
            drilling_html = _get(client, drilling_url) if drilling_url else None
            wiring_html = _get(client, wiring_url) if wiring_url else None
    except httpx.TimeoutException as exc:
        raise TaydakitsFetchError(f"Timed out fetching {url}: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise TaydakitsFetchError(
            f"HTTP {exc.response.status_code} from {exc.request.url}"
        ) from exc
    except httpx.HTTPError as exc:
        raise TaydakitsFetchError(f"Network error fetching {url}: {exc}") from exc

    if designators_html is None:
        raise TaydakitsFetchError(
            "Couldn't find the 'Designators and components' step on that build. "
            "Taydakits may have changed its page layout — please report this URL."
        )

    return FetchedTaydakitsBuild(
        slug=slug,
        overview_url=overview_url,
        overview_html=overview_html,
        designators_html=designators_html,
        drilling_html=drilling_html,
        wiring_html=wiring_html,
        step_urls=step_urls,
    )


def _get(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    if resp.status_code == 404:
        raise TaydakitsFetchError(f"Taydakits returned 404 for {url}.")
    resp.raise_for_status()
    if len(resp.content) > MAX_PAGE_BYTES:
        raise TaydakitsFetchError(
            f"Page at {url} is unexpectedly large ({len(resp.content)} bytes)."
        )
    return resp.text


def _validate_url(url: str) -> tuple[str, str]:
    """Canonicalize URL and return (overview_url, slug).

    Accepts both the overview URL and any sub-step URL — strips back to
    the overview form so callers can paste either.
    """
    url = (url or "").strip()
    if not url:
        raise TaydakitsFetchError("URL is empty.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"taydakits.com", "www.taydakits.com"}:
        raise TaydakitsFetchError(
            f"Only taydakits.com instruction URLs are supported; got host {host!r}."
        )
    path = parsed.path.rstrip("/")
    if not path.startswith("/instructions/"):
        raise TaydakitsFetchError(
            "URL must be a Taydakits instruction page (path starts with /instructions/)."
        )
    # Strip off "/pages/<step>--<id>" if the user pasted a sub-step.
    parts = path.split("/")
    # ["", "instructions", "<slug>", maybe "pages", "<step>--<id>"]
    if len(parts) < 3 or not parts[2]:
        raise TaydakitsFetchError(
            "URL is missing the build slug (expected /instructions/<slug>)."
        )
    slug = parts[2]
    return f"https://www.taydakits.com/instructions/{slug}", slug


def _discover_steps(html: str, slug: str, base: str) -> dict[str, str]:
    """Map step-name keyword → absolute URL by scanning links on the overview.

    Keys are lowercased step path-stems (e.g. ``"designators-and-components"``)
    so callers can match by keyword without parsing the trailing ``--<id>``.
    """
    out: dict[str, str] = {}
    expected_prefix = f"/instructions/{slug}/pages/"
    for match in _STEP_LINK_RE.finditer(html):
        href = match.group(1)
        if not href.startswith(expected_prefix):
            continue
        step_part = href[len(expected_prefix):]
        # Strip the "--<id>" suffix Taydakits appends for routing.
        stem = step_part.split("--", 1)[0].lower()
        if stem and stem not in out:
            out[stem] = urljoin(base, href)
    return out


def _pick_step(step_urls: dict[str, str], keywords: tuple[str, ...]) -> str | None:
    """Return the first step URL whose stem contains all keywords."""
    for stem, url in step_urls.items():
        if all(kw in stem for kw in keywords):
            return url
    return None


__all__ = ["FetchedTaydakitsBuild", "TaydakitsFetchError", "fetch_build"]
