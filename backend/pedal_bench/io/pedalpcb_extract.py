"""Build-package extractor for PedalPCB PDFs.

Given a PedalPCB build doc, pull out as much as possible automatically:
  - pedal title (from the first or drill-template page header text)
  - enclosure type (from the drill-template page, e.g. "125B Enclosure")
  - BOM (reuses the existing `extract_bom`)
  - image renders of the wiring and drill-template pages (for caching)

This is the beating heart of the one-drop UX. If this module degrades
cleanly — returning None where it's unsure — the user can always fill
in the gaps manually on the review screen.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from pedal_bench.core.models import BOMItem
from pedal_bench.io.pedalpcb_pdf import BOMParseError, extract_bom


@dataclass
class ExtractedBuildPackage:
    title: str | None = None
    enclosure: str | None = None
    bom: list[BOMItem] = field(default_factory=list)
    wiring_page_index: int | None = None
    drill_template_page_index: int | None = None
    warnings: list[str] = field(default_factory=list)


# Known enclosure keys in the shipped catalog, plus common aliases the
# PedalPCB PDFs might use (e.g., "1590N1" is Hammond's sku for the 125B).
ENCLOSURE_ALIASES: dict[str, str] = {
    "125B": "125B",
    "125 B": "125B",
    "1590N1": "125B",
    "1590A": "1590A",
    "1590B": "1590B",
    "1590BB": "1590BB",
    "1590BB2": "1590DD",
    "1590DD": "1590DD",
    "1590XX": "1590XX",
}

# Text fragments we DON'T want as the project title.
_TITLE_BLOCKLIST = {
    "pedalpcb",
    "parts list",
    "drill template",
    "schematic diagram",
    "wiring diagram",
    "bill of materials",
    "bom",
    "revised",
    "page",
    "copyright",
}


def extract_build_package(pdf_path: Path | str) -> ExtractedBuildPackage:
    """Run every extractor we've got and return a consolidated result."""
    import pdfplumber

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    pkg = ExtractedBuildPackage()

    with pdfplumber.open(pdf_path) as pdf:
        # Collect per-page text for title / enclosure / page-role detection.
        page_texts: list[str] = []
        for page in pdf.pages:
            try:
                page_texts.append(page.extract_text() or "")
            except Exception:
                page_texts.append("")

        pkg.title = _guess_title(pdf, page_texts)
        pkg.enclosure = _guess_enclosure(page_texts)
        pkg.wiring_page_index = _find_page_index(page_texts, ("wiring diagram",))
        pkg.drill_template_page_index = _find_page_index(
            page_texts, ("drill template", "enclosure")
        )

    try:
        pkg.bom = extract_bom(pdf_path)
    except BOMParseError as exc:
        pkg.warnings.append(f"BOM extraction failed: {exc}")
    except Exception as exc:  # defensive: pdfplumber can throw on odd PDFs
        pkg.warnings.append(f"BOM extraction error: {type(exc).__name__}: {exc}")

    if pkg.title is None:
        pkg.warnings.append("Could not detect pedal title; using filename.")
    if pkg.enclosure is None:
        pkg.warnings.append("Could not detect enclosure type.")

    return pkg


# ---- title ---------------------------------------------------------------

def _guess_title(pdf, page_texts: list[str]) -> str | None:
    """Return the biggest-font text on page 1 that isn't a boilerplate tag."""
    if not pdf.pages:
        return None

    # Strategy A: biggest font on page 1.
    try:
        chars = pdf.pages[0].chars
    except Exception:
        chars = []
    if chars:
        # Group consecutive chars with identical size into text runs, then
        # pick the largest-font run that passes the blocklist.
        runs = _group_chars_by_size(chars)
        for run in sorted(runs, key=lambda r: -r[0]):
            _size, text = run
            clean = text.strip()
            if not clean:
                continue
            if _is_title_candidate(clean):
                return clean

    # Strategy B: fall back to the first non-boilerplate line on any of
    # the first two pages of text.
    for text in page_texts[:2]:
        for line in text.splitlines():
            clean = line.strip()
            if _is_title_candidate(clean):
                return clean
    return None


def _group_chars_by_size(chars: list[dict]) -> list[tuple[float, str]]:
    """Reduce pdfplumber chars into (size, text) text runs."""
    runs: list[tuple[float, str]] = []
    current_size: float | None = None
    buf: list[str] = []

    def flush() -> None:
        if current_size is not None and buf:
            runs.append((current_size, "".join(buf)))

    for ch in chars:
        size = float(ch.get("size") or 0.0)
        text = ch.get("text", "")
        if not text:
            continue
        if current_size is None or abs(size - current_size) > 0.5:
            flush()
            buf = [text]
            current_size = size
        else:
            buf.append(text)
    flush()

    # Merge runs where the text looks like a single word or phrase split on
    # size boundaries (PedalPCB headers often split the title and the tiny
    # "Revised mm/dd/yy" tag right below it; we want only the big part).
    return runs


def _is_title_candidate(line: str) -> bool:
    if not line:
        return False
    lower = line.lower().strip()
    if len(lower) < 3 or len(lower) > 80:
        return False
    for tag in _TITLE_BLOCKLIST:
        if lower == tag or lower.startswith(tag) or lower.endswith(tag):
            return False
    # Reject lines that are mostly digits (page numbers, revision dates).
    alpha = sum(1 for c in lower if c.isalpha())
    if alpha < 3:
        return False
    return True


# ---- enclosure -----------------------------------------------------------

_ENCLOSURE_WORD_RE = re.compile(r"\b(125\s?B|1590[A-Z0-9]{1,3}|1590N1)\b", re.IGNORECASE)


def _guess_enclosure(page_texts: Iterable[str]) -> str | None:
    """Find the first enclosure key that matches text anywhere in the PDF."""
    joined = "\n".join(page_texts)
    # Priority 1: the drill-template page usually has "125B Enclosure" as
    # a header. Check for that exact pattern first.
    for match in re.finditer(r"\b(1590[A-Z0-9]{1,3}|125\s?B|1590N1)\s+Enclosure\b",
                             joined, re.IGNORECASE):
        return _normalize_enclosure(match.group(1))
    # Priority 2: any enclosure-shaped token.
    for match in _ENCLOSURE_WORD_RE.finditer(joined):
        return _normalize_enclosure(match.group(1))
    return None


def _normalize_enclosure(raw: str) -> str | None:
    key = re.sub(r"\s+", "", raw.upper())
    return ENCLOSURE_ALIASES.get(key)


# ---- page roles ----------------------------------------------------------

def _find_page_index(page_texts: list[str], keywords: tuple[str, ...]) -> int | None:
    for idx, text in enumerate(page_texts):
        lower = text.lower()
        if all(kw in lower for kw in keywords):
            return idx
    # Fallback: any single keyword match.
    for idx, text in enumerate(page_texts):
        lower = text.lower()
        if any(kw in lower for kw in keywords):
            return idx
    return None


def known_enclosure_keys() -> list[str]:
    """Catalog-independent. The route layer will cross-check against the
    actual catalog and blank the field if the detected key isn't supported.
    """
    return sorted(set(ENCLOSURE_ALIASES.values()))


__all__ = [
    "ExtractedBuildPackage",
    "extract_build_package",
    "known_enclosure_keys",
]
