# pedal-bench

Bench copilot for DIY guitar pedal builds. Drop a PedalPCB PDF (or paste a
product URL), and the tool extracts the pedal name, enclosure, and full
BOM, then walks you through ordering, drilling, soldering, finishing, and
debugging — all in one place.

![status — working](https://img.shields.io/badge/status-working-emerald)
![license — MIT](https://img.shields.io/badge/license-MIT-blue)

## Features

| Area | What you can do |
|---|---|
| **One-drop / one-paste ingestion** | Drop a PedalPCB PDF, or paste a `pedalpcb.com/product/...` URL. Tool fetches the build doc, extracts title, enclosure, BOM, drill holes, and caches the wiring diagram. AI fallback handles older "Parts List" PDFs and image-only drill templates. |
| **Drill designer** | SVG unfolded-enclosure canvas. Click to place holes, drag to reposition, scroll-wheel to resize, multi-select, undo/redo, mirror-group symmetry. Smart-layout presets. Paste Tayda Box-Tool coordinates directly. |
| **Print template + 3D drill guides** | Print-ready 1:1 mm SVG/PNG with crosshairs at every hole center for center-punching (no printer-friendly enclosure required). Or one-click parametric STL drill guides via `build123d` for 3D printing. |
| **Panel artwork export** | Print-ready SVG (vector) or 600-DPI PNG with knob labels and pedal title at 1:1 scale — for water-slide decals or UV print workflows. |
| **BOM editor + photo verification** | Dense, inline-editable table. AI-powered "verify" button on each row: snap a photo of the part, get a match / mismatch / unsure verdict before soldering. |
| **Order from Tayda** | One-click dialog dedupes your BOM by part, tailors per-kind search queries (resistor, cap, pot, IC), and opens Tayda search-result tabs in batches of 5. Per-part "ordered" checkboxes save shopping progress per project across sessions. |
| **Build-log photos** | Drag-drop image upload per project. Captioned, timestamped, full-viewport view, easy delete. |
| **Bench mode** | Grouped build-along checklist in solder order. Orientation hints on polarity-sensitive rows. Filters for "polarity only" and "pending only" + live progress bar. |
| **Value decoder** | Bidirectional resistor (text ↔ "4K7" ↔ 4-band colors) and capacitor parsing. Pure-TS port of the Python decoders, zero latency. |
| **Debug helper + AI diagnosis** | Per-IC expected pin voltages for 7 seed chips, audio-probe procedure, common-failure triage. AI diagnosis card reasons over symptom + measured voltages + cached wiring image and tells you what to probe next. |

## Quickstart

```bash
git clone https://github.com/ChrisCrouse/pedal-bench
cd pedal-bench
npm install        # workspace tools (concurrently)
npm run setup      # creates .venv, pip-installs backend, npm-installs frontend
npm run dev        # starts both servers in one terminal
```

Open **http://127.0.0.1:5173** in your browser.

The first `setup` pulls ~300 MB of CAD bindings (`build123d` needs Open
CASCADE) and takes a few minutes. After that, `npm run dev` starts in
seconds.

## Requirements

- Python 3.12 or 3.13 (3.14 isn't supported yet — `pypdfium2` / `build123d` don't ship 3.14 wheels)
- Node.js LTS (18+, tested with 24.15)
- Optional: 3D printer for parametric drill guides (PLA / PETG). Without
  one, use the print-ready 1:1 template instead — tape, center-punch,
  drill.

Tested on Windows 10/11 daily; macOS / Linux should work but aren't tested.

## AI features (optional)

A few features call Anthropic's Claude API:

- **BOM extraction fallback** for older PedalPCB PDFs that use a
  multi-column "Parts List" layout (~$0.01 per PDF, only when the
  deterministic table parser fails).
- **Drill template fallback** for image-only / unusual drill pages
  (~$0.01 per PDF, also only on failure).
- **Component photo verification** — verify button on every BOM row
  (~$0.005–0.01 per check).
- **AI diagnosis** in the Debug tab (~$0.02–0.05 per call, cheaper on
  repeat thanks to schematic prompt caching).

**Modern PedalPCB PDFs ingest fully without any key.** Only the
AI-specific features above need one.

Two ways to provide a key:

1. **Self-host:** copy `backend/.env.example` to `backend/.env` and set
   `ANTHROPIC_API_KEY`. Loaded at backend startup.
2. **Bring-your-own-key (BYOK):** any user can paste their key into
   **Settings** in the web UI. Stored in browser localStorage, sent as a
   request header on every API call, **never persisted server-side.**

Get a key at [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).
**Set a usage limit** at [console.anthropic.com/settings/limits](https://console.anthropic.com/settings/limits)
before heavy use — the tool's normal usage is around $1–5/month per active
build, but a runaway loop on pay-as-you-go can cost more.

The header in the app shows AI status: "AI: ready" / "AI: your key" /
"Set up AI →". If you see the third one, click it.

## Other commands

```bash
npm run dev:backend    # only FastAPI
npm run dev:frontend   # only Vite
npm run test           # Python test suite (162 tests)
npm run typecheck      # tsc --noEmit on the frontend
npm run build          # production build of the frontend
```

A `Makefile` is provided for git bash / WSL users with the same targets.

## Architecture

- **Backend** — Python 3.12/3.13 · FastAPI · `build123d` (parametric STL) ·
  `pdfplumber` (BOM + vector layout) · `pypdfium2` (page rasterization)
  · `Pillow` · `anthropic` (optional AI features). Lives in [backend/](./backend/).
- **Frontend** — React 19 · TypeScript 5 · Vite 6 · Tailwind v4 ·
  TanStack Query · native SVG canvas (no Canvas/Konva/Fabric). Lives
  in [frontend/](./frontend/).
- **Storage** — JSON-per-project on disk. Per-user, per-machine.

See [docs/architecture.md](./docs/architecture.md) for the stack
decision record.

## Repo layout

```
pedal-bench/
├── backend/
│   ├── pyproject.toml
│   ├── .env.example                  # template — copy to .env if self-hosting
│   ├── pedal_bench/
│   │   ├── api/
│   │   │   ├── app.py
│   │   │   ├── deps.py
│   │   │   ├── schemas.py
│   │   │   └── routes/               bom · debug · diagnose · enclosures
│   │   │                             holes · pdf · photos · projects · stl
│   │   │                             tayda · verify_component · ai_status
│   │   ├── core/                     models, stores, decoders, hint library
│   │   ├── io/                       PedalPCB extractors (deterministic + AI)
│   │   │                             Tayda coords, PDF→image, STL builder
│   │   └── data/                     enclosures, suppliers, orientation hints,
│   │                                 debug topologies
│   └── tests/                        162 pytest cases
├── frontend/
│   └── src/
│       ├── api/                      typed API client (BYOK header injection)
│       ├── components/
│       │   ├── bom/                  table, PCB layout viewer, verify dialog
│       │   ├── debug/                AI diagnosis card
│       │   ├── drill/                canvas geometry, smart layouts, Tayda
│       │   │                         paste, panel artwork, drill template
│       │   ├── overview/             photos section
│       │   ├── pdf/                  drop zone + review modal
│       │   └── ui/                   buttons, inputs, dialog, AI status pill
│       ├── layout/                   app shell (sidebar + header)
│       ├── lib/                      apiKey storage, decoders TS port
│       └── pages/                    Home · Project · Decoder · Settings
├── projects/                         per-build folders (your data, gitignored)
├── docs/
│   └── architecture.md
├── package.json                      workspace scripts
├── LICENSE                           MIT
└── README.md
```

## Tests

```bash
npm run test
```

162 backend tests cover value decoders, PedalPCB BOM extraction
(deterministic + AI parser logic), Tayda coordinate parsing, STL
generation (watertight meshes + bbox assertions), URL fetcher, AI drill
extraction parser, AI BOM extraction parser, AI diagnosis parser, AI
component-verify parser. Drop a real PedalPCB PDF at
`backend/tests/fixtures/sherwood.pdf` to enable the end-to-end BOM
integration test (otherwise auto-skipped).

Frontend typecheck: `npm run typecheck`.

## Roadmap

- [x] v1 tkinter MVP (Phases 0–3)
- [x] v2 web UI — drill designer, BOM, bench mode, debug, decoder
- [x] One-drop / paste-a-URL ingestion + AI fallback for older PDFs
- [x] AI component verification + AI fault diagnosis
- [x] Print-ready drill template (with crosshairs) + build-log photos
- [x] BYOK + public release
- [ ] SQLite-backed cross-project queries + community-corroborated BOMs
- [ ] Supplier API integration (Tayda / Mouser stock + price)
- [ ] DIYLC `.diy` file import
- [ ] Optional hosted instance for non-technical builders

## License

MIT — see [LICENSE](./LICENSE).
