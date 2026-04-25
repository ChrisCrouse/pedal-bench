import { Card, CardBody, CardHeader } from "@/components/ui/Card";

/**
 * Panel that anchors the Settings page for users without an AI key.
 *
 * The intent is to make the no-key experience feel like a first-class
 * choice, not a degraded fallback. We list every capability that works
 * fully offline so a prospective user can see at a glance that they're
 * not missing the core of pedal-bench by skipping AI.
 */
export function NoKeyCapabilities() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-baseline justify-between gap-3">
          <div className="font-semibold">What works without an API key</div>
          <div className="text-xs text-zinc-500">no signup required</div>
        </div>
      </CardHeader>
      <CardBody>
        <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
          pedal-bench is built deterministic-first. Almost everything works
          offline; AI is opt-in augmentation, not a gate.
        </p>
        <ul className="space-y-1.5 text-sm">
          <Item>
            <strong>Modern PedalPCB PDFs</strong> — drop the build doc and we
            parse the title, enclosure, BOM, and drill template directly from
            the PDF's vector layout.
          </Item>
          <Item>
            <strong>Drill designer</strong> — full SVG canvas, multi-select,
            undo/redo, mirror groups, smart-layout presets, paste-from-Tayda
            coordinates.
          </Item>
          <Item>
            <strong>Print-ready 1:1 templates</strong> + parametric STL drill
            guides for 3D printing (via build123d).
          </Item>
          <Item>
            <strong>BOM editor</strong> with color-coded chips, click-to-tag
            on the PCB layout, polarity warnings.
          </Item>
          <Item>
            <strong>Bench-tab build-along checklist</strong> — solder-order
            grouping, polarity warnings on orientation-sensitive rows, live
            progress bar.
          </Item>
          <Item>
            <strong>Debug tab</strong> — expected IC pin voltages for the seed
            chips, audio-probe procedure, common-failure triage. The pin table
            highlights out-of-range readings as you measure.
          </Item>
          <Item>
            <strong>Cross-project Inventory</strong> — SQLite over your
            project store, dedupes parts so "100K" and "100k Ohm" count as
            one across builds.
          </Item>
          <Item>
            <strong>Order from Tayda</strong> — dedupes the BOM, opens Tayda
            search results in batches, tracks shopping progress per project.
          </Item>
          <Item>
            <strong>Mouser stock + price</strong> — bring your own free Mouser
            Search API key (separate from Anthropic) for stock visibility.
          </Item>
          <Item>
            <strong>Value decoder</strong> — bidirectional resistor (text ↔
            "4K7" ↔ 4-band colors) and capacitor parsing, pure local TS.
          </Item>
        </ul>
      </CardBody>
    </Card>
  );
}

function Item({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-2 text-zinc-700 dark:text-zinc-300">
      <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
      <span>{children}</span>
    </li>
  );
}
