"""SQLite read-only index over the JSON project store.

Source of truth stays JSON-on-disk in projects/<slug>/project.json. This
index is rebuilt from disk on demand (lazy, when an inventory query asks
for it) and used to answer cross-project questions like "how many 100K
resistors do I have across all projects" or "which projects use TL072".

The index lives at <repo>/pedal_bench_index.sqlite and is safe to delete —
it'll rebuild from the JSON files on the next query.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .project_store import ProjectStore


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    slug         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    status       TEXT NOT NULL,
    enclosure    TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bom_rows (
    project_slug TEXT NOT NULL,
    location     TEXT NOT NULL,
    value        TEXT NOT NULL,
    type         TEXT NOT NULL,
    quantity     INTEGER NOT NULL,
    value_norm   TEXT NOT NULL,    -- normalized for grouping ("100k" not "100K Ohm")
    kind         TEXT NOT NULL,    -- resistor / film-cap / electrolytic / diode / etc.
    FOREIGN KEY (project_slug) REFERENCES projects (slug)
);

CREATE INDEX IF NOT EXISTS idx_bom_value_norm ON bom_rows (value_norm);
CREATE INDEX IF NOT EXISTS idx_bom_kind ON bom_rows (kind);
CREATE INDEX IF NOT EXISTS idx_bom_project ON bom_rows (project_slug);
"""


# --- Classification (mirrors frontend componentColors.ts) -------------------
# Kept in sync intentionally — same vocabulary, same buckets. Don't change one
# without the other.

_LOC_RE = {
    "ic": re.compile(r"^ic\d", re.I),
    "transistor": re.compile(r"^q\d", re.I),
    "diode": re.compile(r"^d\d", re.I),
    "inductor": re.compile(r"^l\d+$", re.I),
    "switch": re.compile(r"^(s|sw)\d+$", re.I),
    "resistor": re.compile(r"^r\d+$", re.I),
    "cap": re.compile(r"^c\d+$", re.I),
}


def classify(item_loc: str, item_type: str) -> str:
    """Return one of: resistor / film-cap / electrolytic / diode / transistor /
    ic / pot / inductor / switch / other.

    Mirrors the frontend's classifyComponent. Location prefix is most reliable
    because PedalPCB refdes are consistent (R1, C2, IC1, Q3, ...).
    """
    loc = (item_loc or "").lower().strip()
    t = (item_type or "").lower()

    if _LOC_RE["ic"].match(loc):
        return "ic"
    if _LOC_RE["transistor"].match(loc):
        return "transistor"
    if _LOC_RE["diode"].match(loc):
        return "diode"
    if _LOC_RE["inductor"].match(loc):
        return "inductor"
    if _LOC_RE["switch"].match(loc):
        return "switch"
    if _LOC_RE["resistor"].match(loc):
        return "resistor"
    if loc == "clr":
        return "resistor"
    if _LOC_RE["cap"].match(loc):
        if "electrolytic" in t or "tantalum" in t:
            return "electrolytic"
        return "film-cap"

    if "resistor" in t:
        return "resistor"
    if "electrolytic" in t or "tantalum" in t:
        return "electrolytic"
    if "cap" in t or "ceramic" in t or "film" in t:
        return "film-cap"
    if "diode" in t:
        return "diode"
    if any(k in t for k in ("transistor", "mosfet", "jfet", "bjt")):
        return "transistor"
    if "op-amp" in t or "opamp" in t or "ic" in t:
        return "ic"
    if "pot" in t:
        return "pot"
    if "inductor" in t or "coil" in t:
        return "inductor"
    if "switch" in t or "toggle" in t:
        return "switch"

    if loc and loc.isalpha():
        return "pot"
    return "other"


# --- Value normalization ----------------------------------------------------
# Goal: "100K", "100k", "100 K", "100k ohm", "100k 1/4w" all collapse to "100k"
# so cross-project counts are sensible. Exact units we don't try to convert
# (1µF vs 1uF) — just lowercase, strip whitespace, strip trailing "ohm"/"watt"
# words. For ICs/transistors/diodes the "value" IS the part number, so we just
# uppercase + strip whitespace.

_UNIT_NOISE = re.compile(
    # Strip "ohm/watt/volt" words, optionally preceded by a wattage spec
    # like "1/4" or "1/2", and optionally followed by trailing tolerance.
    r"(?:[\d/.]+\s*)?"
    r"(ohm|ohms|Ω|watt|watts|w|volts|volt|v|tolerance|tol)"
    r"\s*[\d/.]*",
    re.I,
)
_WS = re.compile(r"\s+")
_MICRO = re.compile(r"µ", re.I)


def normalize_value(raw: str, kind: str) -> str:
    """Collapse cosmetic differences so '100K' and '100k Ohm' compare equal."""
    if not raw:
        return ""
    v = raw.strip()
    # Normalize µ→u for capacitors so "1uF" == "1µF".
    v = _MICRO.sub("u", v)
    if kind in ("ic", "transistor", "diode"):
        # Part numbers: just uppercase, drop whitespace.
        return _WS.sub("", v.upper())
    # Passives: lowercase, strip ohm/watt noise, collapse whitespace.
    v = _UNIT_NOISE.sub("", v.lower())
    v = _WS.sub("", v)
    return v


