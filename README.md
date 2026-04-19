# pedal-bench

Bench copilot for DIY guitar pedal builds — PedalPCB BOM import, build
checklist, and 3D-printable drill guides.

A Windows desktop tool that's designed to sit open next to your soldering
iron, not just during ordering. Python 3.12 + tkinter, standalone, no
cloud, no login, no accounts — your builds live as JSON + PDFs in a
`projects/` folder you own.

## What it does

- **Projects** — one folder per pedal. Status transitions (planned →
  ordered → building → finishing → done), attached source PDFs, notes.
- **BOM import** — parses the BOM table straight out of a PedalPCB PDF
  via `pdfplumber`. Auto-tags polarity-sensitive rows (diodes, electros,
  ICs, transistors, LEDs).
- **Bench mode** — grouped build-along checklist (resistors → diodes →
  small caps → ICs → transistors → large caps → pots). Tick as you
  solder. Polarity-sensitive rows show orientation hints (per-pedal
  overrides + keyword defaults); double-click to customize a hint.
  Filters for "polarity-sensitive only" / "pending only".
- **Value decoder** — always-visible side panel. Type `4K7` → `4.7 kΩ` +
  color bands. Type `100n` → `100 nF`. Pick colors from dropdowns → get
  the value. Bidirectional, zero-latency reference you can consult
  dozens of times per session.
- **3D-printable drill guides** — enter hole coordinates in
  [Tayda Box Tool](https://www.taydaelectronics.com/hardware/enclosures/custom-drilled-boxes.html)
  format (side A/B/C/D/E, x/y mm from center of face, diameter mm).
  Exports one wrap-around shell STL per face with the holes you need.
  Shell slips over the enclosure's outer dimensions and self-locates —
  no clamping, no marking out with a ruler.

Built around the PedalPCB build-doc format and Hammond enclosure dims
(1590A / B / BB, 125B, 1590DD, 1590XX).

## Requirements

- **Windows 10 or 11** (works on other OSes in theory; tkinter styling
  and HiDPI calls are Windows-tuned)
- **Python 3.12**
- **A 3D printer** for the drill guides (PLA or PETG)

## Setup

From the repo root:

```bash
# Create the venv
"C:/Users/Chris/AppData/Local/Programs/Python/Python312/python.exe" -m venv .venv

# Install runtime deps
.venv/Scripts/python.exe -m pip install -r requirements.txt

# Optional: dev deps for running the test suite
.venv/Scripts/python.exe -m pip install pytest trimesh
```

Note: `build123d` pulls in OCP (Open CASCADE Python bindings), roughly
300 MB of CAD kernel. This is the parametric STL generator — it takes
~20–30 s to install.

## Run

```bash
.venv/Scripts/python.exe -m app.main
```

Then in the app:

1. **File → New Project…** — name + enclosure
2. **Project tab → Attach PDF…** — your PedalPCB build document
3. **BOM tab → Import from PDF** — populates the component list
4. **Bench tab** — tick components as you solder them
5. **Drill tab → Paste Tayda…** — paste hole coordinates, then
   **Export STLs**

## Tests

```bash
.venv/Scripts/python.exe -m pytest
```

Ships with 100+ tests covering:

- Resistor / cap text parsing and color-code round-trips
- PedalPCB BOM extraction (header detection, blank-row handling,
  embedded newlines, repeated headers across pages)
- Tayda import across CSV / TSV / whitespace / JSON + multiple column
  naming conventions
- STL generator produces watertight meshes with correct bounding boxes
  for Sherwood-shaped hole sets on a 125B

A fixture PDF is expected at `tests/fixtures/sherwood.pdf` for the
end-to-end BOM integration test. Without it, that single test is
auto-skipped.

## Data layout

```
pedal-bench/
├── app/
│   ├── main.py               entry point
│   ├── core/                 models, persistence, decoders
│   ├── io/                   PDF, Tayda, STL
│   ├── ui/                   tkinter views + decoder side panel
│   └── data/                 shipped reference data
│       ├── enclosures.json     Hammond enclosure dimensions
│       ├── suppliers.json      default supplier list
│       └── orientation_hints.json
├── projects/                 one folder per build (your data)
│   └── <slug>/
│       ├── project.json        name, BOM, holes, build progress, notes
│       ├── source.pdf          attached PedalPCB document
│       ├── wiring.png          cached render of page 4
│       ├── drill/
│       │   ├── holes.json      canonical Tayda-shape hole list
│       │   └── guide_<face>.stl
│       └── photos/
├── inventory.json            global parts-on-hand (hybrid tracking)
├── tests/
└── requirements.txt
```

Everything under `projects/` and `inventory.json` is yours — plain JSON
you can hand-edit, diff, or back up with git.

## Status

MVP in progress. Working today:

- [x] Phase 0 — scaffold, tkinter shell, seed catalog data
- [x] Phase 1 — projects + PedalPCB BOM import
- [x] Phase 2 — bench mode checklist + value decoder
- [x] Phase 3 — drill-template STL generator
- [ ] Phase 3.5 — wiring-diagram viewer (pan/zoom page 4 image)
- [ ] Phase 4 — enclosure layout designer (2D drag/snap/clearance)
- [ ] Phase 5 — shopping list with supplier consolidation; substitution
      hints; finishing tracker with dry-time countdowns
- [ ] Phase 6 — markdown / PDF build-log export; component reference UI

## Library choices

| Concern         | Pick          | Notes                                                                |
|-----------------|---------------|----------------------------------------------------------------------|
| PDF tables      | `pdfplumber`  | PedalPCB BOMs are clean columnar text — direct table extraction.     |
| PDF → image     | `pypdfium2`   | Lightweight, no external Poppler install needed on Windows.          |
| Parametric STL  | `build123d`   | Modern Pythonic CAD API. Booleans produce watertight closed meshes. |
| GUI             | `tkinter`/`ttk` | Stdlib. Treeview + PanedWindow are enough for Phase 1–3.           |

## License

TBD — add one before publishing.
