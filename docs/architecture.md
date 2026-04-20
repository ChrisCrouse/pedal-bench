# pedal-bench Architecture (v2)

_Decision record written 2026-04-19 at the start of the v2 web-UI rewrite.
Append-only; document each subsequent architectural decision as a dated
entry below rather than editing history._

## Why v2 exists

The v1 tkinter app (Phases 0–3, tag `v1-tkinter-final` in git history) proved
the domain model and the core pipelines (PedalPCB BOM extraction, value
decoding, orientation hints, `build123d` STL generation, Tayda coordinate
import). It failed on user experience: no visual drill-template feedback, no
PDF auto-ingestion, no room for schematic overlays, no sharing, and a
frontend stack (tkinter) that would fight every future feature.

v2 is a rewrite of the presentation layer and a re-homing of the persisted
domain model onto a relational store. The Python services that already work
(`pedal_bench.core.*`, `pedal_bench.io.*`, seeded catalogs) move behind a
FastAPI surface unchanged.

## The defining product bet

**One-drop PedalPCB PDF → complete, editable build package in under a
minute.** Every other feature is table stakes. If we cannot deliver that,
the product has nothing differentiated.

## Stack decisions

| Concern | Pick | Rationale |
|---|---|---|
| Backend | **FastAPI + Uvicorn** | Async-native, Pydantic validation for free, built-in OpenAPI/Swagger for API docs, clean dep-injection story. Django is too heavy; Flask lacks typing and schema. |
| Python packaging | **`pyproject.toml` + `pip install -e .`** | Modern standard. No poetry/uv hard dep, just pip. `pedal_bench` becomes a proper installable package. |
| Persistence (now) | **SQLite + SQLAlchemy 2.0 + Alembic** | Relational queries are core to the knowledge-graph vision ("every build using OPA2134PA"). SQLite is zero-config locally. |
| Persistence (later) | **Postgres** | Same SQLAlchemy models, just swap the driver URL. Designed-in from day one. |
| Per-project files | **Project folder on disk** (PDFs, STLs, photos) | Too bulky for DB. DB stores a relative path; atomic writes on disk. |
| Frontend framework | **React 19 + TypeScript 5 + Vite** | Industry standard for dense interactive tools. TypeScript catches the kind of bugs a pedal builder shouldn't have to think about. |
| Styling | **Tailwind + shadcn/ui (Radix)** | shadcn gives us accessible, polished components without hand-rolling every modal/select/popover. Copy-in, not npm dep. |
| Server state | **TanStack Query** | Caching + invalidation for the API, zero hand-rolled fetch. |
| Client state | **Zustand** where needed | Lightweight. Avoid Redux overhead. |
| Forms | **react-hook-form + zod** | Schema-validated forms are critical for BOM/hole editing. |
| Routing | **react-router-dom 6** | Conventional, fine. |
| SVG canvas (drill designer) | **Native SVG + React event handlers** | SVG is *made* for this; no canvas/engine dependency needed. |
| 3D preview | **`<model-viewer>` (Google)** | Drop-in web component, zero Three.js glue. If we outgrow it, swap to `@react-three/fiber`. |
| Dev server | **Vite proxy → FastAPI** | Single-origin during dev. Production builds the frontend into `backend/pedal_bench/static/` and FastAPI serves it at `/`. |
| Auth (now) | **None, single-user local** | Skip complexity until it matters. |
| Auth (later) | **JWT with refresh** | Plan the seams: every row has `user_id`, every endpoint has `current_user` dep. |
| Desktop wrapper | **None** (`pedal-bench serve` → opens `http://localhost:8642` in browser) | Electron/Tauri are unnecessary for a self-hosted tool; the browser already has everything we need (3D, SVG, webcam, print, PDF). |
| CI | **GitHub Actions** | `pytest` + `ruff` + `tsc --noEmit` + `vitest` on every PR. To be added Phase 1.5. |
| License | **To be chosen** | Default MIT unless Chris picks otherwise. Recorded in `LICENSE`. |

## Repo layout

```
pedal-bench/
├── backend/
│   ├── pyproject.toml
│   ├── pedal_bench/
│   │   ├── api/            FastAPI app, routes, deps
│   │   ├── core/           models, stores, decoders (from v1 app/core)
│   │   ├── io/             pdf, tayda, stl (from v1 app/io)
│   │   ├── db/             SQLAlchemy models + Alembic migrations
│   │   ├── data/           shipped catalogs (enclosures, suppliers, hints)
│   │   ├── server.py       uvicorn entry point
│   │   └── __main__.py     `python -m pedal_bench` → serve
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/           TanStack Query clients
│       ├── components/    UI primitives (shadcn-generated)
│       └── pages/         route-level screens
├── docs/
│   └── architecture.md    (this file)
├── Makefile               `make dev`, `make test`, `make build`
├── README.md
└── .gitignore
```

