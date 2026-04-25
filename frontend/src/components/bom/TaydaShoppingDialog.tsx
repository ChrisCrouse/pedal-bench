import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import {
  KIND_COLORS,
  KIND_LABELS,
  classifyComponent,
  type ComponentKind,
} from "@/components/bom/componentColors";
import type { BOMItem } from "@/api/client";

interface Props {
  bom: BOMItem[];
  projectSlug: string;
  onClose: () => void;
}

interface Group {
  key: string;
  query: string;
  kind: ComponentKind;
  totalQty: number;
  rows: BOMItem[];
}

// Hardware that Tayda doesn't sell as searchable parts. Skipped by default
// but user can include if they want.
const DEFAULT_SKIP_KINDS: ComponentKind[] = ["switch"];

const BATCH_SIZE = 5;
const STAGGER_MS = 200;

function buildQuery(item: BOMItem): string {
  const kind = classifyComponent(item);
  const v = item.value.trim();
  const t = item.type.trim();
  if (kind === "pot") return v ? `${v} potentiometer` : t || "potentiometer";
  if (kind === "resistor") return v ? `${v} resistor 1/4W` : t || "resistor";
  if (kind === "electrolytic")
    return v ? `${v} electrolytic capacitor` : t || "electrolytic capacitor";
  if (kind === "film-cap") return v ? `${v} capacitor` : t || "capacitor";
  if (kind === "ic" || kind === "transistor" || kind === "diode") return v || t;
  return v || t || item.location;
}

function groupBom(bom: BOMItem[]): Group[] {
  const groups = new Map<string, Group>();
  for (const item of bom) {
    const kind = classifyComponent(item);
    const query = buildQuery(item);
    if (!query.trim()) continue;
    const key = `${kind}::${query.toLowerCase()}`;
    const existing = groups.get(key);
    if (existing) {
      existing.totalQty += item.quantity;
      existing.rows.push(item);
    } else {
      groups.set(key, { key, query, kind, totalQty: item.quantity, rows: [item] });
    }
  }
  return Array.from(groups.values()).sort((a, b) => {
    if (a.kind !== b.kind) return a.kind.localeCompare(b.kind);
    return a.query.localeCompare(b.query);
  });
}

function searchUrl(query: string): string {
  return `https://www.taydaelectronics.com/catalogsearch/result/?q=${encodeURIComponent(query)}`;
}

function loadSet(storageKey: string): Set<string> {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return new Set();
  }
}

function saveSet(storageKey: string, set: Set<string>): void {
  try {
    localStorage.setItem(storageKey, JSON.stringify(Array.from(set)));
  } catch {
    /* localStorage full / disabled — degrade silently */
  }
}

const INTRO_KEY = "pedalBench.taydaIntroDismissed";

