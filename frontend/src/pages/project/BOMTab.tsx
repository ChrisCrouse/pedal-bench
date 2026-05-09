import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";
import { api, type BOMItem, type Project, type ShortageRow } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { PcbLayoutViewer } from "@/components/bom/PcbLayoutViewer";
import {
  KIND_COLORS,
  KIND_LABELS,
  classifyComponent,
  type ComponentKind,
} from "@/components/bom/componentColors";
import { VerifyComponentDialog } from "@/components/bom/VerifyComponentDialog";
import { TaydaShoppingDialog } from "@/components/bom/TaydaShoppingDialog";
import { useAIAvailable } from "@/components/ui/AIRequiredNotice";
import { orientationHintFor, orientationHintSummary } from "@/lib/orientation";
import { normalizeValue } from "@/lib/partValue";

interface Ctx {
  slug: string;
  project: Project;
}

const POLARITY_KEYWORDS = [
  "diode",
  "electrolytic",
  "transistor",
  "op-amp",
  "opamp",
  "led",
  "tantalum",
];

function isPolaritySensitive(t: string): boolean {
  const lower = t.toLowerCase();
  return POLARITY_KEYWORDS.some((k) => lower.includes(k));
}

/** Soldering build order: flat parts first (resistors, diodes, small caps),
 *  then ICs/transistors, then taller through-hole (electros, pots). The Parts
 *  tab uses this as default sort so checking off rows top-to-bottom matches
 *  how you'd actually populate the PCB. */
const BUILD_ORDER: ComponentKind[] = [
  "resistor",
  "diode",
  "film-cap",
  "ic",
  "transistor",
  "electrolytic",
  "pot",
  "inductor",
  "switch",
  "other",
];

