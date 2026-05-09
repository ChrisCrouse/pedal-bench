import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type InventoryItem, type ShortageRow } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  KIND_COLORS,
  KIND_LABELS,
  type ComponentKind,
} from "@/components/bom/componentColors";
import { normalizeValue } from "@/lib/partValue";

const ALL_KINDS: ComponentKind[] = [
  "resistor",
  "film-cap",
  "electrolytic",
  "diode",
  "transistor",
  "ic",
  "pot",
  "inductor",
  "switch",
  "other",
];

// Editable kinds in the Owned tab. Pots and switches encode their full
// description into the value string (B25K, SPDT (On/Off/On)) rather than
// having a separate subtype field — "B25K" / "A25K" are distinct rows,
// "SPDT (On/On)" / "SPDT (On/Off/On)" are distinct rows. Knobs and jacks
// still need richer subtype dimensions and stay deferred.
const STANDARD_KINDS: ComponentKind[] = [
  "resistor",
  "film-cap",
  "electrolytic",
  "diode",
  "transistor",
  "ic",
  "pot",
  "switch",
];

type Tab = "owned" | "shopping" | "usage";

type SortDir = "asc" | "desc";

interface SortState<K extends string> {
  key: K | null;
  dir: SortDir;
}

/** Click cycle: none → asc → desc → none. */
function cycleSort<K extends string>(prev: SortState<K>, key: K): SortState<K> {
  if (prev.key !== key) return { key, dir: "asc" };
  if (prev.dir === "asc") return { key, dir: "desc" };
  return { key: null, dir: "asc" };
}

