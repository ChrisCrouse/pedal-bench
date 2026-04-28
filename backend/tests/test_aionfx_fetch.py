from __future__ import annotations

import pytest

from pedal_bench.io.aionfx_fetch import (
    AionFXFetchError,
    _find_pdf_link,
    _find_title,
    _validate_url,
)


def test_validate_url_accepts_project_and_pdf_urls() -> None:
    assert (
        _validate_url("aionfx.com/project/helios-vintage-distortion/")
        == "https://aionfx.com/project/helios-vintage-distortion/"
    )
    assert (
        _validate_url("https://www.aionfx.com/app/files/docs/helios_documentation.pdf")
        == "https://www.aionfx.com/app/files/docs/helios_documentation.pdf"
    )


def test_validate_url_rejects_other_hosts() -> None:
    with pytest.raises(AionFXFetchError, match="aionfx.com"):
        _validate_url("https://example.com/project/helios/")


def test_find_pdf_link_prefers_current_pcb_only_doc() -> None:
    html = """
    <h1>Helios Vintage Distortion / Pro Co RAT</h1>
    <a href="/app/files/docs/helios_kit_documentation.pdf">Kit Build Documentation (current) pdf</a>
    <a href="/app/files/docs/helios_documentation.pdf">PCB-Only Build Doc (current) pdf</a>
    <a href="/app/files/docs/helios_documentation_v1.0.pdf">PCB-Only Build Doc (v1.0) pdf</a>
    """

    assert (
        _find_pdf_link(html, "https://aionfx.com/project/helios-vintage-distortion/")
        == "https://aionfx.com/app/files/docs/helios_documentation.pdf"
    )


def test_find_title_strips_based_on_suffix() -> None:
    html = "<h1>Helios Vintage Distortion / Pro Co RAT - Aion FX</h1>"
    assert _find_title(html) == "Helios Vintage Distortion"
