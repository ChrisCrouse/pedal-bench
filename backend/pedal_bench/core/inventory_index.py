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
#
# Goal: every equivalent way of writing a passive value collapses to ONE
# canonical string so cross-project counts, BOM↔inventory matching, and
# search all line up. The full grammar is documented in the project README
# under "Resistor and Capacitor Value Conversion Rules" — this file is the
# single backend implementation.
#
#   "100K" / "100k" / "100 K" / "100k ohm" / "100k 1/4w" / "100KF"   → "100k"
#   "4K7" / "4700" / "4.7k" / "4K7J"                                  → "4.7k"
#   "100n" / "0.1u" / "104"  (cap 3-digit code)                       → "100n"
#   "4u7" / "u47" + decimal places                                    → "4.7u" / "470n"
#   "R22" (R-prefix decimal)                                          → "0.22"
#
# ICs/transistors/diodes use part numbers; we just uppercase and strip
# whitespace so "tl 072" and "TL072" collide.

_UNIT_NOISE = re.compile(
    # Strip "ohm/watt/volt" words, optionally preceded by a wattage spec
    # like "1/4" or "1/2", and optionally followed by trailing tolerance.
    r"(?:[\d/.]+\s*)?"
    r"(ohm|ohms|Ω|watt|watts|w|volts|volt|v|tolerance|tol)"
    r"\s*[\d/.]*",
    re.I,
)
_WS = re.compile(r"\s+")


def _strip_micro(v: str) -> str:
    """Collapse both µ (U+00B5 micro sign) and μ (U+03BC Greek mu) to ASCII u."""
    return v.replace("µ", "u").replace("μ", "u")


# Resistor tolerance suffix codes (IEC). F overlaps with farad and K/M
# overlap with multipliers, so we only strip these as tolerance when their
# position is unambiguous.
_RES_TOL_AFTER_MULT_RE = re.compile(
    # 4K7J / 10KF / R22F / 100KK — multiplier letter present earlier, then
    # a single tolerance code at the end.
    r"^([\d.]*[RKMG][\d.]*)([FGJKM])$",
    re.IGNORECASE,
)
_RES_TOL_PURE_DIGITS_RE = re.compile(
    # 100J / 470F — pure digits then F or J at the end. K, M, and G are
    # kept as multipliers in this position (the multiplier reading is far
    # more common in real BOMs than the tolerance reading).
    r"^([\d.]+)([FJ])$",
    re.IGNORECASE,
)


def _strip_resistor_tolerance(s: str) -> str:
    """Drop a trailing tolerance letter from a resistor input string.

    "4K7J" → "4K7"; "10KF" → "10K"; "100J" → "100"; "10K" stays "10K"
    (single trailing K is the multiplier in pure-digits-then-letter form).
    Tolerance is dropped from the value string entirely — we don't track
    tolerance percentage today.
    """
    m = _RES_TOL_AFTER_MULT_RE.match(s)
    if m:
        return m.group(1)
    m = _RES_TOL_PURE_DIGITS_RE.match(s)
    if m:
        return m.group(1)
    return s


# Resistor multiplier letters per IEC / RKM notation. R also acts as
# "ohms anchor" so "R22" = 0.22Ω and "220R" = 220Ω.
_RES_MULTIPLIER: dict[str, float] = {
    "R": 1.0,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}

# Capacitor multiplier letters. Both µ and μ map to 'u' before parsing.
# Case-insensitive — caps don't go big enough for kilo/mega ambiguity to
# matter, and the spec only lists p/n/u/m for caps.
_CAP_MULTIPLIER: dict[str, float] = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
}


def _parse_resistor_magnitude(s: str) -> float | None:
    s = _strip_resistor_tolerance(s)

    # R-prefix: "R22" = 0.22Ω, "K47" = 0.47kΩ, etc.
    m = re.match(r"^([RKMG])(\d+)$", s, re.IGNORECASE)
    if m:
        mult = _RES_MULTIPLIER[m.group(1).upper()]
        try:
            return float(f"0.{m.group(2)}") * mult
        except ValueError:
            return None

    # Letter-as-decimal-point: "4K7" = 4.7k, "2M2" = 2.2M
    m = re.match(r"^(\d+)([RKMG])(\d+)$", s, re.IGNORECASE)
    if m:
        mult = _RES_MULTIPLIER[m.group(2).upper()]
        try:
            return float(f"{m.group(1)}.{m.group(3)}") * mult
        except ValueError:
            return None

    # Standard form: "10k" / "100" / "4.7k" / "1.2K"
    m = re.match(r"^([\d.]+)\s*([RKMG])?$", s, re.IGNORECASE)
    if m:
        try:
            num = float(m.group(1))
        except ValueError:
            return None
        if m.group(2):
            return num * _RES_MULTIPLIER[m.group(2).upper()]
        return num

    return None


