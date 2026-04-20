# pedal-bench

Bench copilot for DIY guitar pedal builds. Drop a PedalPCB PDF and the
tool extracts the pedal name, enclosure, and full BOM; then walk it
through ordering, drilling, soldering, finishing, and debugging — all
in one place.

**Status:** v2 web UI is live on `v2/web-ui`. All major features below
are working end-to-end.

![status badge — v2 in progress](https://img.shields.io/badge/v2-in%20progress-emerald)

## Features

| Area | What you can do |
|---|---|
| **One-drop PDF ingestion** | Drop a PedalPCB PDF on the home page → tool extracts title, enclosure, BOM, caches the wiring diagram. Review screen lets you tweak name / enclosure before committing. |
| **Drill designer** | SVG unfolded-enclosure canvas. Click to place holes, drag to reposition, scroll-wheel to resize, overflow auto-flags. Smart-layout presets: 2×2 pot grid, evenly-spaced jack row, mirror across X/Y, center. Paste Tayda Box Tool coordinates directly. |
| **3D-printable drill guides** | Per-face wrap-around shell STLs via `build123d`, one click from the drill designer, downloadable from the browser. |
| **Panel artwork export** | Print-ready SVG (vector) or 600-DPI PNG with knob labels and pedal title at 1:1 scale — for water-slide decals or UV print workflows. |
| **BOM editor** | Dense, inline-editable table. Polarity-sensitivity flag auto-recomputes when you edit the Type cell. Filter box for quick lookup. |
| **Bench mode** | Grouped build-along checklist in solder order (resistors → diodes → small caps → ICs → transistors → electros → pots). Orientation hints on polarity-sensitive rows with per-category defaults. Filters for "polarity only" and "pending only" + live progress bar. |
| **Value decoder** | Bidirectional resistor (text ↔ "4K7" ↔ 4-band colors) and capacitor parsing. Always-reachable from the header. Pure-TS port of the Python decoders, zero latency. |
| **Debug helper** | Per-IC expected pin voltages for 7 seed chips (JRC4558 / TL072 / OPA2134 / NE5532 / JRC4580 / LM308 / TL074). Type measured voltages, get "ok" or "out of range" chip. Plus audio-probe procedure and common-failure triage. |

## Architecture

- **Backend** — Python 3.12 · FastAPI · `build123d` (parametric STL) ·
  `pdfplumber` (BOM + vector layout) · `pypdfium2` (page rasterization)
  · `Pillow`. Lives in [backend/](./backend/).
- **Frontend** — React 19 · TypeScript 5 · Vite 6 · Tailwind v4 ·
  TanStack Query · native SVG canvas (no Canvas/Konva/Fabric). Lives
  in [frontend/](./frontend/).
- **Storage** — JSON-per-project on disk. Relational SQLite layer
  planned for Phase 2 (cross-project queries, Observations).

See [docs/architecture.md](./docs/architecture.md) for the stack
decision record.

## Requirements

- Windows 10 / 11 (dev tested; macOS / Linux should work, untested)
- Python 3.12
- Node.js LTS (18+, tested with 24.15)
- A 3D printer for the drill guides (PLA / PETG)

## Setup

Works from PowerShell, cmd, or bash:

```bash
npm install        # pulls in concurrently (the workspace dev tool)
npm run setup      # creates .venv, pip-installs backend, npm-installs frontend
```

Setup pulls ~300 MB of CAD bindings (`build123d` needs Open CASCADE) —
the first install takes a few minutes.

## Run

```bash
npm run dev
```

Starts both servers in one terminal:
- FastAPI on **http://127.0.0.1:8642** (API docs at `/docs`)
- Vite on **http://127.0.0.1:5173** ← open this in your browser

The Vite dev server proxies `/api/*` to the backend, so everything is
same-origin during development. Ctrl+C stops both.

## Other commands

```bash
npm run dev:backend    # only FastAPI
npm run dev:frontend   # only Vite
npm run test           # Python test suite
npm run typecheck      # tsc --noEmit on the frontend
npm run build          # production build of the frontend
```

A `Makefile` is provided for git bash / WSL users with the same targets.

## Repo layout

```
pedal-bench/
├── backend/
│   ├── pyproject.toml
│   ├── pedal_bench/
│   │   ├── api/                FastAPI app, routes, DTOs
│   │   │   ├── app.py
│   │   │   ├── deps.py
│   │   │   ├── schemas.py
│   │   │   └── routes/         bom, debug, enclosures, holes, pdf, projects, stl, tayda
│   │   ├── core/               models, stores, decoders, hint library
│   │   ├── io/                 PedalPCB BOM + title extractor, Tayda coords,
│   │   │                       PDF→image, build123d STL builder
│   │   └── data/               enclosures, suppliers, orientation hints,
│   │                           debug topologies
│   └── tests/                  105 pytest cases
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── api/                typed API client
│       ├── components/
│       │   ├── drill/          canvas geometry, hole inspector,
│       │   │                   smart layouts, Tayda paste, panel artwork
│       │   ├── pdf/            drop zone + review modal
│       │   └── ui/             buttons, inputs, dialog, cards
│       ├── layout/             app shell (sidebar + header)
│       ├── lib/                TS port of backend decoders
│       └── pages/              HomePage, DecoderPage, ProjectPage
│           └── project/        Overview, Drill, BOM, Bench, Debug tabs
├── projects/                   per-build folders (your data, gitignored)
├── docs/
│   └── architecture.md
├── package.json                workspace scripts (npm run dev / setup / test)
├── Makefile                    git-bash equivalents
└── README.md
```

## Tests

```bash
npm run test
```

105 backend tests cover value decoders, PedalPCB BOM extraction, Tayda
coordinate parsing, and STL generation (watertight meshes + bbox
assertions). Drop a real PedalPCB PDF at
`backend/tests/fixtures/sherwood.pdf` to enable the end-to-end BOM
integration test (otherwise auto-skipped).

Frontend typecheck: `npm run typecheck`.

## Roadmap

- [x] v1 tkinter MVP (Phases 0–3)
- [x] v2 Phase 1 — web UI scaffold
- [x] v2 Phase 2 — drill designer (visual, drag-to-place, STL export)
- [x] v2 Phase 3 — port BOM / bench / decoder from v1
- [x] v2 Phase 4 — one-drop PDF ingestion
- [x] v2 Phase 5 — debug helper (expected voltages + triage)
- [x] v2 Phase 6 — panel artwork export
- [ ] Phase 7 — SQLite-backed cross-project queries + Observations
- [ ] Phase 8 — vector-circle extraction from drill-template PDF page
- [ ] Phase 9 — supplier API integration (Mouser / DigiKey stock + price)
- [ ] Phase 10 — hosted deployment, auth, build sharing

## License

MIT (tentative — will commit to a LICENSE file before the first tagged release).
