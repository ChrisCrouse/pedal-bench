import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";
import {
  api,
  type Hole,
  type IconKind,
  type Project,
  type STLExport,
} from "@/api/client";
import { Button } from "@/components/ui/Button";
import { EnclosureCanvas } from "@/components/drill/EnclosureCanvas";
import { HoleInspector } from "@/components/drill/HoleInspector";
import { PanelArtworkDialog } from "@/components/drill/PanelArtworkDialog";
import { DrillTemplateDialog } from "@/components/drill/DrillTemplateDialog";
import { TaydaPushDialog } from "@/components/drill/TaydaPushDialog";
import { SmartLayouts } from "@/components/drill/SmartLayouts";
import { TaydaPasteDialog } from "@/components/drill/TaydaPasteDialog";
import {
  NO_MIRROR,
  canMirrorCE,
  createMirrorGroup,
  mirrorHole,
  propagateDrag,
  propagateNonPositional,
  pruneSingletonGroups,
  type MirrorMode,
  type MirrorState,
} from "@/components/drill/mirrors";
import { useUndoable } from "@/hooks/useUndoable";

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

  const presetsQuery = useQuery({
    queryKey: ["layout-presets"],
    queryFn: api.layoutPresets.all,
    staleTime: Infinity,
  });
  const snapGuides = presetsQuery.data?.snap_guides ?? null;

  const holesUndoable = useUndoable<Hole[]>(project.holes);
  const holes = holesUndoable.value;
  const setHoles = holesUndoable.set;

  const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [artworkOpen, setArtworkOpen] = useState(false);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [taydaOpen, setTaydaOpen] = useState(false);
  const [exportResults, setExportResults] = useState<STLExport[] | null>(null);
  const [snapEnabled, setSnapEnabled] = useState(true);
  const [mirrorState, setMirrorState] = useState<MirrorState>(NO_MIRROR);
  const [defaultIcon, setDefaultIcon] = useState<IconKind | null>("pot");

  // Detect dirty state by comparing current holes against the server copy.
  const serverKey = useMemo(() => JSON.stringify(project.holes), [project.holes]);
  const localKey = useMemo(() => JSON.stringify(holes), [holes]);
  const dirty = serverKey !== localKey;

  // When the project from the server changes (e.g., after save), sync
  // WITHOUT pushing history — server syncs should not be undoable.
  useEffect(() => {
    holesUndoable.reset(project.holes);
    setSelectedIndices([]);
  }, [serverKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keyboard shortcuts: arrow-nudge, Delete, Escape, Ctrl+Z/Redo.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const inField = target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);

      // Undo / redo: allowed even when nothing is selected, but still skip
      // while the user is typing in a form field (browser's own undo wins).
      if ((e.ctrlKey || e.metaKey) && !e.altKey) {
        const key = e.key.toLowerCase();
        if (key === "z" && !e.shiftKey && !inField) {
          e.preventDefault();
          holesUndoable.undo();
          setSelectedIndices([]);
          return;
        }
        if ((key === "z" && e.shiftKey) || key === "y") {
          if (inField) return;
          e.preventDefault();
          holesUndoable.redo();
          setSelectedIndices([]);
          return;
        }
      }

      if (selectedIndices.length === 0) return;
      if (inField) return;

      const step = e.shiftKey ? 0.1 : 1;
      const apply = (dx: number, dy: number) => {
        setHoles((prev) => {
          let updated = prev.map((h, i) =>
            selectedIndices.includes(i)
              ? { ...h, x_mm: round1(h.x_mm + dx), y_mm: round1(h.y_mm + dy) }
              : h,
          );
          // Propagate mirror-group updates for each moved hole.
          for (const idx of selectedIndices) {
            updated = propagateDrag(updated, idx);
          }
          return updated;
        });
        e.preventDefault();
      };

      if (e.key === "ArrowUp") apply(0, +step);
      else if (e.key === "ArrowDown") apply(0, -step);
      else if (e.key === "ArrowLeft") apply(-step, 0);
      else if (e.key === "ArrowRight") apply(+step, 0);
      else if (e.key === "Delete" || e.key === "Backspace") {
        setHoles((prev) =>
          pruneSingletonGroups(prev.filter((_, i) => !selectedIndices.includes(i))),
        );
        setSelectedIndices([]);
        e.preventDefault();
      } else if (e.key === "Escape") {
        setSelectedIndices([]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedIndices, holesUndoable, setHoles]);

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

  const reextract = useMutation({
    mutationFn: () => api.projects.extractHoles(slug),
    onSuccess: (extracted) => {
      const doReplace =
        holes.length === 0 ||
        confirm(
          `Extracted ${extracted.length} holes from the PDF. Replace the current ${holes.length}?`,
        );
      if (doReplace) {
        setHoles(extracted);
        setSelectedIndices([]);
      }
    },
    onError: (err) => {
      alert(`Extract failed: ${err instanceof Error ? err.message : String(err)}`);
    },
  });

  const handleAdd = useCallback(
    (h: Hole) => {
      setHoles((prev) => {
        const group = createMirrorGroup(h, mirrorState);
        const next = [...prev, ...group];
        return next;
      });
      // Select the seed (first of group) — index is prev.length from caller's view.
      setSelectedIndices([holes.length]);
    },
    [mirrorState, setHoles, holes.length],
  );

  const handleMoveMany = useCallback(
    (moves: { idx: number; x_mm: number; y_mm: number }[]) => {
      setHoles((prev) => {
        let updated = prev;
        for (const m of moves) {
          updated = updated.map((h, i) =>
            i === m.idx ? { ...h, x_mm: m.x_mm, y_mm: m.y_mm } : h,
          );
          updated = propagateDrag(updated, m.idx);
        }
        return updated;
      });
    },
    [setHoles],
  );

  const handleChangeDiameter = useCallback(
    (idx: number, diameter_mm: number) => {
      setHoles((prev) => {
        const updated = prev.map((h, i) => (i === idx ? { ...h, diameter_mm } : h));
        return propagateNonPositional(updated, idx, { diameter_mm });
      });
    },
    [setHoles],
  );

  // Single-selection mutations come from the inspector; apply to primary selected.
  const primaryIdx = selectedIndices.length > 0 ? selectedIndices[0] : null;
  const primaryHole = primaryIdx !== null ? holes[primaryIdx] ?? null : null;

  const mutateSelected = useCallback(
    (patch: Partial<Hole>) => {
      if (primaryIdx === null) return;
      setHoles((prev) => {
        let next = prev.map((h, i) =>
          i === primaryIdx ? { ...h, ...patch } : h,
        );
        if ("x_mm" in patch || "y_mm" in patch || "side" in patch) {
          next = propagateDrag(next, primaryIdx);
        }
        next = propagateNonPositional(next, primaryIdx, patch);
        return next;
      });
    },
    [primaryIdx, setHoles],
  );

  const deleteSelected = useCallback(() => {
    if (selectedIndices.length === 0) return;
    setHoles((prev) =>
      pruneSingletonGroups(prev.filter((_, i) => !selectedIndices.includes(i))),
    );
    setSelectedIndices([]);
  }, [selectedIndices, setHoles]);

  const importTayda = useCallback(
    (imported: Hole[], mode: "replace" | "append") => {
      setHoles((prev) => (mode === "replace" ? imported : [...prev, ...imported]));
      setSelectedIndices([]);
    },
    [setHoles],
  );

  const applyMirrorToSelected = useCallback(
    (mode: MirrorMode) => {
      if (primaryIdx === null) return;
      setHoles((prev) => {
        const seed = prev[primaryIdx];
        if (!seed) return prev;
        if (mode === "ce" && !canMirrorCE(seed.side)) return prev;
        const twin = mirrorHole(seed, mode);
        return [...prev, twin];
      });
    },
    [primaryIdx, setHoles],
  );

  const toggleMirrorMode = useCallback((mode: MirrorMode) => {
    setMirrorState((prev) => ({ ...prev, [mode]: !prev[mode] }));
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
          {selectedIndices.length > 1 && (
            <span className="ml-2 inline-flex items-center rounded bg-emerald-100 px-1.5 py-0.5 text-[11px] font-medium text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-300">
              {selectedIndices.length} selected
            </span>
          )}
          {dirty && (
            <span className="ml-2 inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-900 dark:bg-amber-900/30 dark:text-amber-300">
              unsaved
            </span>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={holesUndoable.undo}
            disabled={!holesUndoable.canUndo}
            title="Undo (Ctrl+Z)"
          >
            Undo
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={holesUndoable.redo}
            disabled={!holesUndoable.canRedo}
            title="Redo (Ctrl+Shift+Z)"
          >
            Redo
          </Button>
          <Button
            variant="ghost"
            onClick={() => reextract.mutate()}
            disabled={reextract.isPending || !project.source_pdf}
            title={
              project.source_pdf
                ? "Re-extract holes from the attached PDF"
                : "No source PDF attached to this project"
            }
          >
            {reextract.isPending ? "Extracting…" : "Extract from PDF"}
          </Button>
          <Button variant="ghost" onClick={() => setPasteOpen(true)}>
            Paste Tayda…
          </Button>
          <Button
            variant="ghost"
            disabled={holes.length === 0}
            onClick={() => setTemplateOpen(true)}
            title="Print-ready drill template with crosshairs for center-punching"
          >
            Print template…
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
            variant="ghost"
            disabled={holes.length === 0}
            onClick={() => setTaydaOpen(true)}
            title="Send this drill layout to your Tayda Kits Box Designer account"
          >
            Send to Tayda…
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

      {/* Workspace */}
      <div className="flex min-h-0 flex-1">
        <aside className="w-64 shrink-0 overflow-y-auto border-r border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950/50">
          <SmartLayouts
            enclosure={enclosure.data}
            holes={holes}
            selectedIdx={primaryIdx}
            onReplaceAll={(h) => {
              setHoles(h);
              setSelectedIndices([]);
            }}
            onAppend={(newHoles) => {
              setHoles((prev) => [...prev, ...newHoles]);
              setSelectedIndices([]);
            }}
            onMutateSelected={mutateSelected}
            mirrorState={mirrorState}
            onToggleMirror={toggleMirrorMode}
            defaultIcon={defaultIcon}
            onDefaultIconChange={setDefaultIcon}
            snapEnabled={snapEnabled}
            onToggleSnap={setSnapEnabled}
          />
        </aside>

        <div className="min-w-0 flex-1 bg-white p-4 dark:bg-zinc-900">
          <EnclosureCanvas
            enclosure={enclosure.data}
            holes={holes}
            selectedIndices={selectedIndices}
            onSelect={setSelectedIndices}
            onAdd={handleAdd}
            onMoveMany={handleMoveMany}
            onChangeDiameter={handleChangeDiameter}
            onDragBegin={holesUndoable.beginTransaction}
            onDragEnd={holesUndoable.endTransaction}
            defaultIcon={defaultIcon}
            snapEnabled={snapEnabled}
            snapGuides={snapGuides}
          />
        </div>

        <aside className="w-80 shrink-0 overflow-y-auto border-l border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950/50">
          {selectedIndices.length > 1 ? (
            <MultiSelectionPanel
              count={selectedIndices.length}
              onDelete={deleteSelected}
            />
          ) : (
            <HoleInspector
              enclosure={enclosure.data}
              hole={primaryHole}
              onChange={mutateSelected}
              onDelete={deleteSelected}
              onMirror={applyMirrorToSelected}
            />
          )}
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
      <DrillTemplateDialog
        open={templateOpen}
        onClose={() => setTemplateOpen(false)}
        enclosure={enclosure.data}
        holes={holes}
        pedalName={project.name}
      />
      <TaydaPushDialog
        open={taydaOpen}
        onClose={() => setTaydaOpen(false)}
        slug={slug}
        projectName={project.name}
        holeCount={holes.length}
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

function MultiSelectionPanel({
  count,
  onDelete,
}: {
  count: number;
  onDelete: () => void;
}) {
  return (
    <div className="space-y-4 px-4 py-4">
      <div className="text-sm font-semibold">{count} holes selected</div>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Drag any selected hole to move the whole group in lockstep. Nudge with
        arrow keys (Shift = 0.1 mm). Delete removes every selected hole.
      </p>
      <Button variant="danger" onClick={onDelete} className="w-full">
        Delete {count} holes
      </Button>
      <div className="text-xs text-zinc-500">
        Click any one hole to return to single-select for per-hole edits.
      </div>
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
