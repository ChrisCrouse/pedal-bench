import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";
import { api, type BOMItem, type Project } from "@/api/client";
import { orientationHintFor } from "@/lib/orientation";
import {
  KIND_COLORS,
  KIND_LABELS,
  classifyComponent,
  type ComponentKind,
} from "@/components/bom/componentColors";
import { normalizeValue } from "@/lib/partValue";

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


export function BenchTab() {
  const { slug, project } = useOutletContext<Ctx>();
  const qc = useQueryClient();

  const [showPolarityOnly, setShowPolarityOnly] = useState(false);
  const [showPendingOnly, setShowPendingOnly] = useState(false);

  // Local copy of soldered_locations so clicks feel instant; save on change.
  const [soldered, setSoldered] = useState<Set<string>>(
    new Set(project.progress.soldered_locations),
  );

  const [lastWarnings, setLastWarnings] = useState<string[]>([]);

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
      return (await res.json()) as {
        progress: { soldered_locations: string[] };
        consumed: [string, number][];
        restored: [string, number][];
        warnings: string[];
      };
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["projects", slug] });
      // Solder/unsolder mutated inventory — refresh those views too so the
      // Owned/Shopping tabs and the BOM availability badges stay accurate.
      if (data.consumed.length > 0 || data.restored.length > 0) {
        qc.invalidateQueries({ queryKey: ["inventory"] });
        qc.invalidateQueries({ queryKey: ["projects", slug, "shortage"] });
      }
      setLastWarnings(data.warnings);
    },
  });

  // Inventory side-panel data: live per-(kind,value) counters that tick as
  // the user solders.
  const inventoryQuery = useQuery({
    queryKey: ["inventory", "items"],
    queryFn: () => api.inventory.items.list(),
  });

  /** Map an inventory key "kind::value_norm" → on_hand for quick lookup. */
  const inventoryByKey = useMemo(() => {
    const m = new Map<string, number>();
    for (const it of inventoryQuery.data ?? []) m.set(it.key, it.on_hand);
    return m;
  }, [inventoryQuery.data]);

  /** For each unique (kind, value_norm) in this project's BOM, compute
   *  needed / soldered / remaining-to-solder / on-hand. Drives the side
   *  panel and the per-row "running short" indicator. */
  const partStats = useMemo(() => {
    type Stat = {
      kind: ComponentKind;
      value_norm: string;
      display_value: string;
      needed: number;
      soldered: number;
      onHand: number;
      key: string;
    };
    const map = new Map<string, Stat>();
    for (const item of project.bom) {
      const kind = classifyComponent(item);
      if (kind === "other") continue;
      const value_norm = normalizeValue(item.value, kind);
      if (!value_norm) continue;
      const key = `${kind}::${value_norm}`;
      const qty = Math.max(1, item.quantity || 1);
      const isSoldered = soldered.has(item.location);
      const existing = map.get(key);
      if (existing) {
        existing.needed += qty;
        if (isSoldered) existing.soldered += qty;
      } else {
        map.set(key, {
          kind,
          value_norm,
          display_value: item.value,
          needed: qty,
          soldered: isSoldered ? qty : 0,
          onHand: inventoryByKey.get(key) ?? 0,
          key,
        });
      }
    }
    return [...map.values()].sort((a, b) => {
      // Most-urgent first: rows where on_hand < remaining-to-solder.
      const aShort = Math.max(0, a.needed - a.soldered - a.onHand);
      const bShort = Math.max(0, b.needed - b.soldered - b.onHand);
      if (aShort !== bShort) return bShort - aShort;
      return a.kind.localeCompare(b.kind) || a.value_norm.localeCompare(b.value_norm);
    });
  }, [project.bom, soldered, inventoryByKey]);

  /** Per-row stock context. Used to render an inline badge that quantifies
   *  how many of this part type are still available, including a deficit
   *  count when on_hand has gone negative. */
  type RowStock =
    | { state: "untracked" }              // no inventory entry → no badge
    | { state: "ample"; onHand: number }  // plenty of room
    | { state: "tight"; onHand: number }  // 1–2 left after planned solders
    | { state: "last"; onHand: number }   // soldering this is the last one
    | { state: "out"; onHand: number }    // soldering this consumes from a 0 or negative pile
    | { state: "deficit"; onHand: number; by: number };  // already negative

  const rowStock = (item: BOMItem): RowStock => {
    const kind = classifyComponent(item);
    if (kind === "other") return { state: "untracked" };
    const value_norm = normalizeValue(item.value, kind);
    if (!value_norm) return { state: "untracked" };
    const stat = partStats.find(
      (s) => s.kind === kind && s.value_norm === value_norm,
    );
    if (!stat) return { state: "untracked" };
    if (soldered.has(item.location)) return { state: "ample", onHand: stat.onHand };

    if (stat.onHand < 0) {
      return { state: "deficit", onHand: stat.onHand, by: -stat.onHand };
    }
    if (stat.onHand === 0) return { state: "out", onHand: 0 };
    if (stat.onHand === 1) return { state: "last", onHand: 1 };
    if (stat.onHand <= 2) return { state: "tight", onHand: stat.onHand };
    return { state: "ample", onHand: stat.onHand };
  };

  const toggle = (location: string) => {
    // Compute outside the updater so StrictMode's double-invoke doesn't fire
    // the mutation twice (which double-decremented inventory in dev).
    const next = new Set(soldered);
    if (next.has(location)) next.delete(location);
    else next.add(location);
    setSoldered(next);
    saveMutation.mutate(next);
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
    <div className="mx-auto flex max-w-7xl gap-6 px-6 py-6">
      <div className="min-w-0 flex-1">
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

      {lastWarnings.length > 0 && (
        <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <div className="mb-1 flex items-center justify-between">
            <span className="font-medium">Inventory note</span>
            <button
              onClick={() => setLastWarnings([])}
              className="text-xs underline opacity-70 hover:opacity-100"
            >
              dismiss
            </button>
          </div>
          <ul className="list-inside list-disc space-y-0.5 text-xs">
            {lastWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {total === 0 && (
        <div className="rounded-md border border-dashed border-zinc-300 bg-zinc-50 px-4 py-12 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900">
          No BOM yet. Add components on the BOM tab first.
        </div>
      )}

      {/* Group sections */}
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
                const hint = orientationHintFor(item);
                const stock = rowStock(item);
                return (
                  <label
                    key={item.location}
                    onClick={() => toggle(item.location)}
                    className={[
                      "flex cursor-pointer items-center gap-3 border-b px-3 py-2 transition",
                      isDone
                        ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-900/40 dark:bg-emerald-950/20"
                        : "border-zinc-100 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50",
                    ].join(" ")}
                  >
                    <span
                      role="checkbox"
                      aria-checked={isDone}
                      title={isDone ? "Soldered — click to unmark" : "Mark soldered"}
                      className={[
                        "flex h-6 w-6 shrink-0 items-center justify-center rounded border-2 text-sm font-bold transition",
                        isDone
                          ? "border-emerald-600 bg-emerald-600 text-white"
                          : "border-zinc-300 bg-white dark:border-zinc-600 dark:bg-zinc-900",
                      ].join(" ")}
                    >
                      {isDone ? "✓" : ""}
                    </span>
                    {isDone && (
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
                        soldered
                      </span>
                    )}
                    {!isDone && stock.state !== "untracked" && stock.state !== "ample" && (
                      <StockBadge stock={stock} />
                    )}
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

      {/* Side panel: live inventory counters for parts in this BOM. Hidden
       *  on narrow viewports — the main checklist is the primary surface. */}
      <aside className="hidden w-72 shrink-0 lg:block">
        <div className="sticky top-4">
          <div className="mb-2 flex items-baseline justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-700 dark:text-zinc-300">
              Inventory
            </h3>
            <span className="text-xs text-zinc-500">live</span>
          </div>
          <div className="rounded-md border border-zinc-200 bg-white text-sm dark:border-zinc-800 dark:bg-zinc-900">
            {partStats.length === 0 && (
              <div className="px-3 py-4 text-center text-xs text-zinc-500">
                No trackable parts in this BOM yet.
              </div>
            )}
            {partStats.map((s) => {
              const remaining = s.needed - s.soldered;
              const shortBy = Math.max(0, remaining - s.onHand);
              const color = KIND_COLORS[s.kind];
              // Stock styling driven by absolute on_hand AND projected end:
              // negative now → red bold, going negative if you finish → red,
              // zero or last few → amber, otherwise neutral.
              const stockClass =
                s.onHand < 0
                  ? "font-bold text-red-600 dark:text-red-400"
                  : shortBy > 0 || s.onHand === 0
                  ? "font-semibold text-red-600 dark:text-red-400"
                  : s.onHand <= 2
                  ? "text-amber-700 dark:text-amber-400"
                  : "text-zinc-500";
              const stockLabel =
                s.onHand < 0 ? `${s.onHand}` : `${s.onHand}`;
              const stockTitle =
                s.onHand < 0
                  ? `Deficit of ${-s.onHand} — order more before next build`
                  : shortBy > 0
                  ? `Need ${remaining} more, only ${s.onHand} on hand — short by ${shortBy}`
                  : `${s.onHand} in stock`;
              return (
                <div
                  key={s.key}
                  className="flex items-center gap-2 border-b border-zinc-100 px-3 py-2 last:border-0 dark:border-zinc-800"
                >
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: color.fill }}
                    title={KIND_LABELS[s.kind]}
                  />
                  <span className="w-14 truncate font-mono text-xs">
                    {s.display_value}
                  </span>
                  <div className="flex flex-1 items-center justify-end gap-1.5 font-mono text-xs tabular-nums">
                    <span
                      className={
                        s.soldered === s.needed
                          ? "text-emerald-700 dark:text-emerald-400"
                          : "text-zinc-700 dark:text-zinc-300"
                      }
                      title="Soldered / needed"
                    >
                      {s.soldered}/{s.needed}
                    </span>
                    <span className="text-zinc-300 dark:text-zinc-600">·</span>
                    <span className={stockClass} title={stockTitle}>
                      {stockLabel} stock
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          {partStats.some((s) => s.onHand < 0 || s.needed - s.soldered > s.onHand) && (
            <p className="mt-2 text-xs text-zinc-500">
              Red stock numbers mean you're short or in deficit. Negative
              values track parts you've soldered but never logged — order
              that many to balance the books.
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}

type RowStockBadge =
  | { state: "tight"; onHand: number }
  | { state: "last"; onHand: number }
  | { state: "out"; onHand: number }
  | { state: "deficit"; onHand: number; by: number };

function StockBadge({ stock }: { stock: RowStockBadge }) {
  // Color and label calibrated by severity. Tight = caution, last/out = alert,
  // deficit = "you've already overspent your inventory."
  const palette: Record<RowStockBadge["state"], string> = {
    tight: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-300",
    last: "bg-orange-100 text-orange-900 dark:bg-orange-900/40 dark:text-orange-300",
    out: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
    deficit: "bg-red-600 text-white",
  };
  const label =
    stock.state === "tight" ? `${stock.onHand} left`
    : stock.state === "last" ? "1 left"
    : stock.state === "out" ? "0 in stock"
    : `${stock.onHand} (-${stock.by})`;
  const title =
    stock.state === "deficit"
      ? `You're ${stock.by} short — soldering this digs deeper`
      : stock.state === "out"
      ? "Stock is empty — soldering this will go negative"
      : stock.state === "last"
      ? "This is your last one"
      : `Only ${stock.onHand} left in inventory`;
  return (
    <span
      title={title}
      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold tabular-nums ${palette[stock.state]}`}
    >
      {label}
    </span>
  );
}
