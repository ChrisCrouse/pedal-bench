"""Render a single PDF page to a PNG image via pypdfium2.

Used to cache the wiring diagram (PedalPCB PDFs put it on page 4) for
display in the zoom/pan wiring viewer. No OCR, no text extraction — just
a rasterization.
"""

from __future__ import annotations

from pathlib import Path


def render_page_to_png(
    pdf_path: Path | str,
    page_index: int,
    output_path: Path | str,
    *,
    dpi: int = 200,
) -> Path:
    """Render a specific page (0-indexed) to a PNG file.

    Args:
        pdf_path: source PDF.
        page_index: 0-indexed page number. (Page 4 of a PedalPCB PDF -> 3.)
        output_path: destination .png path.
        dpi: render resolution. 200 is a reasonable default for screen
            viewing of a letter-sized page; bump to 300 if you need to
            zoom very far in.

    Returns the output path.
    """
    import pypdfium2 as pdfium  # deferred import

    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    # pypdfium2's native unit is 72 DPI; scale factor = dpi / 72.
    scale = dpi / 72.0

    pdf = pdfium.PdfDocument(pdf_path)
    try:
        if page_index < 0 or page_index >= len(pdf):
            raise IndexError(
                f"page_index {page_index} out of range for {len(pdf)}-page PDF"
            )
        page = pdf[page_index]
        pil_image = page.render(scale=scale).to_pil()
    finally:
        pdf.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pil_image.save(output_path, format="PNG", optimize=True)
    return output_path


__all__ = ["render_page_to_png"]
