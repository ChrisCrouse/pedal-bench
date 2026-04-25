# pedal-bench

A local workbench for DIY guitar pedal builds. Drop a PedalPCB PDF or
paste a product URL — and walk through ordering, drilling, soldering,
finishing, and debugging in one place.

**Works fully offline.** AI is opt-in for four optional features; the
other ~30 capabilities are deterministic and need no API key, no signup,
and no internet beyond ordering parts. See *[What works without an API
key](#what-works-without-an-api-key)* below.

![status — working](https://img.shields.io/badge/status-working-emerald)
![license — MIT](https://img.shields.io/badge/license-MIT-blue)
![no-key first](https://img.shields.io/badge/no--key-first--class-blue)

## What works without an API key

The core build flow needs nothing beyond Python, Node, and your browser.
Almost everything is deterministic — vector PDF parsing, XML parsing,
SQLite, SVG canvas math, local color-band decoders.

| Area | What you can do |
|---|---|
| **PedalPCB ingestion** | Drop a modern PedalPCB build PDF, or paste a `pedalpcb.com/product/...` URL. Tool fetches the build doc and extracts title, enclosure, BOM, drill holes, wiring diagram via vector parsing — no AI required for current PedalPCB layouts. |
| **Drill designer** | SVG unfolded-enclosure canvas. Click to place holes, drag to reposition, scroll-wheel to resize, multi-select, undo/redo, mirror-group symmetry. Smart-layout presets. Paste Tayda Box-Tool coordinates directly. |
| **Print template + 3D drill guides** | Print-ready 1:1 mm SVG/PNG with crosshairs at every hole center for center-punching. Or one-click parametric STL drill guides via `build123d` for 3D printing. |
| **Panel artwork export** | Print-ready SVG (vector) or 600-DPI PNG with knob labels and pedal title at 1:1 scale — for water-slide decals or UV print workflows. |
| **BOM editor** | Dense, inline-editable table with color-coded chips by component kind, click-to-tag onto the cached PCB layout image, polarity warnings on orientation-sensitive rows. |
| **Bench mode** | Grouped build-along checklist in solder order. Polarity warnings on diodes/electrolytics/transistors. Filters for "polarity only" and "pending only" + live progress bar. |
| **Debug helper** | Per-IC expected pin voltages for 7 seed chips with live "ok / out of range" highlighting as you measure. Audio-probe procedure. Common-failure triage by symptom. |
| **Cross-project inventory** | Inventory page shows every unique part across all your projects with totals — "100K resistor: 18 across 5 projects" — and click any row to drill into which projects use it. SQLite index rebuilt on demand from your JSON store. |
| **Order from Tayda** | One-click dialog dedupes your BOM by part, tailors per-kind search queries (resistor, cap, pot, IC), and opens Tayda search-result tabs in batches of 5. Per-part "ordered" checkboxes save shopping progress per project. |
| **Build-log photos** | Drag-drop image upload per project. Captioned, timestamped, full-viewport view, easy delete. |
| **Value decoder** | Bidirectional resistor (text ↔ "4K7" ↔ 4-band colors) and capacitor parsing. Pure-TS port of the Python decoders, zero latency, fully offline. |

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

## Optional AI features

Four features call Anthropic's Claude API. They're hidden from the UI
when no key is configured, so the no-key experience isn't peppered with
disabled buttons. Add a key in Settings and they appear.

| Feature | What it adds | Cost (typical) |
|---|---|---|
| **BOM extraction fallback** | Reads older PedalPCB "Parts List" PDFs that the deterministic table parser can't handle. Only fires when deterministic parsing returns zero rows. | ~$0.01 per PDF |
| **Drill template fallback** | Extracts hole positions from image-only or unusually laid-out drill pages. Only fires when the vector-curve extractor returns nothing. | ~$0.01 per PDF |
| **Component photo verification** | Per-row Verify button on the BOM tab. Snap a photo, get a match / mismatch / unsure verdict before soldering. | ~$0.005–0.01 per check |
| **AI fault diagnosis** | Debug-tab card. Reasons over your symptom + measured pin voltages + cached wiring image; tells you what to probe next. Schematic prompt caching makes repeat calls cheaper. | ~$0.02–0.05 per call |

Typical usage is **$1–5 per active build**. **[Set a usage
limit](https://console.anthropic.com/settings/limits)** before heavy use
— a runaway loop on pay-as-you-go can cost more.

### Why we built the no-key path first

Online pushback against AI features in DIY tools is real, and it has
good reasons behind it: cost, lock-in, opacity, environmental concerns,
and the LLM-shaped hammer treating every problem as a nail.

pedal-bench's design rule is **deterministic-first, AI as augmentation,
never as a gate**. Modern PedalPCB build docs have predictable vector
layouts — we read them with `pdfplumber` and never call an LLM. Drill
geometry is `build123d` math, not an LLM "imagining" hole positions.
Color-band decoders are pure local math, not a vision call.

AI earns its place in four spots where there's no good deterministic
alternative: vision against arbitrary photos, OCR-shaped text
extraction, and reasoning over voltage readings. Even there, every AI
feature degrades cleanly to "not available" when no key is present —
and the rest of the app keeps working.

If you want the AI extras, add a key. If you don't, you're not missing
the core of pedal-bench.

### Adding a key

Two ways to provide one:

1. **Self-host:** copy `backend/.env.example` to `backend/.env` and set
   `ANTHROPIC_API_KEY`. Loaded at backend startup.
2. **Bring-your-own-key (BYOK):** paste your key into **Settings** in
   the web UI. Stored in browser localStorage, sent as a request header
   on every API call, **never persisted server-side.**

Get a key at [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).

The header pill shows status: emerald **AI: ready** / **AI: your key**
when configured, neutral **AI: off** when not. The "off" state is a
calm signpost, not a nag.

## Other commands

```bash
npm run dev:backend    # only FastAPI
npm run dev:frontend   # only Vite
npm run test           # Python test suite
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

Backend tests cover value decoders, PedalPCB BOM extraction
(deterministic + AI parser logic), cross-project SQLite inventory
index, Tayda coordinate parsing, STL
generation (watertight meshes + bbox assertions), URL fetcher, AI drill
/ BOM / diagnosis / component-verify parsers. Drop a real PedalPCB PDF
at `backend/tests/fixtures/sherwood.pdf` to enable the end-to-end BOM
integration test (otherwise auto-skipped).

Frontend typecheck: `npm run typecheck`.

## Roadmap

- [x] v1 tkinter MVP (Phases 0–3)
- [x] v2 web UI — drill designer, BOM, bench mode, debug, decoder
- [x] One-drop / paste-a-URL ingestion + AI fallback for older PDFs
- [x] AI component verification + AI fault diagnosis
- [x] Print-ready drill template (with crosshairs) + build-log photos
- [x] BYOK + public release
- [x] SQLite-backed cross-project inventory (Inventory page)
- [x] First-class no-AI-key experience (hidden surfaces, neutral pill, capabilities panel)
- [ ] DigiKey or Octopart integration (free public APIs — Mouser's "free" tier requires sales approval, removed)
- [ ] Community-corroborated BOMs (requires hosted backend)
- [ ] Optional hosted instance for non-technical builders

## License

MIT — see [LICENSE](./LICENSE).
