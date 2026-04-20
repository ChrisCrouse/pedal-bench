import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";
import { type BOMItem, type Project } from "@/api/client";

interface Ctx {
  slug: string;
  project: Project;
}

const GROUP_ORDER: { key: string; label: string }[] = [
  { key: "resistors", label: "Resistors" },
  { key: "diodes", label: "Diodes" },
  { key: "small_caps", label: "Small caps (ceramic / film)" },
  { key: "ics", label: "ICs / op-amps" },
  { key: "transistors", label: "Transistors" },
  { key: "large_caps", label: "Electrolytic caps" },
  { key: "pots", label: "Pots" },
  { key: "other", label: "Other" },
];

function groupFor(item: BOMItem): string {
  const t = item.type.toLowerCase();
  if (t.includes("resistor")) return "resistors";
  if (t.includes("diode")) return "diodes";
  if (t.includes("transistor")) return "transistors";
  if (t.includes("op-amp") || t.includes("opamp") || t.includes("ic ") || t.startsWith("dual op"))
    return "ics";
  if (t.includes("electrolytic") || t.includes("tantalum")) return "large_caps";
  if (t.includes("cap") || t.includes("ceramic") || t.includes("film")) return "small_caps";
  if (t.includes("pot")) return "pots";
  return "other";
}

const DEFAULT_ORIENTATION_HINTS: { match: string[]; hint: string }[] = [
  { match: ["signal diode", "diode"], hint: "Band = cathode — match the stripe on the PCB silkscreen" },
  { match: ["schottky"], hint: "Band = cathode — match the stripe on the PCB silkscreen" },
  { match: ["electrolytic", "tantalum"], hint: "+ leg (longer) → + marked pad on PCB" },
  { match: ["op-amp", "opamp", "dip"], hint: "Notch / dot = pin 1" },
  { match: ["transistor"], hint: "Flat side matches the flat on the PCB silkscreen" },
  { match: ["led"], hint: "+ leg (longer) = anode → + pad on PCB" },
];

function defaultHint(bomType: string): string | null {
  const t = bomType.toLowerCase();
  for (const { match, hint } of DEFAULT_ORIENTATION_HINTS) {
    if (match.some((k) => t.includes(k))) return hint;
  }
  return null;
}

export function BenchTab() {
  const { slug, project } = useOutletContext<Ctx>();
  const qc = useQueryClient();

  const [showPolarityOnly, setShowPolarityOnly] = useState(false);
  const [showPendingOnly, setShowPendingOnly] = useState(false);

  // Local copy of soldered_locations so clicks feel instant; save on change.
  const [soldered, setSoldered] = useState<Set<string>>(
    new Set(project.progress.soldered_locations),
  );

  const saveMutation = useMutation({
    mutationFn: async (next: Set<string>) => {
      const res = await fetch(`/api/v1/projects/${slug}/progress`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          soldered_locations: [...next].sort(),
          current_phase: project.progress.current_phase,
          phase_notes: project.progress.phase_notes,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects", slug] }),
  });

  const toggle = (location: string) => {
    setSoldered((prev) => {
      const next = new Set(prev);
      if (next.has(location)) next.delete(location);
      else next.add(location);
      saveMutation.mutate(next);
      return next;
    });
  };

  const grouped = useMemo(() => {
    const map: Record<string, BOMItem[]> = {};
    for (const item of project.bom) {
      const g = groupFor(item);
      (map[g] ??= []).push(item);
    }
    return map;
  }, [project.bom]);

  const filter = (items: BOMItem[]) =>
    items.filter((i) => {
      if (showPolarityOnly && !i.polarity_sensitive) return false;
      if (showPendingOnly && soldered.has(i.location)) return false;
      return true;
    });

  const total = project.bom.length;
  const done = Math.min(soldered.size, total);
  const pct = total ? Math.round((100 * done) / total) : 0;

  return (
    <div className="mx-auto max-w-4xl px-6 py-6">
      <div className="mb-5 flex flex-wrap items-center gap-4">
        <div className="text-sm text-zinc-600 dark:text-zinc-400">
          <span className="font-semibold text-zinc-900 dark:text-zinc-100">
            {done} / {total}
          </span>{" "}
          soldered · <span className="font-mono">{pct}%</span>
        </div>
        <div className="h-2 w-40 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
          <div
            className="h-full bg-emerald-500 transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="ml-auto flex gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={showPolarityOnly}
              onChange={(e) => setShowPolarityOnly(e.target.checked)}
            />
            Polarity-sensitive only
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={showPendingOnly}
              onChange={(e) => setShowPendingOnly(e.target.checked)}
            />
            Pending only
          </label>
        </div>
      </div>

      {total === 0 && (
        <div className="rounded-md border border-dashed border-zinc-300 bg-zinc-50 px-4 py-12 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900">
          No BOM yet. Add components on the BOM tab first.
        </div>
      )}

      {GROUP_ORDER.map(({ key, label }) => {
        const items = grouped[key];
        if (!items || items.length === 0) return null;
        const visible = filter(items);
        if (visible.length === 0) return null;
        const groupDone = items.filter((i) => soldered.has(i.location)).length;
        return (
          <section key={key} className="mb-6">
            <header className="mb-2 flex items-baseline gap-2">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-700 dark:text-zinc-300">
                {label}
              </h3>
              <span className="text-xs text-zinc-500">
                {groupDone}/{items.length}
              </span>
            </header>
            <div className="rounded-md border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
              {visible.map((item) => {
                const isDone = soldered.has(item.location);
                const hint = item.orientation_hint ?? defaultHint(item.type);
                return (
                  <label
                    key={item.location}
                    className="flex cursor-pointer items-center gap-3 border-b border-zinc-100 px-3 py-1.5 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
                  >
                    <input
                      type="checkbox"
                      checked={isDone}
                      onChange={() => toggle(item.location)}
                      className="h-4 w-4 rounded border-zinc-300 text-emerald-600"
                    />
                    <span
                      className={`w-12 font-mono font-semibold ${
                        isDone ? "text-zinc-400 line-through" : "text-zinc-900 dark:text-zinc-100"
                      }`}
                    >
                      {item.location}
                    </span>
                    <span
                      className={`w-16 font-mono text-sm ${
                        isDone ? "text-zinc-400" : "text-zinc-700 dark:text-zinc-300"
                      }`}
                    >
                      {item.value}
                    </span>
                    <span
                      className={`flex-1 truncate text-sm ${
                        isDone ? "text-zinc-400" : "text-zinc-600 dark:text-zinc-400"
                      }`}
                    >
                      {item.type}
                    </span>
                    {item.polarity_sensitive && hint && (
                      <span className="shrink-0 rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900/30 dark:text-amber-300">
                        ⚠ {hint}
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
