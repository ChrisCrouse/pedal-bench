"""Shared build-document import contracts.

Supplier-specific extractors return this shape so the API routes can keep
the upload / preview / create flows consistent across PDF sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pedal_bench.core.models import BOMItem, Hole

SourceSupplier = Literal["pedalpcb", "aionfx", "taydakits"]


@dataclass
class ExtractedBuildPackage:
    title: str | None = None
    enclosure: str | None = None
    bom: list[BOMItem] = field(default_factory=list)
    holes: list[Hole] = field(default_factory=list)
    wiring_page_index: int | None = None
    drill_template_page_index: int | None = None
    pcb_layout_page_index: int | None = 0
    schematic_page_index: int | None = None
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    drill_tool_url: str | None = None
    source_supplier: SourceSupplier | None = None
    source_url: str | None = None


__all__ = ["ExtractedBuildPackage", "SourceSupplier"]