def _parse_capacitor_magnitude(s: str) -> float | None:
    # Strip optional trailing F (farad indicator): "10uF" → "10u"
    s_no_f = re.sub(r"[Ff]$", "", s) if len(s) > 1 else s

    # 3-digit code (only when input is exactly 3 digits): "104" = 100nF.
    # Parsed as AB × 10^N picofarads.
    if re.match(r"^\d{3}$", s_no_f):
        ab = int(s_no_f[:2])
        n = int(s_no_f[2])
        return ab * (10 ** n) * 1e-12

    # u-prefix decimal: "u47" = 0.47uF, "n47" = 0.47nF, "p47" = 0.47pF.
    m = re.match(r"^([pnumPNUM])(\d+)$", s_no_f)
    if m:
        mult = _CAP_MULTIPLIER[m.group(1).lower()]
        try:
            return float(f"0.{m.group(2)}") * mult
        except ValueError:
            return None

    # Letter-as-decimal-point: "4u7" = 4.7uF, "2n2" = 2.2nF
    m = re.match(r"^(\d+)([pnumPNUM])(\d+)$", s_no_f)
    if m:
        mult = _CAP_MULTIPLIER[m.group(2).lower()]
        try:
            return float(f"{m.group(1)}.{m.group(3)}") * mult
        except ValueError:
            return None

    # Standard form: "100n" / "10u" / "47p" / "1.5n" / bare "1" (= 1F)
    m = re.match(r"^([\d.]+)\s*([pnumPNUM])?$", s_no_f)
    if m:
        try:
            num = float(m.group(1))
        except ValueError:
            return None
        if m.group(2):
            return num * _CAP_MULTIPLIER[m.group(2).lower()]
        return num  # bare number — interpret as farads (rare but unambiguous)

    return None


def value_magnitude(raw: str, kind: str) -> float | None:
    """Parse a passive value to a numeric magnitude in base units.

    Resistors → ohms. Capacitors → farads. ICs / transistors / diodes
    return None — their value is a part number, not a magnitude.

    Follows IEC / RKM resistor notation and 3-digit-code capacitor
    notation as documented in the README. Returns None if the input
    can't be parsed.
    """
    if not raw or kind in ("ic", "transistor", "diode"):
        return None
    s = _strip_micro(raw.strip())
    if not s:
        return None

    if kind == "resistor":
        return _parse_resistor_magnitude(s)
    if kind in ("film-cap", "electrolytic"):
        return _parse_capacitor_magnitude(s)
    return None


def _format_engineering(mag: float, kind: str) -> str:
    """Render a numeric magnitude back to canonical engineering notation.

    Resistors use R/k/M/G; capacitors use p/n/u/m. Uses %g formatting so
    integer-valued numbers print without a trailing ".0" ("10k" not "10.0k").
    """
    if mag == 0:
        return "0"
    if kind == "resistor":
        prefixes = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, "")]
    else:  # capacitor kinds
        prefixes = [(1.0, "F"), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p")]
    for div, prefix in prefixes:
        if abs(mag) >= div:
            val = mag / div
            return f"{val:g}{prefix}"
    # Below the smallest prefix (e.g., sub-ohm value or sub-pF cap)
    return f"{mag:g}"


def normalize_value(raw: str, kind: str) -> str:
    """Collapse cosmetic differences so equivalent forms share a single key.

    For passives we parse to a numeric magnitude and re-render in canonical
    engineering form ("100K Ohm" → "100k", "104" → "100n", "4K7" → "4.7k").
    Inputs that don't parse fall back to the old cosmetic normalization
    (lowercase + strip spaces and ohm/watt noise) so we don't lose data.
    """
    if not raw:
        return ""
    v = _strip_micro(raw.strip())
    if kind in ("ic", "transistor", "diode"):
        return _WS.sub("", v.upper())

    # Pots and switches both store a free-form descriptor as their "value"
    # (B25K / SPDT (On/Off/On)) rather than a numeric magnitude. The pot
    # path matters specifically because W-taper pots collide with the
    # _UNIT_NOISE wattage stripper ("W10K" → "10k" loses the taper letter).
    # Switches go down the same lane for consistency — preserve the raw
    # description so SPDT and DPDT and 3PDT all stay distinct keys.
    if kind in ("pot", "switch"):
        return _WS.sub("", v.lower())

    # Other passives (resistor / cap kinds): prefer the numeric canonical
    # form so equivalent inputs always produce the same key. Strip noise
    # first so "100k 1/4w" and similar still parse.
    cleaned = _UNIT_NOISE.sub("", v).strip()
    cleaned = _WS.sub("", cleaned)

    # For resistors, also drop the tolerance suffix before checking magnitude
    # (so "10KF" → 10000Ω, not None). _parse_resistor_magnitude does this
    # internally, but the cosmetic fallback below needs the same treatment
    # to keep "10kf" and "10k" producing the same value_norm.
    if kind == "resistor":
        cleaned = _strip_resistor_tolerance(cleaned)

    mag = value_magnitude(cleaned, kind)
    if mag is not None:
        return _format_engineering(mag, kind)

    # Unparseable — fall back to old cosmetic form.
    return cleaned.lower()


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
