# pedal-bench

Bench copilot for DIY guitar pedal builds. Turn a PedalPCB PDF into a
complete fabrication package: BOM, build checklist with orientation hints,
value decoder reference, and 3D-printable drill guides — in the browser.

**Status:** v2 rewrite in progress on branch `v2/web-ui`. Backend runs;
frontend scaffold renders the enclosure catalog end-to-end. Drill
designer and PDF ingestion land next.

## Architecture

- **Backend** — Python 3.12 · FastAPI · SQLAlchemy (coming) · build123d
  · pdfplumber · pypdfium2. Lives in [backend/](./backend/).
- **Frontend** — React 19 · TypeScript · Vite · Tailwind v4 · TanStack
  Query. Lives in [frontend/](./frontend/).
- **Storage** — JSON-per-project on disk today; SQLite-backed relational
  model planned for Phase 2.

See [docs/architecture.md](./docs/architecture.md) for the full decision
record and rationale.

## Requirements

- Windows 10 / 11 (other OSes fine; dev has been on Windows)
- Python 3.12 — [python.org](https://www.python.org/downloads/)
- Node.js LTS — [nodejs.org](https://nodejs.org/) (install via `winget install OpenJS.NodeJS.LTS`)
- A 3D printer for the drill guides (PLA / PETG)

## Setup

```bash
make install
```

This creates `.venv/`, installs the backend in editable mode
(`pip install -e "backend[dev]"`), and runs `npm install` in the frontend.

## Run

```bash
make dev
```

Starts:
- FastAPI on **http://127.0.0.1:8642** (API docs at `/docs`)
- Vite on **http://127.0.0.1:5173** (open this in your browser)

The Vite dev server proxies `/api/*` to the backend, so everything is
same-origin during development.

Stop with Ctrl+C.

## Other commands

```bash
make backend      # run only the FastAPI server
make frontend     # run only the Vite dev server
make test         # run the Python test suite
make typecheck    # run `tsc --noEmit` on the frontend
make build        # production build of the frontend
make clean        # wipe .venv, node_modules, dist, caches
```

## Repo layout

```
pedal-bench/
├── backend/
│   ├── pyproject.toml
│   ├── pedal_bench/
│   │   ├── api/                FastAPI app, routes, DTOs
│   │   ├── core/               models, persistence, decoders
│   │   ├── io/                 PDF, Tayda, STL (build123d)
│   │   └── data/               shipped catalogs (enclosures, suppliers, hints)
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── api/                typed API client
│       └── pages/              route-level screens
├── projects/                   per-build folders (your data)
├── docs/
│   └── architecture.md
├── Makefile
└── README.md
```

## Tests

```bash
make test
```

105 tests cover value decoders, PedalPCB BOM extraction, Tayda coordinate
parsing, and STL generation (watertight mesh + bbox assertions). Drop a
real PedalPCB PDF at `backend/tests/fixtures/sherwood.pdf` to enable the
end-to-end BOM integration test (otherwise auto-skipped).

## Roadmap

- [x] Phase 0 — scaffold + catalogs (v1, tkinter)
- [x] Phase 1 — projects + BOM import (v1, tkinter)
- [x] Phase 2 — bench mode + value decoder (v1, tkinter)
- [x] Phase 3 — drill STL generator (v1, tkinter)
- [x] v2 — web UI scaffold (FastAPI + React), enclosure catalog wired through
- [ ] Phase 4 — drill designer (SVG unfolded enclosure, drag-to-place, live STL preview)
- [ ] Phase 5 — one-drop PDF ingestion (title / enclosure / BOM / vector drill coords / wiring image)
- [ ] Phase 6 — schematic-linked bench mode, debug helper with expected pin voltages
- [ ] Phase 7 — supplier API integration, substitution hints, finishing tracker
- [ ] Phase 8 — knowledge base across builds, pattern-learned warnings
- [ ] Phase 9 — hosted deployment, auth, sharing

## License

MIT (tentative — will commit to a LICENSE file before the first tagged release).
