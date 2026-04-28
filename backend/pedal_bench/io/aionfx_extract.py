"""Build-package extractor for Aion FX documentation PDFs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from pedal_bench.core.models import Enclosure
from pedal_bench.io.aionfx_drill import extract_drill_holes
from pedal_bench.io.aionfx_pdf import AionFXBOMParseError, extract_bom
from pedal_bench.io.build_import import ExtractedBuildPackage
from pedal_bench.io.pedalpcb_extract import _normalize_enclosure


def is_aionfx_pdf(pdf_path: Path | str) -> bool:
    import pdfplumber

    try:
        with pdfplumber.open(pdf_path) as pdf:
            texts = []
            for page in pdf.pages[:2]:
                texts.append(page.extract_text() or "")
    except Exception:
        return False
    joined = "\n".join(texts).upper()
    markers = ("PROJECT NAME", "BASED ON", "BUILD DIFFICULTY", "DOCUMENT VERSION")
    return sum(1 for marker in markers if marker in joined) >= 3


def extract_build_package(
    pdf_path: Path | str,
    enclosure: Enclosure | None = None,
) -> ExtractedBuildPackage:
    import pdfplumber

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    pkg = ExtractedBuildPackage(source_supplier="aionfx")

    with pdfplumber.open(pdf_path) as pdf:
        page_texts = []
        for page in pdf.pages:
            try:
                page_texts.append(page.extract_text() or "")
            except Exception:
                page_texts.append("")

    pkg.title = _guess_title(page_texts)
    pkg.enclosure = _guess_enclosure(page_texts)
    pkg.drill_template_page_index = _find_exact_heading_page(page_texts, "DRILL TEMPLATE")
    pkg.wiring_page_index = _find_exact_heading_page(page_texts, "WIRING DIAGRAM")
    pkg.schematic_page_index = _find_exact_heading_page(page_texts, "SCHEMATIC")
    # Aion docs place the PCB population artwork on the cover page.
    # "ENCLOSURE LAYOUT" is for drilling/jack placement and is the wrong
    # image for BOM click-to-tag.
    pkg.pcb_layout_page_index = 0

    try:
        pkg.bom = extract_bom(pdf_path)
    except AionFXBOMParseError as exc:
        pkg.warnings.append(f"BOM extraction failed: {exc}")
    except Exception as exc:
        pkg.warnings.append(f"BOM extraction error: {type(exc).__name__}: {exc}")

    try:
        holes = extract_drill_holes(
            pdf_path,
            enclosure=enclosure,
            page_index=pkg.drill_template_page_index,
        )
        if holes:
            pkg.holes = holes
        else:
            pkg.warnings.append(
                "Aion FX drill-template hole extraction yielded no confident results."
            )
    except Exception as exc:
        pkg.warnings.append(
            f"Aion FX drill-template extraction error: {type(exc).__name__}: {exc}"
        )

    if pkg.title is None:
        pkg.warnings.append("Could not detect pedal title; using filename.")
    if pkg.enclosure is None:
        pkg.warnings.append("Could not detect enclosure type.")

    return pkg


def _guess_title(page_texts: list[str]) -> str | None:
    if not page_texts:
        return None
    lines = [line.strip() for line in page_texts[0].splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        if line.upper() == "PROJECT NAME" and idx + 1 < len(lines):
            return _title_case(lines[idx + 1])
    # Fallback for text extractors that include the running header.
    for line in lines[:5]:
        if "CLASSIC" in line.upper() or "VINTAGE" in line.upper():
            clean = re.sub(r"\s+\d+$", "", line).strip()
            return _title_case(clean)
    return None


def _title_case(value: str) -> str:
    words = value.strip().split()
    if not words:
        return value
    return " ".join(w.capitalize() if w.isupper() else w for w in words)


def _guess_enclosure(page_texts: Iterable[str]) -> str | None:
    joined = "\n".join(page_texts)
    for match in re.finditer(r"\b(125\s?B|1590[A-Z0-9]{1,3}|1590N1)\b", joined, re.I):
        normalized = _normalize_enclosure(match.group(1))
        if normalized:
            return normalized
    return None


def _find_exact_heading_page(page_texts: list[str], heading: str) -> int | None:
    target = heading.upper()
    for idx, text in enumerate(page_texts):
        lines = [line.strip().upper() for line in text.splitlines() if line.strip()]
        if lines and lines[0] == target:
            return idx
    return None


__all__ = [
    "extract_build_package",
    "is_aionfx_pdf",
    "_find_exact_heading_page",
    "_guess_enclosure",
    "_guess_title",
]
