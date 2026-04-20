import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";
import { type BOMItem, type Project } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

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

export function BOMTab() {
  const { slug, project } = useOutletContext<Ctx>();
  const qc = useQueryClient();

  const [bom, setBom] = useState<BOMItem[]>(project.bom);
  const [filter, setFilter] = useState("");

  const dirty = useMemo(
    () => JSON.stringify(project.bom) !== JSON.stringify(bom),
    [project.bom, bom],
  );

  const saveMutation = useMutation({
    // There's no single /bom PUT; reuse the project PATCH-friendly flow by
    // writing the full project via dedicated endpoint. For now we PATCH the
    // project (notes round-trip, BOM updates go directly through the store
    // by re-saving the project). Keep a simple approach: call a custom
    // endpoint that replaces just the BOM would be ideal; for now, re-save
    // through a minimal extension on the server side.
    mutationFn: async (next: BOMItem[]) => {
      // Optimistic: persist via a tiny wrapper that writes the project.
      const updated = await fetch(`/api/v1/projects/${slug}/bom`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bom: next }),
      });
      if (!updated.ok) throw new Error(await updated.text());
      return (await updated.json()) as BOMItem[];
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", slug] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const visible = useMemo(() => {
    if (!filter.trim()) return bom;
    const q = filter.toLowerCase();
    return bom.filter(
      (b) =>
        b.location.toLowerCase().includes(q) ||
        b.value.toLowerCase().includes(q) ||
        b.type.toLowerCase().includes(q),
    );
  }, [bom, filter]);

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

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-3 border-b border-zinc-200 bg-white px-4 py-2.5 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="text-sm text-zinc-500">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">
            {bom.length} items
          </span>
          {dirty && (
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
        <div className="ml-auto flex gap-2">
          <Button onClick={addRow}>+ Add row</Button>
          <Button
            variant="primary"
            disabled={!dirty || saveMutation.isPending}
            onClick={() => saveMutation.mutate(bom)}
          >
            {saveMutation.isPending ? "Saving…" : dirty ? "Save" : "Saved"}
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-zinc-50 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:bg-zinc-900">
            <tr>
              <Th>Loc</Th>
              <Th>Value</Th>
              <Th>Type</Th>
              <Th>Notes</Th>
              <Th className="w-10 text-center">⚠</Th>
              <Th className="w-16 text-right">Qty</Th>
              <Th className="w-10"> </Th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item, visibleIdx) => {
              // Map visible index back to the full-bom index.
              const actualIdx = bom.indexOf(item);
              return (
                <tr
                  key={`${actualIdx}-${visibleIdx}`}
                  className="border-b border-zinc-100 hover:bg-zinc-50/60 dark:border-zinc-800 dark:hover:bg-zinc-900"
                >
                  <Td>
                    <CellInput
                      value={item.location}
                      onChange={(v) => updateAt(actualIdx, { location: v })}
                      className="w-20 font-mono font-semibold"
                    />
                  </Td>
                  <Td>
                    <CellInput
                      value={item.value}
                      onChange={(v) => updateAt(actualIdx, { value: v })}
                      className="w-24 font-mono"
                    />
                  </Td>
                  <Td>
                    <CellInput
                      value={item.type}
                      onChange={(v) => updateAt(actualIdx, { type: v })}
                      className="w-full min-w-[200px]"
                    />
                  </Td>
                  <Td>
                    <CellInput
                      value={item.notes}
                      onChange={(v) => updateAt(actualIdx, { notes: v })}
                      className="w-full min-w-[140px]"
                    />
                  </Td>
                  <Td className="text-center text-amber-600">
                    {item.polarity_sensitive ? "⚠" : ""}
                  </Td>
                  <Td className="text-right">
                    <CellInput
                      value={String(item.quantity)}
                      onChange={(v) => {
                        const n = Math.max(1, Math.floor(Number(v) || 1));
                        updateAt(actualIdx, { quantity: n });
                      }}
                      className="w-12 text-right font-mono"
                    />
                  </Td>
                  <Td>
                    <button
                      onClick={() => removeRow(actualIdx)}
                      className="text-xs text-red-600 hover:text-red-500"
                      title="Remove row"
                    >
                      ×
                    </button>
                  </Td>
                </tr>
              );
            })}
            {visible.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-sm text-zinc-500">
                  {bom.length === 0
                    ? "No BOM yet — add rows manually or import from a PedalPCB PDF."
                    : "No matches for filter."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      className={`border-b border-zinc-200 px-3 py-2 text-left dark:border-zinc-800 ${className ?? ""}`}
    >
      {children}
    </th>
  );
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-3 py-1 align-middle ${className ?? ""}`}>{children}</td>;
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
