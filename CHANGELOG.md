# Changelog

## Unreleased — 2026-04-25

### Added

- **Taydakits import.** Paste a `taydakits.com/instructions/...` URL
  and pedal-bench imports the build the same way it does for PedalPCB:
  title, enclosure, BOM, schematic, wiring diagram, and drill
  template. Server-side hostname dispatch — no new endpoints, no
  frontend client changes. Snapshot HTML committed under
  `backend/tests/data/` so the parser is pinned in CI.
- **Tayda drill-template auto-import.** Both PedalPCB product pages
  and Taydakits instruction pages link to a Tayda Manufacturing
  Center drill template via a `public_key` URL. We now extract that
  link, hit Tayda's public box-design API
  (`api.taydakits.com/api/v4/box_designs/new`), and drop the holes
  straight onto the project — no OCR, no AI, no scraping. PedalPCB
  still prefers its vector extractor when it succeeds; the Tayda API
  is a fallback. Taydakits uses it as the primary path.
- **"Order drilled enclosure…"** button on the Drill tab when the
  build advertises a Tayda drill-template URL. Opens the Tayda tool
  in a new tab with this build's holes pre-loaded — Tayda offers a
  paid custom-drilling service for users without a 3D printer or
  drill press. Includes an inline caption explaining the workflow.
- **"Re-extract BOM from PDF"** button on the BOM tab. Re-runs the
  parser against the project's cached `source.pdf` and shows a
  preview Dialog with old vs new row counts before replacing.
  Backfills projects created against older buggier extractors.
- **"Fetch from Tayda"** button on the Drill tab. Re-fetches the
  drill template from the Tayda API using the project's stored
  `drill_tool_url`. Same preview pattern as Re-extract BOM.
  Backfills projects created before drill auto-import existed.
- **`next_steps`** field on the import preview, distinct from
  `warnings`. Workflow hand-offs (informational, blue) no longer
  share a section with actual extraction failures (amber). Auto-
  hides when the data was successfully imported.

### Fixed

- **Taydakits create flow dropped extracted holes.** Stale comment
  said "holes intentionally left empty" from before drill auto-
  import existed, and the line that should have copied them was
  missing. Fresh imports now land all 7 fuzz-face holes correctly.
- **`_hole_to_out` was stripping `icon` and the four mirror fields.**
  Long-standing pre-existing bug — icons were saved to disk fine
  but stripped on the way back to the frontend. All hole metadata
  now round-trips correctly.

### Internal

- New backend modules: `io/taydakits_fetch.py`,
  `io/taydakits_extract.py`, `io/tayda_drill_api.py`.
- New tests: `test_taydakits_extract.py` (16 tests, snapshot-driven),
  `test_tayda_drill_api.py` (10 tests, captured-payload-driven).
  Total backend suite: 225 passing.

## Prior

See `git log` for history before this changelog was started.
