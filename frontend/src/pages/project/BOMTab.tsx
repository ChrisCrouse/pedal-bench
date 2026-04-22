import { useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";
import { api, type BOMItem, type Project } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PcbLayoutViewer } from "@/components/bom/PcbLayoutViewer";
import {
  KIND_COLORS,
  KIND_LABELS,
  classifyComponent,
  type ComponentKind,
} from "@/components/bom/componentColors";
import { VerifyComponentDialog } from "@/components/bom/VerifyComponentDialog";

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
  const [filterKind, setFilterKind] = useState<ComponentKind | null>(null);
  const [hoverLoc, setHoverLoc] = useState<string | null>(null);
  const [selectedLoc, setSelectedLoc] = useState<string | null>(null);
  const [tagMode, setTagMode] = useState<string | null>(null);
  const [refdesMap, setRefdesMap] = useState<Record<string, [number, number]>>(
    project.refdes_map ?? {},
  );
  const [verifyRow, setVerifyRow] = useState<BOMItem | null>(null);
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", slug] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const saveRefdesMutation = useMutation({
    mutationFn: (map: Record<string, [number, number]>) =>
      api.projects.setRefdesMap(slug, map),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects", slug] }),
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
    return rows;
  }, [bom, filter, filterKind]);

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

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 border-b border-zinc-200 bg-white px-4 py-2.5 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="text-sm text-zinc-500">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">
            {bom.length} items
          </span>
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
                    className="h-2 w-2 rounded-full"
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
        <div className="ml-auto flex gap-2">
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

      {/* Split workspace */}
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-auto" ref={tableBodyRef}>
          <table className="min-w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-zinc-50 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:bg-zinc-900">
              <tr>
                <Th className="w-8">&nbsp;</Th>
                <Th>Loc</Th>
                <Th>Value</Th>
                <Th>Type</Th>
                <Th>Notes</Th>
                <Th className="w-10 text-center">⚠</Th>
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
                      "border-b border-zinc-100 transition dark:border-zinc-800",
                      isSelected
                        ? "bg-emerald-50 dark:bg-emerald-900/20"
                        : isHovered
                          ? "bg-zinc-50 dark:bg-zinc-900"
                          : "",
                    ].join(" ")}
                  >
                    <Td className="pl-3">
                      <span
                        className="inline-block h-3 w-3 rounded-sm"
                        style={{ backgroundColor: color.fill }}
                        title={KIND_LABELS[kind]}
                      />
                    </Td>
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
                        <button
                          onClick={() => setVerifyRow(item)}
                          disabled={!item.location.trim() || (!item.value.trim() && !item.type.trim())}
                          className="text-[11px] text-emerald-700 underline hover:text-emerald-900 disabled:text-zinc-400 disabled:no-underline dark:text-emerald-400 dark:hover:text-emerald-200"
                          title="Verify this component with a photo"
                        >
                          verify
                        </button>
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
                  <td colSpan={9} className="px-4 py-8 text-center text-sm text-zinc-500">
                    {bom.length === 0
                      ? "No BOM yet — add rows manually or import from a PedalPCB PDF."
                      : "No matches for filter."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <aside className="w-[45%] min-w-[400px] shrink-0 border-l border-zinc-200 dark:border-zinc-800">
          <PcbLayoutViewer
            imageUrl={api.projects.pcbLayoutImageUrl(slug)}
            bom={bom}
            refdesMap={refdesMap}
            highlightLocation={hoverLoc || selectedLoc}
            tagMode={tagMode}
            onTag={handleTag}
            onHoverLocation={setHoverLoc}
            onSelectLocation={(loc) => setSelectedLoc(loc)}
          />
          {refdesDirty && saveRefdesMutation.isPending && (
            <div className="border-t border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
              Saving tag…
            </div>
          )}
        </aside>
      </div>
      {verifyRow && (
        <VerifyComponentDialog
          slug={slug}
          row={verifyRow}
          onClose={() => setVerifyRow(null)}
        />
      )}
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