export function TaydaShoppingDialog({ bom, projectSlug, onClose }: Props) {
  const groups = useMemo(() => groupBom(bom), [bom]);

  const orderedKey = `pedalBench.taydaOrdered.${projectSlug}`;
  const skippedKey = `pedalBench.taydaSkipped.${projectSlug}`;

  const [ordered, setOrdered] = useState<Set<string>>(() => loadSet(orderedKey));
  const [skipped, setSkipped] = useState<Set<string>>(() => {
    const stored = loadSet(skippedKey);
    if (stored.size > 0) return stored;
    // First open: pre-skip default kinds.
    const initial = new Set<string>();
    for (const g of groups) {
      if (DEFAULT_SKIP_KINDS.includes(g.kind)) initial.add(g.key);
    }
    return initial;
  });
  const [showIntro, setShowIntro] = useState(
    () => !localStorage.getItem(INTRO_KEY),
  );
  const [openingProgress, setOpeningProgress] = useState<{
    current: number;
    total: number;
  } | null>(null);

  useEffect(() => saveSet(orderedKey, ordered), [orderedKey, ordered]);
  useEffect(() => saveSet(skippedKey, skipped), [skippedKey, skipped]);

  const remaining = groups.filter(
    (g) => !skipped.has(g.key) && !ordered.has(g.key),
  );
  const orderedCount = groups.filter((g) => ordered.has(g.key)).length;

  const toggleOrdered = (key: string) => {
    setOrdered((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleSkip = (key: string) => {
    setSkipped((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const openOne = (g: Group) => {
    window.open(searchUrl(g.query), "_blank", "noopener,noreferrer");
  };

  const openBatch = () => {
    const batch = remaining.slice(0, BATCH_SIZE);
    if (batch.length === 0) return;
    setOpeningProgress({ current: 0, total: batch.length });
    batch.forEach((g, i) => {
      setTimeout(() => {
        openOne(g);
        setOpeningProgress((prev) =>
          prev ? { ...prev, current: i + 1 } : null,
        );
        if (i === batch.length - 1) {
          setTimeout(() => setOpeningProgress(null), 600);
        }
      }, i * STAGGER_MS);
    });
  };

  const dismissIntro = () => {
    localStorage.setItem(INTRO_KEY, "1");
    setShowIntro(false);
  };

  const resetAll = () => {
    setOrdered(new Set());
    setSkipped(new Set());
  };

  // Group rendering by component kind for visual scannability.
  const byKind = useMemo(() => {
    const buckets = new Map<ComponentKind, Group[]>();
    for (const g of groups) {
      const arr = buckets.get(g.kind) ?? [];
      arr.push(g);
      buckets.set(g.kind, arr);
    }
    return Array.from(buckets.entries());
  }, [groups]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl dark:bg-zinc-950"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
          <div className="min-w-0">
            <div className="font-semibold">Order BOM from Tayda</div>
            <div className="text-xs text-zinc-500">
              {orderedCount} of {groups.length - skipped.size} ordered
              {skipped.size > 0 && ` · ${skipped.size} skipped`}
            </div>
          </div>
          <button
            onClick={onClose}
            className="ml-3 text-2xl leading-none text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* First-run intro */}
        {showIntro && (
          <div className="border-b border-zinc-200 bg-emerald-50 px-5 py-3 text-sm dark:border-zinc-800 dark:bg-emerald-950/30">
            <div className="font-medium text-emerald-900 dark:text-emerald-200">
              How this works
            </div>
            <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-xs text-emerald-900/90 dark:text-emerald-200/80">
              <li>
                We open a Tayda search tab for each unique part in your BOM
                (deduped — 4× 100K resistors = one search).
              </li>
              <li>
                You pick the right match in Tayda — voltage, package, and
                tolerance vary, so a human eye is needed.
              </li>
              <li>
                Click <strong>Mark ordered</strong> here to track progress. Your
                progress is saved per project.
              </li>
            </ol>
            <p className="mt-2 text-xs text-emerald-900/70 dark:text-emerald-200/60">
              Tayda has no public cart API, so this is the most we can automate
              without risking your account.
            </p>
            <button
              onClick={dismissIntro}
              className="mt-2 text-xs font-medium text-emerald-800 underline hover:text-emerald-900 dark:text-emerald-300 dark:hover:text-emerald-100"
            >
              Got it
            </button>
          </div>
        )}

        {/* Progress while opening */}
        {openingProgress && (
          <div className="border-b border-zinc-200 bg-zinc-50 px-5 py-2 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
            Opening tab {openingProgress.current} of {openingProgress.total}…
            (allow popups if your browser blocks them)
          </div>
        )}

        {/* List */}
        <div className="flex-1 overflow-auto px-2 py-2">
          {groups.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-zinc-500">
              No orderable parts in this BOM.
            </div>
          ) : (
            byKind.map(([kind, gs]) => {
              const color = KIND_COLORS[kind];
              return (
                <div key={kind} className="mb-3">
                  <div className="sticky top-0 z-10 flex items-center gap-2 bg-white/95 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500 backdrop-blur dark:bg-zinc-950/95">
                    <span
                      className="inline-block h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: color.fill }}
                    />
                    {KIND_LABELS[kind]}
                    <span className="font-normal text-zinc-400">
                      ({gs.length})
                    </span>
                  </div>
                  {gs.map((g) => {
                    const isSkipped = skipped.has(g.key);
                    const isOrdered = ordered.has(g.key);
                    return (
                      <div
                        key={g.key}
                        className={[
                          "group flex items-center gap-3 rounded px-3 py-2 transition",
                          isOrdered
                            ? "bg-emerald-50/60 dark:bg-emerald-950/20"
                            : isSkipped
                              ? "opacity-40"
                              : "hover:bg-zinc-50 dark:hover:bg-zinc-900/60",
                        ].join(" ")}
                      >
                        <input
                          type="checkbox"
                          checked={isOrdered}
                          onChange={() => toggleOrdered(g.key)}
                          disabled={isSkipped}
                          className="h-4 w-4 shrink-0 cursor-pointer accent-emerald-600"
                          title="Mark as ordered"
                        />
                        <div className="min-w-0 flex-1">
                          <div
                            className={[
                              "font-mono text-sm",
                              isOrdered
                                ? "text-zinc-500 line-through"
                                : "text-zinc-800 dark:text-zinc-200",
                            ].join(" ")}
                          >
                            {g.query}
                          </div>
                          {g.rows.some((r) => r.location) && (
                            <div className="truncate text-[11px] text-zinc-400">
                              {g.rows
                                .map((r) => r.location)
                                .filter(Boolean)
                                .join(", ")}
                            </div>
                          )}
                        </div>
                        <div className="shrink-0 text-right font-mono text-sm tabular-nums text-zinc-600 dark:text-zinc-400">
                          ×{g.totalQty}
                        </div>
                        <div className="flex shrink-0 items-center gap-3 opacity-0 transition group-hover:opacity-100">
                          <button
                            onClick={() => {
                              navigator.clipboard.writeText(g.query).catch(() => {});
                            }}
                            className="text-[11px] text-zinc-500 underline hover:text-zinc-700 dark:hover:text-zinc-300"
                            title="Copy search query"
                          >
                            copy
                          </button>
                          <button
                            onClick={() => toggleSkip(g.key)}
                            className="text-[11px] text-zinc-500 underline hover:text-zinc-700 dark:hover:text-zinc-300"
                          >
                            {isSkipped ? "include" : "skip"}
                          </button>
                        </div>
                        <button
                          onClick={() => openOne(g)}
                          disabled={isSkipped}
                          className={[
                            "shrink-0 rounded px-2 py-1 text-xs font-medium transition",
                            isOrdered
                              ? "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300"
                              : "bg-emerald-600 text-white hover:bg-emerald-500 disabled:bg-zinc-300 dark:disabled:bg-zinc-800",
                          ].join(" ")}
                        >
                          Search Tayda ↗
                        </button>
                      </div>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-200 px-5 py-3 dark:border-zinc-800">
          <div className="flex items-center gap-3 text-xs text-zinc-500">
            <span>
              <span className="font-medium text-emerald-700 dark:text-emerald-400">
                {orderedCount}
              </span>{" "}
              ordered · <span className="font-medium">{remaining.length}</span>{" "}
              left
            </span>
            {(ordered.size > 0 || skipped.size > 0) && (
              <button
                onClick={resetAll}
                className="text-zinc-400 underline hover:text-zinc-600 dark:hover:text-zinc-300"
              >
                reset
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
            <Button
              variant="primary"
              onClick={openBatch}
              disabled={remaining.length === 0 || openingProgress !== null}
            >
              {remaining.length === 0
                ? "All ordered"
                : `Open next ${Math.min(BATCH_SIZE, remaining.length)} ↗`}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
