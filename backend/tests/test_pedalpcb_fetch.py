"""Unit tests for pedalpcb_fetch — parsing + URL validation.

Network-dependent tests (actually hitting pedalpcb.com) are intentionally
skipped; the parsing logic is what matters and it's testable offline.
"""

from __future__ import annotations

import pytest

from pedal_bench.io.pedalpcb_fetch import (
    PedalPCBFetchError,
    _find_pdf_link,
    _find_title,
    _validate_product_url,
)


# -- URL validation ---------------------------------------------------------


class TestValidateProductURL:
    def test_canonicalizes_bare_domain(self) -> None:
        assert (
            _validate_product_url("pedalpcb.com/product/duocast/")
            == "https://www.pedalpcb.com/product/duocast/"
        )

    def test_canonicalizes_http(self) -> None:
        assert (
            _validate_product_url("http://www.pedalpcb.com/product/duocast")
            == "https://www.pedalpcb.com/product/duocast/"
        )

    def test_accepts_www(self) -> None:
        assert (
            _validate_product_url("https://www.pedalpcb.com/product/terrarium/")
            == "https://www.pedalpcb.com/product/terrarium/"
        )

    def test_strips_query_string(self) -> None:
        assert (
            _validate_product_url(
                "https://www.pedalpcb.com/product/duocast/?utm_source=foo"
            )
            == "https://www.pedalpcb.com/product/duocast/"
        )

    def test_rejects_other_domain(self) -> None:
        with pytest.raises(PedalPCBFetchError, match="pedalpcb.com"):
            _validate_product_url("https://example.com/product/foo/")

    def test_rejects_non_product_path(self) -> None:
        with pytest.raises(PedalPCBFetchError, match="/product/"):
            _validate_product_url("https://www.pedalpcb.com/shop/")

    def test_rejects_empty(self) -> None:
        with pytest.raises(PedalPCBFetchError, match="empty"):
            _validate_product_url("")


# -- PDF link extraction ----------------------------------------------------


class TestFindPDFLink:
    def test_finds_canonical_link(self) -> None:
        html = '<p><a href="https://docs.pedalpcb.com/project/DuoCast.pdf">Download Build Documentation</a></p>'
        assert (
            _find_pdf_link(html, "https://www.pedalpcb.com/product/duocast/")
            == "https://docs.pedalpcb.com/project/DuoCast.pdf"
        )

    def test_handles_extra_attrs(self) -> None:
        html = (
            '<a class="btn" target="_blank" '
            'href="https://docs.pedalpcb.com/project/Terrarium-PedalPCB.pdf" '
            'rel="noopener">Download Build Doc</a>'
        )
        link = _find_pdf_link(html, "https://www.pedalpcb.com/product/pcb351/")
        assert link == "https://docs.pedalpcb.com/project/Terrarium-PedalPCB.pdf"

    def test_returns_none_when_missing(self) -> None:
        html = "<html><body><p>No PDF here</p></body></html>"
        assert _find_pdf_link(html, "https://www.pedalpcb.com/product/foo/") is None

    def test_ignores_other_pdfs(self) -> None:
        html = '<a href="https://example.com/something.pdf">unrelated</a>'
        assert _find_pdf_link(html, "https://www.pedalpcb.com/product/foo/") is None


# -- Title extraction -------------------------------------------------------


class TestFindTitle:
    def test_finds_product_title(self) -> None:
        html = '<h1 class="product_title entry-title">DuoCast</h1>'
        assert _find_title(html) == "DuoCast"

    def test_strips_inner_tags(self) -> None:
        html = '<h1 class="product_title"><span>Sherwood</span> Overdrive</h1>'
        assert _find_title(html) == "Sherwood Overdrive"

    def test_collapses_whitespace(self) -> None:
        html = '<h1 class="product_title">\n   Duo   Cast   \n</h1>'
        assert _find_title(html) == "Duo Cast"

    def test_returns_none_without_title(self) -> None:
        html = "<html><body><h1>different heading</h1></body></html>"
        assert _find_title(html) is None
