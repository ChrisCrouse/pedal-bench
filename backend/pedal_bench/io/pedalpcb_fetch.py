"""Fetch a PedalPCB build-documentation PDF from a product-page URL.

The PedalPCB site hosts product pages at ``pedalpcb.com/product/<slug>/``
and each page links to a build-doc PDF on ``docs.pedalpcb.com/project/*.pdf``
(named by the pedal, not the SKU — so the PDF URL is *not* derivable from
the product slug and we must scrape the product page).

This module handles the two hops: product page → PDF URL → PDF bytes.
Used by the /api/v1/pdf/from-url route so users can paste a product URL
instead of downloading + dragging the PDF themselves.

Scraping footprint:
- Single GET on the product page, single GET on the PDF.
- Identifies ourselves via User-Agent (no cloaking).
- robots.txt permits /product/ — see pedalpcb.com/robots.txt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

USER_AGENT = "pedal-bench/0.2 (+https://github.com/ccrouse/pedal-bench)"
PDF_LINK_PATTERN = re.compile(
    r'href="(https://docs\.pedalpcb\.com/project/[^"]+\.pdf)"',
    re.IGNORECASE,
)
TITLE_PATTERN = re.compile(
    r"<h1[^>]*class=\"[^\"]*product_title[^\"]*\"[^>]*>(.*?)</h1>",
    re.IGNORECASE | re.DOTALL,
)
REQUEST_TIMEOUT = 20.0
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB hard cap


@dataclass(frozen=True)
class FetchedPDF:
    """Result of fetching a PedalPCB build doc."""

    pdf_bytes: bytes
    pdf_url: str
    product_url: str
    suggested_name: str | None  # from the product-page <h1>, if found


class PedalPCBFetchError(Exception):
    """User-presentable error; the message is safe to show verbatim."""


def fetch_from_product_url(url: str) -> FetchedPDF:
    """Scrape a PedalPCB product page and download its build PDF.

    Raises PedalPCBFetchError with a user-readable message on any failure.
    """
    product_url = _validate_product_url(url)

    headers = {"User-Agent": USER_AGENT}
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers=headers,
            follow_redirects=True,
        ) as client:
            resp = client.get(product_url)
            if resp.status_code == 404:
                raise PedalPCBFetchError(
                    f"PedalPCB returned 404 for {product_url}. Check the URL."
                )
            resp.raise_for_status()
            html = resp.text

            pdf_url = _find_pdf_link(html, base_url=product_url)
            if not pdf_url:
                raise PedalPCBFetchError(
                    "No build-documentation PDF link found on that product page. "
                    "Some PedalPCB products don't publish a build doc."
                )

            suggested_name = _find_title(html)

            pdf_resp = client.get(pdf_url)
            pdf_resp.raise_for_status()
            pdf_bytes = pdf_resp.content
    except httpx.TimeoutException as exc:
        raise PedalPCBFetchError(f"Timed out fetching {url}: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise PedalPCBFetchError(
            f"HTTP {exc.response.status_code} from {exc.request.url}"
        ) from exc
    except httpx.HTTPError as exc:
        raise PedalPCBFetchError(f"Network error fetching {url}: {exc}") from exc

    if not pdf_bytes:
        raise PedalPCBFetchError("Downloaded PDF is empty.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise PedalPCBFetchError(
            f"Downloaded PDF is {len(pdf_bytes) // (1024 * 1024)} MB (limit 50 MB)."
        )
    if not pdf_bytes.startswith(b"%PDF-"):
        raise PedalPCBFetchError(
            "Downloaded file is not a PDF (server returned something else)."
        )

    return FetchedPDF(
        pdf_bytes=pdf_bytes,
        pdf_url=pdf_url,
        product_url=product_url,
        suggested_name=suggested_name,
    )


def _validate_product_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise PedalPCBFetchError("URL is empty.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"pedalpcb.com", "www.pedalpcb.com"}:
        raise PedalPCBFetchError(
            f"Only pedalpcb.com product URLs are supported; got host {host!r}."
        )
    if not parsed.path.startswith("/product/"):
        raise PedalPCBFetchError(
            "URL must be a PedalPCB product page (path starts with /product/)."
        )
    # Rebuild canonical URL (drop query params / fragments, normalize trailing slash).
    path = parsed.path if parsed.path.endswith("/") else parsed.path + "/"
    return f"https://www.pedalpcb.com{path}"


def _find_pdf_link(html: str, base_url: str) -> str | None:
    m = PDF_LINK_PATTERN.search(html)
    if not m:
        return None
    href = m.group(1)
    # Already absolute per the regex, but route through urljoin for safety.
    return urljoin(base_url, href)


def _find_title(html: str) -> str | None:
    m = TITLE_PATTERN.search(html)
    if not m:
        return None
    # Strip any inner HTML tags the theme may have inserted, then whitespace.
    raw = re.sub(r"<[^>]+>", "", m.group(1))
    title = re.sub(r"\s+", " ", raw).strip()
    return title or None


__all__ = ["FetchedPDF", "PedalPCBFetchError", "fetch_from_product_url"]