function compare(a: unknown, b: unknown): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a ?? "").localeCompare(String(b ?? ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

/** Sort component values by the backend-supplied magnitude (e.g. "10k" → 10000)
 *  so 1k < 10k < 100k < 1M. Falls back to natural string compare on the display
 *  value when one or both sides don't parse to a number (IC part numbers, or a
 *  stale response that didn't include the field). */
function compareValue(
  ma: number | null | undefined,
  mb: number | null | undefined,
  da: string,
  db: string,
): number {
  // typeof check, not !== null, so `undefined` (missing field) also falls back.
  if (typeof ma === "number" && typeof mb === "number") return ma - mb;
  if (typeof ma === "number") return -1;
  if (typeof mb === "number") return 1;
  return compare(da, db);
}

function SortableTh<K extends string>({
  sortKey,
  sort,
  setSort,
  align = "left",
  className = "",
  children,
}: {
  sortKey: K;
  sort: SortState<K>;
  setSort: (s: SortState<K>) => void;
  align?: "left" | "right" | "center";
  className?: string;
  children: React.ReactNode;
}) {
  const active = sort.key === sortKey;
  const arrow = !active ? "↕" : sort.dir === "asc" ? "↑" : "↓";
  const justify =
    align === "right" ? "justify-end" : align === "center" ? "justify-center" : "justify-start";
  return (
    <th
      onClick={() => setSort(cycleSort(sort, sortKey))}
      className={`cursor-pointer select-none px-4 py-2 text-${align} hover:bg-zinc-100 dark:hover:bg-zinc-800 ${className}`}
      title="Click to sort"
    >
      <span className={`inline-flex items-center gap-1 ${justify}`}>
        {children}
        <span
          className={
            active ? "text-zinc-700 dark:text-zinc-200" : "text-zinc-300 dark:text-zinc-600"
          }
        >
          {arrow}
        </span>
      </span>
    </th>
  );
}

export function InventoryPage() {
  const [tab, setTab] = useState<Tab>("owned");

  return (
    <div className="mx-auto max-w-screen-2xl px-6 py-8">
      <div className="mb-4">
        <h1 className="text-2xl font-semibold tracking-tight">Inventory</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Track what you own, see what you still need to buy, and check which
          parts are used across your builds.
        </p>
      </div>

      <BuildabilitySummary onJumpToShopping={() => setTab("shopping")} />

      <div className="mb-6 flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
        <TabButton active={tab === "owned"} onClick={() => setTab("owned")}>
          Owned
        </TabButton>
        <TabButton active={tab === "shopping"} onClick={() => setTab("shopping")}>
          Shopping list
        </TabButton>
        <TabButton active={tab === "usage"} onClick={() => setTab("usage")}>
          Usage
        </TabButton>
      </div>

      {tab === "owned" && <OwnedTab />}
      {tab === "shopping" && <ShoppingTab />}
      {tab === "usage" && <UsageTab />}
    </div>
  );
}

function BuildabilitySummary({
  onJumpToShopping,
}: {
  onJumpToShopping: () => void;
}) {
  const q = useQuery({
    queryKey: ["inventory", "buildability"],
    queryFn: api.inventory.buildability,
  });

  // Render a stable-height shell so the page doesn't jump while loading.
  if (!q.data) {
    return <div className="mb-4 h-9" aria-hidden />;
  }

  const { buildable, total_active } = q.data;

  let body: React.ReactNode;
  if (total_active === 0) {
    body = (
      <span className="text-zinc-500">
        No active projects yet — mark a project active to see buildability.
      </span>
    );
  } else if (buildable === total_active) {
    body = (
      <span>
        <span className="font-semibold text-emerald-700 dark:text-emerald-400">
          All {total_active} active project{total_active === 1 ? "" : "s"}
        </span>{" "}
        can be built with current stock.
      </span>
    );
  } else if (buildable === 0) {
    body = (
      <span>
        <span className="font-semibold text-amber-700 dark:text-amber-400">
          None of your {total_active} active project
          {total_active === 1 ? "" : "s"}
        </span>{" "}
        can be built with current stock —{" "}
        <button
          type="button"
          onClick={onJumpToShopping}
          className="font-semibold text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-400"
        >
          see Shopping list
        </button>
        .
      </span>
    );
  } else {
    body = (
      <span>
        <span className="font-semibold text-emerald-700 dark:text-emerald-400">
          {buildable} of {total_active} active projects
        </span>{" "}
        can be built with current stock — the rest need parts from the{" "}
        <button
          type="button"
          onClick={onJumpToShopping}
          className="font-semibold text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-400"
        >
          Shopping list
        </button>
        .
      </span>
    );
  }

  return (
    <div className="mb-4 flex items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-900">
      <span aria-hidden>🛠</span>
      <div className="text-zinc-700 dark:text-zinc-200">{body}</div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "px-4 py-2 text-sm font-medium transition border-b-2",
        active
          ? "border-emerald-600 text-emerald-700 dark:text-emerald-400"
          : "border-transparent text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

// ---- Owned tab --------------------------------------------------------------

type OwnedSortKey = "kind" | "value" | "on_hand" | "reserved" | "available";

function OwnedTab() {
  const qc = useQueryClient();
  const [kindFilter, setKindFilter] = useState<ComponentKind | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState<OwnedSortKey>>({
    key: null,
    dir: "asc",
  });

  const items = useQuery({
    queryKey: ["inventory", "items", kindFilter, search],
    queryFn: () =>
      api.inventory.items.list(kindFilter ?? undefined, search || undefined),
  });

  const stats = useMemo(() => {
    const data = items.data ?? [];
    let onHand = 0;
    let reserved = 0;
    for (const it of data) {
      onHand += it.on_hand;
      reserved += it.reserved_total;
    }
    return { unique: data.length, onHand, reserved };
  }, [items.data]);

  const filtered = !!kindFilter || search.trim().length > 0;

  const sortedItems = useMemo(() => {
    const data = items.data ?? [];
    if (!sort.key) return data;
    const key = sort.key;
    const sign = sort.dir === "asc" ? 1 : -1;
    return [...data].sort((a, b) => {
      const cmp =
        key === "value"
          ? compareValue(
              a.value_magnitude,
              b.value_magnitude,
              a.display_value || a.value_norm,
              b.display_value || b.value_norm,
            )
          : compare(
              key === "kind" ? a.kind
                : key === "on_hand" ? a.on_hand
                : key === "reserved" ? a.reserved_total
                : a.available,
              key === "kind" ? b.kind
                : key === "on_hand" ? b.on_hand
                : key === "reserved" ? b.reserved_total
                : b.available,
            );
      return sign * cmp;
    });
  }, [items.data, sort]);

  // Inventory mutations need to invalidate both ["inventory"] (Owned table,
  // global Shopping shortage, OwnedTab counters) AND ["projects"] (per-
  // project shortage queries that drive Parts-tab availability badges,
  // Overview readiness card, sidebar heat dots, Home cards). Without the
  // ["projects"] invalidation those views lag until the next background
  // refetch — visible as "delay between inventory edit and BOM update".
  const invalidateInventoryEverywhere = () => {
    qc.invalidateQueries({ queryKey: ["inventory"] });
    qc.invalidateQueries({ queryKey: ["projects"] });
  };

  const upsert = useMutation({
    mutationFn: api.inventory.items.upsert,
    onSuccess: invalidateInventoryEverywhere,
  });
  const patch = useMutation({
    mutationFn: ({ key, on_hand }: { key: string; on_hand: number }) =>
      api.inventory.items.patch(key, { on_hand }),
    onSuccess: invalidateInventoryEverywhere,
  });
  const del = useMutation({
    mutationFn: api.inventory.items.delete,
    onSuccess: invalidateInventoryEverywhere,
  });

  const [draftKind, setDraftKind] = useState<ComponentKind>("resistor");
  const [draftValue, setDraftValue] = useState("");
  const [draftOnHand, setDraftOnHand] = useState("");

  // If a row already exists for this (kind, value), the form is restocking —
  // sum with existing on_hand instead of replacing. Avoids the trap where
  // typing "10 more" silently overwrites the count.
  const draftMatch = useMemo<InventoryItem | null>(() => {
    const trimmed = draftValue.trim();
    if (!trimmed) return null;
    const norm = normalizeValue(trimmed, draftKind);
    if (!norm) return null;
    return (
      items.data?.find((i) => i.kind === draftKind && i.value_norm === norm) ??
      null
    );
  }, [items.data, draftKind, draftValue]);

  const onAdd = () => {
    if (!draftValue.trim()) return;
    const entered = Math.max(0, parseInt(draftOnHand || "0", 10) || 0);
    const total = (draftMatch?.on_hand ?? 0) + entered;
    upsert.mutate({
      kind: draftKind,
      value: draftValue.trim(),
      on_hand: total,
    });
    setDraftValue("");
    setDraftOnHand("");
  };

  return (
    <div>
      <div className="mb-6 grid grid-cols-3 gap-3">
        <StatCard
          label="Unique parts"
          value={stats.unique}
          hint={filtered ? "filtered" : undefined}
        />
        <StatCard
          label="Total on hand"
          value={stats.onHand}
          hint={filtered ? "filtered" : undefined}
        />
        <StatCard
          label="Reserved for builds"
          value={stats.reserved}
          hint={filtered ? "filtered" : undefined}
          tooltip="Stock already set aside for a project. Available = On hand − Reserved."
        />
      </div>
      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search value or notes…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex flex-wrap gap-1.5">
          {STANDARD_KINDS.map((k) => {
            const active = kindFilter === k;
            const color = KIND_COLORS[k];
            return (
              <button
                key={k}
                onClick={() => setKindFilter(active ? null : k)}
                className={[
                  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition",
                  active ? "ring-2 ring-offset-1" : "hover:brightness-110",
                ].join(" ")}
                style={{
                  backgroundColor: color.fill + (active ? "" : "22"),
                  color: active ? color.text : color.fill,
                }}
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: color.fill }}
                />
                {KIND_LABELS[k]}
              </button>
            );
          })}
          {kindFilter && (
            <button
              onClick={() => setKindFilter(null)}
              className="text-xs text-zinc-500 underline hover:text-zinc-700 dark:hover:text-zinc-300"
            >
              clear
            </button>
          )}
        </div>
      </div>

      {/* Add row */}
      <div className="mb-4 rounded-lg border border-dashed border-zinc-300 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-900/40">
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="block text-xs text-zinc-500">Kind</label>
            <select
              value={draftKind}
              onChange={(e) => setDraftKind(e.target.value as ComponentKind)}
              className="rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-950"
            >
              {STANDARD_KINDS.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABELS[k]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-zinc-500">Value</label>
            <Input
              placeholder="10k, 100n, TL072…"
              value={draftValue}
              onChange={(e) => setDraftValue(e.target.value)}
              className="w-40"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500">
              {draftMatch ? "Add to stock" : "On hand"}
            </label>
            <Input
              type="number"
              min="0"
              value={draftOnHand}
              onChange={(e) => setDraftOnHand(e.target.value)}
              className="w-24"
            />
          </div>
          <Button onClick={onAdd} disabled={!draftValue.trim() || upsert.isPending}>
            {draftMatch ? "Add to stock" : "Add"}
          </Button>
          {draftMatch && (
            <div className="text-xs text-zinc-500">
              Already have <span className="font-mono">{draftMatch.on_hand}</span>
              {parseInt(draftOnHand, 10) > 0 && (
                <>
                  {" "}
                  → new total{" "}
                  <span className="font-mono font-semibold">
                    {draftMatch.on_hand + (parseInt(draftOnHand, 10) || 0)}
                  </span>
                </>
              )}
              . Use the row's count to set an exact value instead.
            </div>
          )}
        </div>
      </div>

      {/* Items table */}
      <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <table className="w-full text-sm">
          <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
            <tr>
              <SortableTh sortKey="kind" sort={sort} setSort={setSort}>
                Kind
              </SortableTh>
              <SortableTh sortKey="value" sort={sort} setSort={setSort}>
                Value
              </SortableTh>
              <SortableTh sortKey="on_hand" sort={sort} setSort={setSort} align="right">
                On hand
              </SortableTh>
              <SortableTh sortKey="reserved" sort={sort} setSort={setSort} align="right">
                Reserved
              </SortableTh>
              <SortableTh sortKey="available" sort={sort} setSort={setSort} align="right">
                Available
              </SortableTh>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {items.isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-zinc-500">
                  loading…
                </td>
              </tr>
            )}
            {!items.isLoading && sortedItems.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-zinc-500">
                  No parts owned yet. Add some above.
                </td>
              </tr>
            )}
            {sortedItems.map((it) => (
              <OwnedRow
                key={it.key}
                item={it}
                onAdjust={(on_hand) => patch.mutate({ key: it.key, on_hand })}
                onDelete={() => del.mutate(it.key)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OwnedRow({
  item,
  onAdjust,
  onDelete,
}: {
  item: InventoryItem;
  onAdjust: (on_hand: number) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(item.on_hand));
  const color = KIND_COLORS[item.kind as ComponentKind] ?? KIND_COLORS.other;

  const commit = () => {
    const n = Math.max(0, parseInt(draft, 10) || 0);
    if (n !== item.on_hand) onAdjust(n);
    setEditing(false);
  };

  const reservationEntries = Object.entries(item.reservations);

  return (
    <tr className="border-b border-zinc-100 dark:border-zinc-800">
      <td className="px-4 py-2">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: color.fill }}
          />
          <span className="text-xs text-zinc-500">
            {KIND_LABELS[item.kind as ComponentKind] ?? item.kind}
          </span>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-2 font-mono">
        {item.display_value || item.value_norm}
      </td>
      <td className="px-4 py-2 text-right font-mono tabular-nums">
        {editing ? (
          <input
            type="number"
            value={draft}
            min="0"
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") {
                setDraft(String(item.on_hand));
                setEditing(false);
              }
            }}
            autoFocus
            className="w-20 rounded border border-zinc-300 bg-white px-1 py-0.5 text-right dark:border-zinc-700 dark:bg-zinc-950"
          />
        ) : (
          <button
            onClick={() => {
              setDraft(String(item.on_hand));
              setEditing(true);
            }}
            className="hover:underline"
          >
            {item.on_hand}
          </button>
        )}
      </td>
      <td className="px-4 py-2 text-right text-zinc-500 tabular-nums">
        {item.reserved_total > 0 ? (
          <span title={reservationEntries.map(([s, n]) => `${s}: ${n}`).join("\n")}>
            {item.reserved_total}
          </span>
        ) : (
          <span className="text-zinc-300">—</span>
        )}
      </td>
      <td className="px-4 py-2 text-right font-mono tabular-nums">
        <span
          className={
            item.available > 0
              ? "text-emerald-700 dark:text-emerald-400"
              : "text-zinc-400"
          }
        >
          {item.available}
        </span>
      </td>
      <td className="px-2 py-2 text-right">
        <button
          onClick={onDelete}
          className="text-xs text-zinc-400 hover:text-red-600"
          title="Delete"
        >
          ×
        </button>
      </td>
    </tr>
  );
}

// ---- Shopping tab -----------------------------------------------------------

type ShoppingSortKey = "kind" | "value" | "needed" | "on_hand" | "shortfall";

function ShoppingTab() {
  const shortage = useQuery({
    queryKey: ["inventory", "shortage"],
    queryFn: api.inventory.shortage,
  });
  // Default to shortfall desc — biggest gaps first, which is the natural
  // "what should I buy next" view.
  const [sort, setSort] = useState<SortState<ShoppingSortKey>>({
    key: "shortfall",
    dir: "desc",
  });

  const rows = useMemo(() => {
    const filtered = (shortage.data?.rows ?? []).filter((r) => r.shortfall > 0);
    if (!sort.key) return filtered;
    const key = sort.key;
    const sign = sort.dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const cmp =
        key === "value"
          ? compareValue(a.value_magnitude, b.value_magnitude, a.display_value, b.display_value)
          : compare(
              key === "kind" ? a.kind
                : key === "needed" ? a.needed
                : key === "on_hand" ? a.on_hand
                : a.shortfall,
              key === "kind" ? b.kind
                : key === "needed" ? b.needed
                : key === "on_hand" ? b.on_hand
                : b.shortfall,
            );
      return sign * cmp;
    });
  }, [shortage.data, sort]);
  const cost = shortage.data?.estimated_total_cost_usd ?? null;
  // True when at least one shortfall row got its price from the oracle
  // rather than a user-set inventory price. Drives "~" prefixes + tooltip.
  const costHasEstimates = useMemo(
    () =>
      (shortage.data?.rows ?? []).some(
        (r) => r.shortfall > 0 && r.unit_cost_estimated,
      ),
    [shortage.data],
  );

  // Per-project cost rollup. Distribution is proportional to each project's
  // quantity contribution (from needed_by_qty) — so a build that needs 10 of
  // a $1 resistor and is competing with a build that needs 1 gets ~91% of
  // the cost attributed, not 50%. Cost is allocated only across the
  // shortfall (not the whole need) since that's what you're actually buying.
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: api.projects.list,
  });
  const costByProject = useMemo(() => {
    const totals = new Map<string, number>();
    const estimatedFlag = new Map<string, boolean>();
    for (const r of shortage.data?.rows ?? []) {
      if (r.shortfall === 0 || r.unit_cost_usd == null) continue;
      const totalContribution = Object.values(r.needed_by_qty).reduce(
        (s, q) => s + q,
        0,
      );
      if (totalContribution <= 0) continue;
      const rowCost = r.unit_cost_usd * r.shortfall;
      for (const [slug, qty] of Object.entries(r.needed_by_qty)) {
        const share = rowCost * (qty / totalContribution);
        totals.set(slug, (totals.get(slug) ?? 0) + share);
        if (r.unit_cost_estimated) estimatedFlag.set(slug, true);
      }
    }
    const nameOf = new Map<string, string>();
    for (const p of projectsQuery.data ?? []) nameOf.set(p.slug, p.name);
    return [...totals.entries()]
      .map(([slug, cost]) => ({
        slug,
        name: nameOf.get(slug) ?? slug,
        cost,
        estimated: estimatedFlag.get(slug) ?? false,
      }))
      .sort((a, b) => b.cost - a.cost);
  }, [shortage.data, projectsQuery.data]);

  const stats = useMemo(() => {
    const allRows = shortage.data?.rows ?? [];
    const buyRows = allRows.filter((r) => r.shortfall > 0);
    const totalQty = buyRows.reduce((sum, r) => sum + r.shortfall, 0);
    return { partsToBuy: buyRows.length, totalQty };
  }, [shortage.data]);

  return (
    <div>
      <div className="mb-4 grid grid-cols-3 gap-3">
        <StatCard label="Parts to buy" value={stats.partsToBuy} />
        <StatCard label="Total qty to buy" value={stats.totalQty} />
        <StatCard
          label="Est. total cost"
          value={
            cost !== null
              ? `${costHasEstimates ? "~" : ""}$${cost.toFixed(2)}`
              : "—"
          }
          tooltip={
            cost === null
              ? undefined
              : costHasEstimates
                ? "Includes prices estimated from typical Tayda Electronics retail. Set unit costs on inventory items to lock in your actual paid prices."
                : "Based on unit costs you've set on inventory items."
          }
        />
      </div>
      <p className="mb-4 text-sm text-zinc-500">
        Parts needed across all <span className="font-medium">active</span>{" "}
        projects, minus what you already own. Mark a project inactive to keep
        its BOM out of this list.
      </p>

      {costByProject.length > 0 && (
        <div className="mb-4 rounded-lg border border-zinc-200 bg-white px-4 py-3 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Cost by project
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-sm">
            {costByProject.map((p) => (
              <Link
                key={p.slug}
                to={`/projects/${p.slug}/parts`}
                title={
                  p.estimated
                    ? "Includes oracle-estimated prices for parts you haven't logged unit costs for"
                    : undefined
                }
                className="inline-flex items-center gap-1.5 text-zinc-700 hover:text-emerald-700 dark:text-zinc-300 dark:hover:text-emerald-400"
              >
                <span>{p.name}</span>
                <span className="font-mono tabular-nums text-zinc-500">
                  {p.estimated ? "~" : ""}${p.cost.toFixed(2)}
                </span>
              </Link>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-zinc-500">
            Each row's cost is split across the projects that need it,
            weighted by how many of that part each project's BOM calls for.
            A "~" means the cost includes prices estimated from typical
            Tayda retail — set unit costs on inventory items to lock in
            your actual paid prices.
          </p>
        </div>
      )}

      <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <table className="w-full text-sm">
          <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
            <tr>
              <SortableTh sortKey="kind" sort={sort} setSort={setSort}>
                Kind
              </SortableTh>
              <SortableTh sortKey="value" sort={sort} setSort={setSort}>
                Value
              </SortableTh>
              <SortableTh sortKey="needed" sort={sort} setSort={setSort} align="right">
                Need
              </SortableTh>
              <SortableTh sortKey="on_hand" sort={sort} setSort={setSort} align="right">
                Have
              </SortableTh>
              <SortableTh sortKey="shortfall" sort={sort} setSort={setSort} align="right">
                Buy
              </SortableTh>
              <th className="px-4 py-2 text-left">For</th>
            </tr>
          </thead>
          <tbody>
            {shortage.isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-zinc-500">
                  loading…
                </td>
              </tr>
            )}
            {!shortage.isLoading && rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-zinc-500">
                  Nothing to buy — every active project's BOM is covered.
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <ShortageRowView key={`${r.kind}::${r.value_norm}`} row={r} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ShortageRowView({ row }: { row: ShortageRow }) {
  const color = KIND_COLORS[row.kind as ComponentKind] ?? KIND_COLORS.other;
  return (
    <tr className="border-b border-zinc-100 dark:border-zinc-800">
      <td className="px-4 py-2">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: color.fill }}
          />
          <span className="text-xs text-zinc-500">
            {KIND_LABELS[row.kind as ComponentKind] ?? row.kind}
          </span>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-2 font-mono">{row.display_value}</td>
      <td className="px-4 py-2 text-right font-mono tabular-nums">{row.needed}</td>
      <td className="px-4 py-2 text-right font-mono tabular-nums text-zinc-500">
        {row.on_hand}
      </td>
      <td className="px-4 py-2 text-right font-mono tabular-nums font-semibold text-amber-700 dark:text-amber-400">
        {row.shortfall}
      </td>
      <td className="px-4 py-2">
        <div className="flex flex-wrap gap-1">
          {row.needed_by.map((slug) => (
            <Link
              key={slug}
              to={`/projects/${slug}/parts`}
              className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            >
              {slug}
            </Link>
          ))}
        </div>
      </td>
    </tr>
  );
}

// ---- Usage tab (existing read-only cross-project view) ---------------------

type UsageSortKey = "kind" | "value" | "qty" | "projects";

function UsageTab() {
  const [kindFilter, setKindFilter] = useState<ComponentKind | null>(null);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sort, setSort] = useState<SortState<UsageSortKey>>({
    key: "qty",
    dir: "desc",
  });

  const stats = useQuery({
    queryKey: ["inventory", "stats"],
    queryFn: api.inventory.stats,
  });

  const parts = useQuery({
    queryKey: ["inventory", "parts", kindFilter, search],
    queryFn: () =>
      api.inventory.parts(kindFilter ?? undefined, search || undefined),
  });

  const sortedParts = useMemo(() => {
    const data = parts.data?.parts ?? [];
    if (!sort.key) return data;
    const key = sort.key;
    const sign = sort.dir === "asc" ? 1 : -1;
    return [...data].sort((a, b) => {
      const cmp =
        key === "value"
          ? compareValue(a.value_magnitude, b.value_magnitude, a.display_value, b.display_value)
          : compare(
              key === "kind" ? a.kind
                : key === "qty" ? a.total_qty
                : a.project_count,
              key === "kind" ? b.kind
                : key === "qty" ? b.total_qty
                : b.project_count,
            );
      return sign * cmp;
    });
  }, [parts.data, sort]);

  const kindCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const row of stats.data?.by_kind ?? []) m.set(row.kind, row.quantity);
    return m;
  }, [stats.data]);

  return (
    <div>
      <div className="mb-6 grid grid-cols-3 gap-3">
        <StatCard
          label="Active projects"
          value={stats.data?.project_count ?? "—"}
          tooltip="Active projects only — inactive ones are excluded from the BOM index."
        />
        <StatCard
          label="Distinct parts in BOMs"
          value={stats.data?.unique_parts ?? "—"}
          tooltip="Distinct (kind, value) pairs referenced by any active project's BOM. Includes parts you don't own yet."
        />
        <StatCard label="Total parts" value={stats.data?.total_parts ?? "—"} />
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search value or type…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex flex-wrap gap-1.5">
          {ALL_KINDS.filter((k) => (kindCounts.get(k) ?? 0) > 0).map((k) => {
            const active = kindFilter === k;
            const color = KIND_COLORS[k];
            const n = kindCounts.get(k) ?? 0;
            return (
              <button
                key={k}
                onClick={() => setKindFilter(active ? null : k)}
                className={[
                  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition",
                  active ? "ring-2 ring-offset-1" : "hover:brightness-110",
                ].join(" ")}
                style={{
                  backgroundColor: color.fill + (active ? "" : "22"),
                  color: active ? color.text : color.fill,
                }}
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: color.fill }}
                />
                {KIND_LABELS[k]} <span className="opacity-70">({n})</span>
              </button>
            );
          })}
          {kindFilter && (
            <button
              onClick={() => setKindFilter(null)}
              className="text-xs text-zinc-500 underline hover:text-zinc-700 dark:hover:text-zinc-300"
            >
              clear
            </button>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <table className="w-full text-sm">
          <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
            <tr>
              <SortableTh sortKey="kind" sort={sort} setSort={setSort}>
                Part
              </SortableTh>
              <SortableTh sortKey="value" sort={sort} setSort={setSort}>
                Value
              </SortableTh>
              <SortableTh sortKey="qty" sort={sort} setSort={setSort} align="right">
                Qty
              </SortableTh>
              <SortableTh sortKey="projects" sort={sort} setSort={setSort} align="right">
                Projects
              </SortableTh>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {parts.isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-sm text-zinc-500">
                  loading…
                </td>
              </tr>
            )}
            {parts.data?.parts.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-sm text-zinc-500">
                  No parts match.
                </td>
              </tr>
            )}
            {sortedParts.map((p) => {
              const key = `${p.kind}::${p.value_norm}`;
              const isOpen = expanded === key;
              const color = KIND_COLORS[p.kind as ComponentKind] ?? KIND_COLORS.other;
              return (
                <PartRow
                  key={key}
                  part={p}
                  open={isOpen}
                  onToggle={() => setExpanded(isOpen ? null : key)}
                  color={color}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  tooltip,
  hint,
}: {
  label: string;
  value: number | string;
  tooltip?: string;
  /** Tiny right-aligned chip next to the label — e.g. "(filtered)" when the
   *  table's filters narrow the count below the global total. */
  hint?: string;
}) {
  return (
    <div
      title={tooltip}
      className={`rounded-lg border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-950 ${
        tooltip ? "cursor-help" : ""
      }`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          {label}
        </div>
        {hint && (
          <div className="text-[10px] font-medium uppercase tracking-wider text-amber-600 dark:text-amber-400">
            {hint}
          </div>
        )}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function PartRow({
  part,
  open,
  onToggle,
  color,
}: {
  part: import("@/api/client").InventoryPart;
  open: boolean;
  onToggle: () => void;
  color: { fill: string; stroke: string; text: string };
}) {
  const projects = useQuery({
    queryKey: ["inventory", "projectsUsing", part.kind, part.value_norm],
    queryFn: () => api.inventory.projectsUsing(part.kind, part.value_norm),
    enabled: open,
  });

  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer border-b border-zinc-100 transition hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900/60"
      >
        <td className="px-4 py-2">
          <div className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: color.fill }}
            />
            <span className="text-xs text-zinc-500">
              {KIND_LABELS[part.kind as ComponentKind] ?? part.kind}
            </span>
          </div>
        </td>
        <td className="whitespace-nowrap px-4 py-2 font-mono">{part.display_value}</td>
        <td className="px-4 py-2 text-right font-mono tabular-nums">
          {part.total_qty}
        </td>
        <td className="px-4 py-2 text-right text-zinc-500 tabular-nums">
          {part.project_count}
        </td>
        <td className="px-2 py-2 text-right text-zinc-400">{open ? "▾" : "▸"}</td>
      </tr>
      {open && (
        <tr className="bg-zinc-50/60 dark:bg-zinc-900/40">
          <td colSpan={5} className="px-6 py-3">
            {projects.isLoading && (
              <div className="text-xs text-zinc-500">loading projects…</div>
            )}
            {projects.data && (
              <ul className="space-y-1.5">
                {projects.data.projects.map((proj) => (
                  <li
                    key={proj.slug}
                    className="flex items-center justify-between text-sm"
                  >
                    <Link
                      to={`/projects/${proj.slug}/bom`}
                      className="text-emerald-700 hover:underline dark:text-emerald-400"
                    >
                      {proj.name}
                    </Link>
                    <span className="text-xs text-zinc-500 tabular-nums">
                      ×{proj.quantity}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
