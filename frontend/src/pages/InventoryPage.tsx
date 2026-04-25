import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Input } from "@/components/ui/Input";
import {
  KIND_COLORS,
  KIND_LABELS,
  type ComponentKind,
} from "@/components/bom/componentColors";

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

export function InventoryPage() {
  const [kindFilter, setKindFilter] = useState<ComponentKind | null>(null);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const stats = useQuery({
    queryKey: ["inventory", "stats"],
    queryFn: api.inventory.stats,
  });

  const parts = useQuery({
    queryKey: ["inventory", "parts", kindFilter, search],
    queryFn: () =>
      api.inventory.parts(kindFilter ?? undefined, search || undefined),
  });

  const kindCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const row of stats.data?.by_kind ?? []) m.set(row.kind, row.quantity);
    return m;
  }, [stats.data]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Inventory</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Cross-project parts. Same value across projects is grouped — "100K"
          and "100k Ohm" count as one part.
        </p>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-3 gap-3">
        <StatCard
          label="Projects"
          value={stats.data?.project_count ?? "—"}
        />
        <StatCard
          label="Unique parts"
          value={stats.data?.unique_parts ?? "—"}
        />
        <StatCard
          label="Total parts"
          value={stats.data?.total_parts ?? "—"}
        />
      </div>

      {/* Filters */}
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

      {/* Parts table */}
      <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <table className="w-full text-sm">
          <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
            <tr>
              <th className="px-4 py-2 text-left">Part</th>
              <th className="px-4 py-2 text-left">Value</th>
              <th className="px-4 py-2 text-right">Qty</th>
              <th className="px-4 py-2 text-right">Projects</th>
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
            {parts.data?.parts.map((p) => {
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

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="text-xs font-medium uppercase tracking-wider text-zinc-500">
        {label}
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
        <td className="px-4 py-2 font-mono">{part.display_value}</td>
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
