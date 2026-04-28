"""Fetch Aion FX documentation PDFs from project or direct PDF URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

USER_AGENT = "pedal-bench/0.2 (+https://github.com/ccrouse/pedal-bench)"
REQUEST_TIMEOUT = 20.0
MAX_PDF_BYTES = 50 * 1024 * 1024

_ANCHOR_RE = re.compile(r'<a\s+[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.I | re.S)
_TITLE_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)


@dataclass(frozen=True)
class FetchedAionFXPDF:
    pdf_bytes: bytes
    pdf_url: str
    source_url: str
    suggested_name: str | None = None


class AionFXFetchError(Exception):
    """User-presentable fetch error."""


def fetch_from_url(url: str) -> FetchedAionFXPDF:
    source_url = _validate_url(url)
    headers = {"User-Agent": USER_AGENT}
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers=headers,
            follow_redirects=True,
        ) as client:
            if source_url.lower().endswith(".pdf"):
                pdf_url = source_url
                suggested_name = None
            else:
                resp = client.get(source_url)
                if resp.status_code == 404:
                    raise AionFXFetchError(f"Aion FX returned 404 for {source_url}.")
                resp.raise_for_status()
                html = resp.text
                pdf_url = _find_pdf_link(html, source_url)
                if not pdf_url:
                    raise AionFXFetchError(
                        "No current PCB-only build documentation PDF found on that Aion FX page."
                    )
                suggested_name = _find_title(html)

            pdf_resp = client.get(pdf_url)
            pdf_resp.raise_for_status()
            pdf_bytes = pdf_resp.content
    except AionFXFetchError:
        raise
    except httpx.TimeoutException as exc:
        raise AionFXFetchError(f"Timed out fetching {url}: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise AionFXFetchError(
            f"HTTP {exc.response.status_code} from {exc.request.url}"
        ) from exc
    except httpx.HTTPError as exc:
        raise AionFXFetchError(f"Network error fetching {url}: {exc}") from exc

    if not pdf_bytes:
        raise AionFXFetchError("Downloaded PDF is empty.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise AionFXFetchError(
            f"Downloaded PDF is {len(pdf_bytes) // (1024 * 1024)} MB (limit 50 MB)."
        )
    if not pdf_bytes.startswith(b"%PDF-"):
        raise AionFXFetchError("Downloaded file is not a PDF.")

    return FetchedAionFXPDF(
        pdf_bytes=pdf_bytes,
        pdf_url=pdf_url,
        source_url=source_url,
        suggested_name=suggested_name,
    )


def _validate_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise AionFXFetchError("URL is empty.")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in {"aionfx.com", "www.aionfx.com"}:
        raise AionFXFetchError(f"Only aionfx.com URLs are supported; got host {host!r}.")
    if parsed.scheme != "https":
        raw = parsed._replace(scheme="https").geturl()
    return raw


def _find_pdf_link(html: str, base_url: str) -> str | None:
    candidates: list[tuple[int, str]] = []
    for match in _ANCHOR_RE.finditer(html):
        href, raw_label = match.groups()
        label = re.sub(r"<[^>]+>", "", raw_label)
        normalized = " ".join(label.split()).lower()
        score = 0
        if "pcb-only" in normalized or "pcb only" in normalized:
            score += 100
        if "current" in normalized:
            score += 25
        if "kit" in normalized:
            score -= 50
        if "documentation" in normalized or "build doc" in normalized:
            score += 10
        candidates.append((score, urljoin(base_url, href)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _find_title(html: str) -> str | None:
    match = _TITLE_RE.search(html)
    if not match:
        return None
    title = re.sub(r"<[^>]+>", "", match.group(1))
    title = re.sub(r"\s+", " ", title).strip()
    if " / " in title:
        title = title.split(" / ", 1)[0].strip()
    return title or None


__all__ = [
    "AionFXFetchError",
    "FetchedAionFXPDF",
    "fetch_from_url",
    "_find_pdf_link",
    "_find_title",
    "_validate_url",
]