## Service boundaries

- **Frontend never touches disk.** Always goes through the backend API.
- **Backend never runs frontend JS.** Plain JSON APIs, no SSR.
- **Catalogs (enclosures, suppliers, hints) are read-only data shipped in
  the backend package.** Edited via PR to the repo, not via the API.
- **User projects are mutable data stored per-user** (initially: all rows
  belong to the "local" pseudo-user).

## Data model (draft)

The v1 dataclasses become the API DTOs. The SQLAlchemy models layer a
relational schema on top. Key additions over v1:

- `Circuit` — topology classification (Tube Screamer, Big Muff, etc.)
  with expected pin voltages and canonical BOM fingerprint.
- `Pedal` — a reusable `Circuit + Enclosure + Artwork` spec.
- `Build` — a physical instance of a `Pedal`. Current projects become builds.
- `BuildEvent` — timestamped `{photo, note, measurement, substitution}`
  tied to a Build.
- `Observation` — learned rules surfaced as warnings on future builds.

Implementation note: Phase 1 of v2 keeps the v1 JSON persistence and fronts
it with a FastAPI layer. The SQLAlchemy rewrite happens in Phase 2, once
the web UI surfaces what the data model actually needs to answer.

## Migration strategy from v1

1. Branch `v2/web-ui` from `main`.
2. `git mv app/{core,io,data} backend/pedal_bench/{core,io,data}` — preserve
   blame / history.
3. Delete `app/ui/` and `app/main.py`. They live on in git history.
4. Rename imports `app.*` → `pedal_bench.*` in tests and modules.
5. Scaffold FastAPI around the existing stores — no behavior change.
6. Ship the drill designer as the first user-facing v2 screen (it's
   where tkinter failed hardest; proves the UX bet).
7. Port BOM / bench / decoder / project views screen-by-screen.
8. Add PDF-ingestion pipeline (including vector drill-coord extraction).
9. Add SQLAlchemy + Circuit/Pedal/Build model; migrate projects JSON → DB.
10. Add auth, multi-user, hosted deployment story.

## Open questions (for Chris, not blockers)

- **License?** Defaulting to MIT. Override if needed.
- **Hosted domain?** If/when we host publicly. Not blocking.
- **Branding?** Logo / favicon / colors. Can be placeholder until it ships
  publicly.

## Out of scope for v2 Phase 1

- Mobile companion app
- Real-time collaboration
- Community sharing service (export works; hosting doesn't)
- Plugin marketplace
- Supplier API integration (Mouser, DigiKey)
- LLM features

These are Phase 2+ and the v1 architecture doesn't preclude any of them.

---

## Decision log

- **2026-04-19** — Initial v2 architecture recorded. Branch `v2/web-ui`
  created. Stack decisions above are the point of departure.
- **2026-04-19** — Phase 2 (drill designer) shipped. SVG + native
  pointer events proved correct for the canvas; no Canvas/Konva needed.
  Enclosures reoriented to Tayda portrait convention (face A width = short
  physical dim, height = long dim). All 105 tests re-verified.
- **2026-04-19** — Phase 3 (port v1 features) shipped. TS port of the
  Python decoders kept in sync with pytest coverage. New thin routes
  `PUT /projects/{slug}/bom` and `PUT /projects/{slug}/progress`.
- **2026-04-19** — Phase 4 (PDF one-drop) shipped. Extractor uses
  biggest-font-on-page-1 for title and "<enclosure> Enclosure" header
  regex for enclosure. Two endpoints: `/pdf/extract` (preview) and
  `/projects/from-pdf` (atomic create). Warnings returned in the
  preview payload so the UI surfaces graceful fallbacks.
- **2026-04-19** — Phase 5 (debug helper) shipped. Seed dataset of
  7 common pedal ICs with per-pin expected voltages + tolerances at
  9V / VREF=4.5V, audio-probe procedure, and failure triage table.
- **2026-04-19** — Phase 6 (panel artwork) shipped. Pure-frontend
  SVG/PNG generation. No backend endpoint needed — the data is already
  on the client.
- **2026-04-19** — Top-level `ErrorBoundary` added at `main.tsx` root.