@dataclass
class PartTotal:
    """One row of a 'how many X across all projects' query."""
    kind: str
    value_norm: str
    display_value: str       # one representative original value for display
    total_qty: int
    project_count: int
    project_slugs: list[str]


@dataclass
class ProjectHit:
    """One project that uses a given part."""
    slug: str
    name: str
    status: str
    quantity: int


class InventoryIndex:
    """Read-only-ish SQLite index built from the JSON project store.

    Rebuilt fully from disk on every refresh() — projects are small (dozens,
    not millions), so a full rebuild is faster and simpler than tracking
    incremental changes. Call refresh() before any query that needs to be
    current.
    """

    def __init__(self, db_path: Path, store: ProjectStore) -> None:
        self.db_path = Path(db_path)
        self.store = store

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def refresh(self) -> None:
        """Drop everything and rebuild from disk."""
        # Wipe and recreate. Schema is small, projects fit in memory.
        if self.db_path.exists():
            self.db_path.unlink()
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            project_rows: list[tuple] = []
            bom_rows: list[tuple] = []
            for project in self.store.iter_projects():
                project_rows.append(
                    (
                        project.slug,
                        project.name,
                        project.status,
                        project.enclosure,
                        project.updated_at,
                    )
                )
                for item in project.bom:
                    kind = classify(item.location, item.type)
                    value_norm = normalize_value(item.value, kind)
                    bom_rows.append(
                        (
                            project.slug,
                            item.location,
                            item.value,
                            item.type,
                            int(item.quantity),
                            value_norm,
                            kind,
                        )
                    )
            conn.executemany(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?)", project_rows
            )
            conn.executemany(
                "INSERT INTO bom_rows VALUES (?, ?, ?, ?, ?, ?, ?)", bom_rows
            )

    def part_totals(
        self, kind_filter: str | None = None, search: str | None = None
    ) -> list[PartTotal]:
        """Group by (kind, value_norm) and total quantities across all projects."""
        where: list[str] = ["value_norm != ''"]
        params: list = []
        if kind_filter:
            where.append("kind = ?")
            params.append(kind_filter)
        if search:
            where.append("(value_norm LIKE ? OR type LIKE ?)")
            term = f"%{search.lower()}%"
            params.extend([term, term])
        where_sql = " AND ".join(where)

        sql = f"""
        SELECT
            kind,
            value_norm,
            MIN(value)              AS display_value,
            SUM(quantity)           AS total_qty,
            COUNT(DISTINCT project_slug) AS project_count,
            GROUP_CONCAT(DISTINCT project_slug) AS slugs
        FROM bom_rows
        WHERE {where_sql}
        GROUP BY kind, value_norm
        ORDER BY total_qty DESC, kind, value_norm
        """
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            PartTotal(
                kind=r["kind"],
                value_norm=r["value_norm"],
                display_value=r["display_value"],
                total_qty=int(r["total_qty"]),
                project_count=int(r["project_count"]),
                project_slugs=(r["slugs"] or "").split(","),
            )
            for r in rows
        ]

    def projects_using(self, kind: str, value_norm: str) -> list[ProjectHit]:
        """Which projects use this part, and how many?"""
        sql = """
        SELECT
            p.slug, p.name, p.status,
            SUM(b.quantity) AS quantity
        FROM bom_rows b
        JOIN projects p ON p.slug = b.project_slug
        WHERE b.kind = ? AND b.value_norm = ?
        GROUP BY p.slug, p.name, p.status
        ORDER BY quantity DESC, p.name
        """
        with self._conn() as conn:
            rows = conn.execute(sql, (kind, value_norm)).fetchall()
        return [
            ProjectHit(
                slug=r["slug"],
                name=r["name"],
                status=r["status"],
                quantity=int(r["quantity"]),
            )
            for r in rows
        ]

    def stats(self) -> dict:
        """Top-level counts for the inventory dashboard."""
        with self._conn() as conn:
            project_count = conn.execute(
                "SELECT COUNT(*) FROM projects"
            ).fetchone()[0]
            unique_parts = conn.execute(
                "SELECT COUNT(DISTINCT kind || '::' || value_norm) "
                "FROM bom_rows WHERE value_norm != ''"
            ).fetchone()[0]
            total_parts = conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM bom_rows"
            ).fetchone()[0]
            by_kind = conn.execute(
                "SELECT kind, SUM(quantity) AS qty FROM bom_rows "
                "GROUP BY kind ORDER BY qty DESC"
            ).fetchall()
        return {
            "project_count": int(project_count),
            "unique_parts": int(unique_parts),
            "total_parts": int(total_parts),
            "by_kind": [
                {"kind": r["kind"], "quantity": int(r["qty"])} for r in by_kind
            ],
        }


__all__ = [
    "InventoryIndex",
    "PartTotal",
    "ProjectHit",
    "classify",
    "normalize_value",
]
