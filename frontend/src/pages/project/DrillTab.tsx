import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";
import { api, type Hole, type Project, type STLExport } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { EnclosureCanvas } from "@/components/drill/EnclosureCanvas";
import { HoleInspector } from "@/components/drill/HoleInspector";
import { PanelArtworkDialog } from "@/components/drill/PanelArtworkDialog";
import { SmartLayouts } from "@/components/drill/SmartLayouts";
import { TaydaPasteDialog } from "@/components/drill/TaydaPasteDialog";

interface Ctx {
  slug: string;
  project: Project;
}

export function DrillTab() {
  const { slug, project } = useOutletContext<Ctx>();
  const qc = useQueryClient();
  const enclosure = useQuery({
    queryKey: ["enclosures", project.enclosure],
    queryFn: () => api.enclosures.get(project.enclosure),
    enabled: !!project.enclosure,
  });

  const [holes, setHoles] = useState<Hole[]>(project.holes);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [artworkOpen, setArtworkOpen] = useState(false);
  const [exportResults, setExportResults] = useState<STLExport[] | null>(null);

  // Detect dirty state by comparing current holes against the server copy.
  const serverKey = useMemo(() => JSON.stringify(project.holes), [project.holes]);
  const localKey = useMemo(() => JSON.stringify(holes), [holes]);
  const dirty = serverKey !== localKey;

  // When the project from the server changes (e.g., after save), sync local state.
  useEffect(() => {
    setHoles(project.holes);
  }, [serverKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keyboard shortcuts: arrow keys nudge, Delete removes, Escape deselects.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (selectedIdx === null) return;
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;

      const step = e.shiftKey ? 0.1 : 1;
      const apply = (dx: number, dy: number) => {
        setHoles((prev) =>
          prev.map((h, i) =>
            i === selectedIdx
              ? { ...h, x_mm: round1(h.x_mm + dx), y_mm: round1(h.y_mm + dy) }
              : h,
          ),
        );
        e.preventDefault();
      };
      if (e.key === "ArrowUp") apply(0, +step);
      else if (e.key === "ArrowDown") apply(0, -step);
      else if (e.key === "ArrowLeft") apply(-step, 0);
      else if (e.key === "ArrowRight") apply(+step, 0);
      else if (e.key === "Delete" || e.key === "Backspace") {
        setHoles((prev) => prev.filter((_, i) => i !== selectedIdx));
        setSelectedIdx(null);
        e.preventDefault();
      } else if (e.key === "Escape") {
        setSelectedIdx(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedIdx]);

  const saveMutation = useMutation({
    mutationFn: (next: Hole[]) => api.projects.replaceHoles(slug, next),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", slug] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const exportMutation = useMutation({
    mutationFn: () => api.projects.exportSTLs(slug),
    onSuccess: (results) => setExportResults(results),
  });

  const handleAdd = useCallback((h: Hole) => {
    setHoles((prev) => {
      const next = [...prev, h];
      setSelectedIdx(next.length - 1);
      return next;
    });
  }, []);

  const handleMove = useCallback((idx: number, x_mm: number, y_mm: number) => {
    setHoles((prev) => prev.map((h, i) => (i === idx ? { ...h, x_mm, y_mm } : h)));
  }, []);

  const handleChangeDiameter = useCallback((idx: number, diameter_mm: number) => {
    setHoles((prev) => prev.map((h, i) => (i === idx ? { ...h, diameter_mm } : h)));
  }, []);

  const mutateSelected = useCallback((patch: Partial<Hole>) => {
    if (selectedIdx === null) return;
    setHoles((prev) =>
      prev.map((h, i) => (i === selectedIdx ? { ...h, ...patch } : h)),
    );
  }, [selectedIdx]);

  const deleteSelected = useCallback(() => {
    if (selectedIdx === null) return;
    setHoles((prev) => prev.filter((_, i) => i !== selectedIdx));
    setSelectedIdx(null);
  }, [selectedIdx]);

  const importTayda = useCallback((imported: Hole[], mode: "replace" | "append") => {
    setHoles((prev) => (mode === "replace" ? imported : [...prev, ...imported]));
    setSelectedIdx(null);
  }, []);

  if (!project.enclosure) {
    return (
      <div className="mx-auto max-w-xl px-6 py-16 text-center text-sm text-zinc-600 dark:text-zinc-400">
        Set an enclosure on the Overview tab first — the drill designer needs face
        dimensions to work.
      </div>
    );
  }
  if (enclosure.isLoading) {
    return <div className="px-6 py-16 text-center text-sm text-zinc-500">loading enclosure…</div>;
  }
  if (enclosure.isError || !enclosure.data) {
    return (
      <div className="px-6 py-16 text-center text-sm text-red-600 dark:text-red-400">
        Could not load enclosure{" "}
        <code>{project.enclosure}</code>: {(enclosure.error as Error)?.message}
      </div>
    );
  }

  const selectedHole = selectedIdx === null ? null : holes[selectedIdx] ?? null;
  const byside: Record<string, number> = {};
  for (const h of holes) byside[h.side] = (byside[h.side] ?? 0) + 1;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-200 bg-white px-4 py-2.5 text-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mr-2 text-zinc-500">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">
            {holes.length} holes
          </span>
          {Object.keys(byside).length > 0 && (
            <span className="ml-1 text-xs text-zinc-500">
              ·{" "}
              {Object.entries(byside)
                .sort()
                .map(([s, n]) => `${s}:${n}`)
                .join("  ")}
            </span>
          )}
          {dirty && (
            <span className="ml-2 inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-900 dark:bg-amber-900/30 dark:text-amber-300">
              unsaved
            </span>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" onClick={() => setPasteOpen(true)}>
            Paste Tayda…
          </Button>
          <Button
            variant="ghost"
            disabled={holes.length === 0}
            onClick={() => setArtworkOpen(true)}
            title="Download print-ready panel artwork (SVG / PNG)"
          >
            Panel artwork…
          </Button>
          <Button
            variant="secondary"
            disabled={!dirty || saveMutation.isPending}
            onClick={() => saveMutation.mutate(holes)}
          >
            {saveMutation.isPending ? "Saving…" : dirty ? "Save" : "Saved"}
          </Button>
          <Button
            variant="primary"
            disabled={holes.length === 0 || dirty || exportMutation.isPending}
            title={
              dirty
                ? "Save first — export uses the server-side hole list"
                : "Generate STL drill guides per face"
            }
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? "Exporting…" : "Export STLs"}
          </Button>
        </div>
      </div>

      {/* Workspace: left sidebar / canvas / right inspector */}
      <div className="flex min-h-0 flex-1">
        <aside className="w-64 shrink-0 overflow-y-auto border-r border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950/50">
          <SmartLayouts
            enclosure={enclosure.data}
            holes={holes}
            selectedIdx={selectedIdx}
            onReplaceAll={setHoles}
            onAppend={(newHoles) => setHoles((prev) => [...prev, ...newHoles])}
            onMutateSelected={mutateSelected}
          />
        </aside>

        <div className="min-w-0 flex-1 bg-white p-4 dark:bg-zinc-900">
          <EnclosureCanvas
            enclosure={enclosure.data}
            holes={holes}
            selectedIdx={selectedIdx}
            onSelect={setSelectedIdx}
            onAdd={handleAdd}
            onMove={handleMove}
            onChangeDiameter={handleChangeDiameter}
          />
        </div>

        <aside className="w-80 shrink-0 overflow-y-auto border-l border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950/50">
          <HoleInspector
            enclosure={enclosure.data}
            hole={selectedHole}
            onChange={mutateSelected}
            onDelete={deleteSelected}
          />
        </aside>
      </div>

      <TaydaPasteDialog
        open={pasteOpen}
        onClose={() => setPasteOpen(false)}
        onImport={importTayda}
      />
      <PanelArtworkDialog
        open={artworkOpen}
        onClose={() => setArtworkOpen(false)}
        enclosure={enclosure.data}
        holes={holes}
        pedalName={project.name}
      />
      {exportResults && (
        <ExportResultsOverlay
          slug={slug}
          results={exportResults}
          onClose={() => setExportResults(null)}
        />
      )}
    </div>
  );
}

function ExportResultsOverlay({
  slug,
  results,
  onClose,
}: {
  slug: string;
  results: STLExport[];
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-w-md rounded-lg border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-lg font-semibold">STL export complete</div>
        <div className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          Wrote {results.length} drill-guide STL{results.length === 1 ? "" : "s"} to{" "}
          <code>projects/{slug}/drill/</code>.
        </div>
        <ul className="mt-4 space-y-1 text-sm">
          {results.map((r) => (
            <li key={r.side} className="flex items-center justify-between gap-2">
              <span>
                Side <span className="font-mono">{r.side}</span> —{" "}
                {(r.size_bytes / 1024).toFixed(1)} KB
              </span>
              <a
                className="text-emerald-700 underline hover:text-emerald-800 dark:text-emerald-400"
                href={`/api/v1/projects/${slug}/stl/${r.side}.stl`}
                download
              >
                Download
              </a>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex justify-end">
          <Button variant="primary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}

function round1(v: number) {
  return Math.round(v * 10) / 10;
}