export function BOMTab() {
  const { slug, project } = useOutletContext<Ctx>();
  const qc = useQueryClient();

  // Local soldered-locations set; saved through PUT /progress. We track
  // inventory side-effects (consumed/restored/warnings) so the side panel
  // can flash deficit hints.
  const [soldered, setSoldered] = useState<Set<string>>(
    new Set(project.progress.soldered_locations),
  );
  // Re-sync local soldered state when the project payload changes (e.g. after
  // server invalidation triggered by a save).
  useEffect(() => {
    setSoldered(new Set(project.progress.soldered_locations));
  }, [project.progress.soldered_locations]);
  const [solderWarnings, setSolderWarnings] = useState<string[]>([]);

  // Build workflow filters — useful enough to keep visible always.
  const [showPolarityOnly, setShowPolarityOnly] = useState(false);
  const [showPendingOnly, setShowPendingOnly] = useState(false);

  const [bom, setBom] = useState<BOMItem[]>(project.bom);
  const [filter, setFilter] = useState("");
  const [filterKind, setFilterKind] = useState<ComponentKind | null>(null);
  const [hoverLoc, setHoverLoc] = useState<string | null>(null);
  const [selectedLoc, setSelectedLoc] = useState<string | null>(null);
  const [tagMode, setTagMode] = useState<string | null>(null);
  const [refdesMap, setRefdesMap] = useState<Record<string, [number, number]>>(
    project.refdes_map ?? {},
  );
  const [verifyRow, setVerifyRow] = useState<BOMItem | null>(null);
  const [taydaOpen, setTaydaOpen] = useState(false);
  const [reextractError, setReextractError] = useState<string | null>(null);
  const [reextractPreview, setReextractPreview] = useState<{
    bom: BOMItem[];
    previous_count: number;
    warnings: string[];
  } | null>(null);
  const aiAvailable = useAIAvailable();

  const reextractMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/v1/projects/${slug}/reextract-bom`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await res.text());
      return (await res.json()) as {
        bom: BOMItem[];
        previous_count: number;
        warnings: string[];
      };
    },
    onSuccess: (data) => {
      setReextractError(null);
      setReextractPreview(data);
    },
    onError: (err) => {
      setReextractError(err instanceof Error ? err.message : String(err));
    },
  });

  const applyReextract = () => {
    if (reextractPreview) setBom(reextractPreview.bom);
    setReextractPreview(null);
  };
  const tableBodyRef = useRef<HTMLDivElement>(null);

  const dirty = useMemo(
    () => JSON.stringify(project.bom) !== JSON.stringify(bom),
    [project.bom, bom],
  );

  const bomDirty = dirty;
  const refdesDirty = useMemo(
    () => JSON.stringify(project.refdes_map ?? {}) !== JSON.stringify(refdesMap),
    [project.refdes_map, refdesMap],
  );

  const saveBomMutation = useMutation({
    mutationFn: async (next: BOMItem[]) => {
      const res = await fetch(`/api/v1/projects/${slug}/bom`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bom: next }),
      });
      if (!res.ok) throw new Error(await res.text());
      return (await res.json()) as BOMItem[];
    },
    // ["projects"] is a prefix match, so invalidating it refreshes the
    // project list (sidebar dots, home cards) AND this project's detail
    // AND its shortage query. BOM edits change readiness/cost everywhere.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });

  const saveRefdesMutation = useMutation({
    mutationFn: (map: Record<string, [number, number]>) =>
      api.projects.setRefdesMap(slug, map),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });

  // Cache-buster bumped after upload/clear so the <img> refetches even though
  // the URL itself is stable. Stays in sync with project.has_custom_pcb_image.
  const [pcbImageVersion, setPcbImageVersion] = useState(0);

  const uploadPcbImageMutation = useMutation({
    mutationFn: (file: File) => api.projects.attachPcbLayoutImage(slug, file),
    onSuccess: () => {
      setPcbImageVersion((v) => v + 1);
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const clearPcbImageMutation = useMutation({
    mutationFn: () => api.projects.deletePcbLayoutImage(slug),
    onSuccess: () => {
      setPcbImageVersion((v) => v + 1);
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  // Progress mutation — saves soldered_locations and applies inventory
  // consumption server-side. Same wire shape the old Bench tab used.
  const progressMutation = useMutation({
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
      // Soldering changes inventory on_hand (consumed) and every project's
      // shortage (because inventory dropped pool-wide). Invalidate both
      // tree roots so sidebar readiness, Owned counters, Shopping list,
      // and per-project availability all re-fetch.
      qc.invalidateQueries({ queryKey: ["projects"] });
      if (data.consumed.length > 0 || data.restored.length > 0) {
        qc.invalidateQueries({ queryKey: ["inventory"] });
      }
      setSolderWarnings(data.warnings);
    },
  });

  const toggleSoldered = (location: string) => {
    // Hoist the side effect out of the state updater so React StrictMode's
    // double-invoke in dev doesn't fire the mutation twice.
    const next = new Set(soldered);
    if (next.has(location)) next.delete(location);
    else next.add(location);
    setSoldered(next);
    progressMutation.mutate(next);
  };

  // Shortage view: needed minus available across owned-stock for THIS project.
  // Refetches when the BOM changes (saveBomMutation invalidates project data).
  const shortageQuery = useQuery({
    queryKey: ["projects", slug, "shortage"],
    queryFn: () => api.projects.shortage(slug),
  });

  // Index by `(kind, value_norm)` so each BOM row can show its own
  // availability badge inline.
  const shortageByKindValue = useMemo(() => {
    const m = new Map<string, ShortageRow>();
    for (const r of shortageQuery.data?.rows ?? []) {
      m.set(`${r.kind}::${r.value_norm}`, r);
    }
    return m;
  }, [shortageQuery.data]);

  const reserveAllMutation = useMutation({
    mutationFn: async () => {
      const rows = shortageQuery.data?.rows ?? [];
      // For each row, set our reservation to min(needed, available + already_ours).
      // Backend `set_reservation` with absolute qty handles the math.
      for (const r of rows) {
        const target = Math.min(r.needed, r.available + r.reserved_for_self);
        if (target === r.reserved_for_self) continue;
        await api.inventory.items.reserve(`${r.kind}::${r.value_norm}`, slug, target);
      }
    },
    onSuccess: () => {
      // Reservations change inventory state and every project's
      // available counts pool-wide. Refresh both trees.
      qc.invalidateQueries({ queryKey: ["inventory"] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const visible = useMemo(() => {
    let rows = bom;
    if (filterKind) {
      rows = rows.filter((b) => classifyComponent(b) === filterKind);
    }
    if (filter.trim()) {
      const q = filter.toLowerCase();
      rows = rows.filter(
        (b) =>
          b.location.toLowerCase().includes(q) ||
          b.value.toLowerCase().includes(q) ||
          b.type.toLowerCase().includes(q),
      );
    }
    if (showPolarityOnly) rows = rows.filter((b) => b.polarity_sensitive);
    if (showPendingOnly) rows = rows.filter((b) => !soldered.has(b.location));
    // Sort by build order: resistors → diodes → small caps → ICs → transistors
    // → electros → pots. Within a kind, refdes order (R1, R2, R3, …) is
    // preserved as a stable tiebreaker.
    const orderIndex = new Map<ComponentKind, number>(
      BUILD_ORDER.map((k, i) => [k, i]),
    );
    return [...rows].sort((a, b) => {
      const ka = classifyComponent(a);
      const kb = classifyComponent(b);
      const oa = orderIndex.get(ka) ?? 999;
      const ob = orderIndex.get(kb) ?? 999;
      if (oa !== ob) return oa - ob;
      return a.location.localeCompare(b.location, undefined, { numeric: true });
    });
  }, [bom, filter, filterKind, showPolarityOnly, showPendingOnly, soldered]);

  const updateAt = (index: number, patch: Partial<BOMItem>) => {
    setBom((prev) =>
      prev.map((b, i) => {
        if (i !== index) return b;
        const next = { ...b, ...patch };
        if (patch.type !== undefined) {
          next.polarity_sensitive = isPolaritySensitive(next.type);
        }
        return next;
      }),
    );
  };

  const addRow = () =>
    setBom((prev) => [
      ...prev,
      {
        location: "",
        value: "",
        type: "",
        notes: "",
        quantity: 1,
        polarity_sensitive: false,
        orientation_hint: null,
      },
    ]);

  const removeRow = (index: number) =>
    setBom((prev) => prev.filter((_, i) => i !== index));

  const handleTag = (refdes: string, x: number, y: number) => {
    const next = { ...refdesMap, [refdes]: [x, y] as [number, number] };
    setRefdesMap(next);
    saveRefdesMutation.mutate(next);
    setTagMode(null);
    setSelectedLoc(refdes);
  };

  const removeTag = (refdes: string) => {
    const next = { ...refdesMap };
    delete next[refdes];
    setRefdesMap(next);
    saveRefdesMutation.mutate(next);
  };

  // Counts per kind for the filter chips.
  const kindCounts = useMemo(() => {
    const counts: Record<ComponentKind, number> = {
      resistor: 0,
      "film-cap": 0,
      electrolytic: 0,
      diode: 0,
      transistor: 0,
      ic: 0,
      pot: 0,
      inductor: 0,
      switch: 0,
      other: 0,
    };
    for (const b of bom) counts[classifyComponent(b)] += 1;
    return counts;
  }, [bom]);

  const taggedCount = Object.keys(refdesMap).length;

  // Soldering progress numbers shown in the toolbar.
  const totalParts = bom.length;
  const doneCount = Math.min(soldered.size, totalParts);
  const donePct = totalParts ? Math.round((100 * doneCount) / totalParts) : 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 border-b border-zinc-200 bg-white px-4 py-2.5 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="text-sm text-zinc-500">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">
            {bom.length} items
          </span>
          {totalParts > 0 && (
            <span className="ml-2 inline-flex items-center gap-1.5 align-middle text-xs">
              · <span className="font-semibold text-zinc-900 dark:text-zinc-100 tabular-nums">{doneCount}/{totalParts}</span>
              <span className="text-zinc-500">soldered</span>
              <span className="inline-block h-2 w-24 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                <span
                  className="block h-full bg-emerald-500 transition-all"
                  style={{ width: `${donePct}%` }}
                />
              </span>
            </span>
          )}
          {taggedCount > 0 && (
            <span className="ml-2 text-xs">
              · <span className="font-medium text-emerald-700 dark:text-emerald-400">{taggedCount}</span> tagged
            </span>
          )}
          {bomDirty && (
            <span className="ml-2 inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-900 dark:bg-amber-900/30 dark:text-amber-300">
              unsaved
            </span>
          )}
        </div>
        <Input
          placeholder="filter…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex flex-wrap gap-1.5">
          {(Object.entries(kindCounts) as [ComponentKind, number][])
            .filter(([, n]) => n > 0)
            .map(([k, n]) => {
              const active = filterKind === k;
              const color = KIND_COLORS[k];
              return (
                <button
                  key={k}
                  onClick={() => setFilterKind(active ? null : k)}
                  className={[
                    "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium transition",
                    active ? "ring-2 ring-offset-1" : "hover:brightness-110",
                  ].join(" ")}
                  style={{
                    backgroundColor: color.fill + (active ? "" : "22"),
                    color: active ? color.text : color.fill,
                    borderColor: color.stroke,
                  }}
                  title={`${KIND_LABELS[k]} (${n})`}
                >
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: color.fill }}
                  />
                  {KIND_LABELS[k]} <span className="opacity-70">({n})</span>
                </button>
              );
            })}
          {filterKind && (
            <button
              onClick={() => setFilterKind(null)}
              className="text-xs text-zinc-500 underline hover:text-zinc-700 dark:hover:text-zinc-300"
            >
              clear
            </button>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-zinc-600 dark:text-zinc-400">
          <label className="flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={showPolarityOnly}
              onChange={(e) => setShowPolarityOnly(e.target.checked)}
              className="h-3.5 w-3.5"
            />
            Polarity only
          </label>
          <label className="flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={showPendingOnly}
              onChange={(e) => setShowPendingOnly(e.target.checked)}
              className="h-3.5 w-3.5"
            />
            Pending only
          </label>
        </div>
        <div className="ml-auto flex gap-2">
          {project.source_pdf && (
            <Button
              variant="ghost"
              onClick={() => reextractMutation.mutate()}
              disabled={reextractMutation.isPending}
              title="Re-run the BOM parser against the project's cached PDF"
            >
              {reextractMutation.isPending ? "Re-extracting…" : "Re-extract BOM"}
            </Button>
          )}
          <Button
            variant="ghost"
            onClick={() => reserveAllMutation.mutate()}
            disabled={
              shortageQuery.isLoading ||
              reserveAllMutation.isPending ||
              !(shortageQuery.data?.rows ?? []).some(
                (r) => r.available > 0 && r.reserved_for_self < r.needed,
              )
            }
            title="Reserve every available part this build needs against your inventory"
          >
            {reserveAllMutation.isPending ? "Reserving…" : "Reserve from Inventory"}
          </Button>
          <Button
            variant="ghost"
            onClick={() => setTaydaOpen(true)}
            disabled={bom.length === 0}
            title="Open Tayda search results for each part"
          >
            Order from Tayda…
          </Button>
          <Button onClick={addRow}>+ Add row</Button>
          <Button
            variant="primary"
            disabled={!bomDirty || saveBomMutation.isPending}
            onClick={() => saveBomMutation.mutate(bom)}
          >
            {saveBomMutation.isPending ? "Saving…" : bomDirty ? "Save" : "Saved"}
          </Button>
        </div>
      </div>
      {reextractError && (
        <div className="border-b border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
          Re-extract failed: {reextractError}
        </div>
      )}
      {solderWarnings.length > 0 && (
        <div className="border-b border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <div className="mb-1 flex items-center justify-between">
            <span className="font-medium">Inventory note</span>
            <button
              onClick={() => setSolderWarnings([])}
              className="text-xs underline opacity-70 hover:opacity-100"
            >
              dismiss
            </button>
          </div>
          <ul className="list-inside list-disc space-y-0.5 text-xs">
            {solderWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Split workspace */}
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-auto" ref={tableBodyRef}>
          <table className="min-w-full border-separate border-spacing-0 text-sm">
            <thead className="sticky top-0 z-10 bg-zinc-50 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:bg-zinc-900">
              <tr>
                <Th className="w-12 text-center">Done</Th>
                <Th className="w-8">&nbsp;</Th>
                <Th>Loc</Th>
                <Th>Value</Th>
                <Th className="hidden md:table-cell">Type</Th>
                <Th className="hidden xl:table-cell">Notes</Th>
                <Th className="hidden w-28 text-center lg:table-cell">
                  <span title="Polarity-sensitive parts — orient correctly before soldering. Hover the ⚠ for the specific reminder.">
                    Polarity
                  </span>
                </Th>
                <Th className="w-16 text-right">Qty</Th>
                <Th className="sticky right-[60px] z-20 w-24 bg-zinc-50 text-center shadow-[-4px_0_8px_-6px_rgba(0,0,0,0.25)] dark:bg-zinc-900">
                  Tag
                </Th>
                <Th className="sticky right-0 z-20 w-[60px] bg-zinc-50 dark:bg-zinc-900"> </Th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => {
                const actualIdx = bom.indexOf(item);
                const kind = classifyComponent(item);
                const color = KIND_COLORS[kind];
                const isTagged = !!refdesMap[item.location];
                const isHovered = hoverLoc === item.location;
                const isSelected = selectedLoc === item.location;
                const isDone = soldered.has(item.location);
                const hint = orientationHintFor(item);
                // Sticky cells need an opaque background that matches the row.
                const stickyBg = isSelected
                  ? "bg-emerald-50 dark:bg-emerald-950"
                  : isHovered
                    ? "bg-zinc-50 dark:bg-zinc-900"
                    : "bg-white dark:bg-zinc-950";
                return (
                  <tr
                    key={`${actualIdx}-${item.location}`}
                    onMouseEnter={() => setHoverLoc(item.location || null)}
                    onMouseLeave={() => setHoverLoc(null)}
                    className={[
                      "transition",
                      isDone
                        ? "bg-emerald-50/50 dark:bg-emerald-950/20"
                        : isSelected
                          ? "bg-emerald-50 dark:bg-emerald-900/20"
                          : isHovered
                            ? "bg-zinc-50 dark:bg-zinc-900"
                            : "",
                    ].join(" ")}
                  >
                    <Td className="text-center">
                      <button
                        onClick={() => toggleSoldered(item.location)}
                        aria-checked={isDone}
                        role="checkbox"
                        title={isDone ? "Soldered — click to unmark" : "Mark soldered"}
                        className={[
                          "inline-flex h-5 w-5 items-center justify-center rounded border-2 text-xs font-bold transition",
                          isDone
                            ? "border-emerald-600 bg-emerald-600 text-white"
                            : "border-zinc-300 bg-white hover:border-emerald-400 dark:border-zinc-600 dark:bg-zinc-900",
                        ].join(" ")}
                      >
                        {isDone ? "✓" : ""}
                      </button>
                    </Td>
                    <Td className="pl-2">
                      <span
                        className="inline-block h-2.5 w-2.5 rounded-sm"
                        style={{ backgroundColor: color.fill }}
                        title={KIND_LABELS[kind]}
                      />
                    </Td>
                    <Td>
                      <CellInput
                        value={item.location}
                        onChange={(v) => updateAt(actualIdx, { location: v })}
                        className={`w-16 font-mono font-semibold ${
                          isDone ? "text-zinc-400 line-through" : ""
                        }`}
                      />
                    </Td>
                    <Td>
                      <CellInput
                        value={item.value}
                        onChange={(v) => updateAt(actualIdx, { value: v })}
                        className={`w-44 font-mono ${isDone ? "text-zinc-400" : ""}`}
                      />
                    </Td>
                    <Td className="hidden md:table-cell">
                      <CellInput
                        value={item.type}
                        onChange={(v) => updateAt(actualIdx, { type: v })}
                        className={`w-full min-w-[140px] ${
                          isDone ? "text-zinc-400" : ""
                        }`}
                      />
                    </Td>
                    <Td className="hidden xl:table-cell">
                      <CellInput
                        value={item.notes}
                        onChange={(v) => updateAt(actualIdx, { notes: v })}
                        className="w-full"
                      />
                    </Td>
                    <Td className="hidden text-center lg:table-cell">
                      {item.polarity_sensitive && !isDone && (
                        <span
                          className="inline-flex max-w-full items-center gap-1 truncate whitespace-nowrap rounded bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900/30 dark:text-amber-300"
                          title={
                            hint ??
                            "Polarity-sensitive — check orientation before soldering"
                          }
                        >
                          {hint ? `⚠ ${orientationHintSummary(hint)}` : "⚠ check"}
                        </span>
                      )}
                    </Td>
                    <Td className="text-right">
                      <div className="flex flex-col items-end gap-0.5">
                        <CellInput
                          value={String(item.quantity)}
                          onChange={(v) => {
                            const n = Math.max(1, Math.floor(Number(v) || 1));
                            updateAt(actualIdx, { quantity: n });
                          }}
                          className="w-12 text-right font-mono"
                        />
                        <AvailabilityBadge
                          row={shortageByKindValue.get(
                            `${kind}::${normalizeValue(item.value, kind)}`,
                          )}
                          needed={item.quantity}
                        />
                      </div>
                    </Td>
                    <Td className={`sticky right-[60px] z-10 text-center shadow-[-4px_0_8px_-6px_rgba(0,0,0,0.25)] ${stickyBg}`}>
                      {isTagged ? (
                        <button
                          onClick={() => removeTag(item.location)}
                          className="text-[11px] text-emerald-700 underline hover:text-emerald-900 dark:text-emerald-400"
                          title="Remove tag from PCB"
                        >
                          tagged ×
                        </button>
                      ) : (
                        <button
                          onClick={() =>
                            setTagMode(tagMode === item.location ? null : item.location)
                          }
                          className={[
                            "rounded px-2 py-0.5 text-[11px] transition",
                            tagMode === item.location
                              ? "bg-emerald-600 text-white"
                              : "bg-zinc-200 text-zinc-700 hover:bg-emerald-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-emerald-900/40",
                          ].join(" ")}
                          disabled={!item.location.trim()}
                          title={
                            item.location.trim()
                              ? "Click, then click on the PCB image to place this component"
                              : "Set a location (refdes) first"
                          }
                        >
                          {tagMode === item.location ? "cancel" : "tag"}
                        </button>
                      )}
                    </Td>
                    <Td className={`sticky right-0 z-10 ${stickyBg}`}>
                      <div className="flex items-center justify-end gap-2">
                        {aiAvailable && (
                          <button
                            onClick={() => setVerifyRow(item)}
                            disabled={!item.location.trim() || (!item.value.trim() && !item.type.trim())}
                            className="text-[11px] text-emerald-700 underline hover:text-emerald-900 disabled:text-zinc-400 disabled:no-underline dark:text-emerald-400 dark:hover:text-emerald-200"
                            title="Verify this component with a photo (AI)"
                          >
                            verify
                          </button>
                        )}
                        <button
                          onClick={() => removeRow(actualIdx)}
                          className="text-xs text-red-600 hover:text-red-500"
                          title="Remove row"
                        >
                          ×
                        </button>
                      </div>
                    </Td>
                  </tr>
                );
              })}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-4 py-8 text-center text-sm text-zinc-500">
                    {bom.length === 0
                      ? "No BOM yet — add rows manually or import from a PedalPCB PDF."
                      : "No matches for filter."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <aside className="flex w-[45%] min-w-[400px] max-w-[900px] shrink-0 flex-col border-l border-zinc-200 dark:border-zinc-800">
          {/* PCB pane fills the aside. Per-row inventory availability is
           *  shown inline in the BOM table, so no separate panel here. */}
          <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="min-h-0 flex-1">
              <PcbLayoutViewer
                imageUrl={`${api.projects.pcbLayoutImageUrl(slug)}?v=${pcbImageVersion}`}
                bom={bom}
                refdesMap={refdesMap}
                highlightLocation={hoverLoc || selectedLoc}
                tagMode={tagMode}
                onTag={handleTag}
                onHoverLocation={setHoverLoc}
                onSelectLocation={(loc) => setSelectedLoc(loc)}
                onUploadImage={async (file) => {
                  await uploadPcbImageMutation.mutateAsync(file);
                }}
                onClearImage={
                  project.has_custom_pcb_image
                    ? async () => {
                        await clearPcbImageMutation.mutateAsync();
                      }
                    : undefined
                }
                hasCustomImage={!!project.has_custom_pcb_image}
              />
            </div>
            {refdesDirty && saveRefdesMutation.isPending && (
              <div className="border-t border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
                Saving tag…
              </div>
            )}
          </div>
        </aside>
      </div>
      {verifyRow && (
        <VerifyComponentDialog
          slug={slug}
          row={verifyRow}
          onClose={() => setVerifyRow(null)}
        />
      )}
      {taydaOpen && (
        <TaydaShoppingDialog
          bom={bom}
          projectSlug={slug}
          onClose={() => setTaydaOpen(false)}
        />
      )}
      <Dialog
        open={reextractPreview !== null}
        onClose={() => setReextractPreview(null)}
        title="Re-extract BOM from PDF"
        maxWidth="md"
      >
        {reextractPreview && (
          <div className="space-y-4">
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              Re-ran the BOM parser against this project's cached PDF.
            </p>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900">
                <div className="text-xs uppercase tracking-wider text-zinc-500">Current</div>
                <div className="text-2xl font-semibold">{reextractPreview.previous_count}</div>
                <div className="text-xs text-zinc-500">rows in editor</div>
              </div>
              <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 dark:border-emerald-800 dark:bg-emerald-950/40">
                <div className="text-xs uppercase tracking-wider text-emerald-700 dark:text-emerald-400">
                  From PDF
                </div>
                <div className="text-2xl font-semibold text-emerald-800 dark:text-emerald-300">
                  {reextractPreview.bom.length}
                </div>
                <div className="text-xs text-emerald-700/80 dark:text-emerald-400/80">
                  rows extracted
                </div>
              </div>
            </div>
            {reextractPreview.warnings.length > 0 && (
              <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200">
                <div className="mb-1 font-semibold">Warnings</div>
                <ul className="list-inside list-disc space-y-0.5">
                  {reextractPreview.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-xs text-zinc-500">
              Replacing only updates the editor. Click <strong>Save</strong> on the
              Parts tab afterwards to persist — until then your current rows are
              still on disk.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setReextractPreview(null)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={applyReextract}>
                Replace editor with {reextractPreview.bom.length} rows
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      className={`border-b border-zinc-200 px-2 py-1.5 text-left dark:border-zinc-800 ${className ?? ""}`}
    >
      {children}
    </th>
  );
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  // border-separate means <tr> borders don't render; row separator goes per-cell.
  return (
    <td className={`border-b border-zinc-100 px-2 py-0.5 align-middle dark:border-zinc-800 ${className ?? ""}`}>
      {children}
    </td>
  );
}

function AvailabilityBadge({
  row,
  needed,
}: {
  row: ShortageRow | undefined;
  needed: number;
}) {
  if (!row) return null;
  // Effective availability for this build = free stock + what's already
  // reserved for this project (we can keep using those without releasing
  // them). If that covers `needed`, we're set; otherwise show a "have/need"
  // shortfall pill.
  const effective = row.available + row.reserved_for_self;
  const ok = effective >= needed;
  const label = ok ? `✓ ${effective}` : `${effective}/${needed}`;
  const tooltip = [
    `On hand: ${row.on_hand}`,
    row.reserved_for_others > 0
      ? `Reserved by other builds: ${row.reserved_for_others}`
      : null,
    row.reserved_for_self > 0
      ? `Reserved for this build: ${row.reserved_for_self}`
      : null,
    !ok ? `Need to buy: ${row.shortfall}` : null,
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <span
      title={tooltip}
      className={[
        "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold tabular-nums",
        ok
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
          : "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-300",
      ].join(" ")}
    >
      {label}
    </span>
  );
}

function CellInput({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`rounded border border-transparent bg-transparent px-1.5 py-0.5 text-sm focus:border-emerald-400 focus:bg-white focus:outline-none dark:focus:bg-zinc-900 ${className ?? ""}`}
    />
  );
}
