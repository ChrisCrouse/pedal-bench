import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type Hole, type PDFExtractOut } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useAIAvailable } from "@/components/ui/AIRequiredNotice";

export type PdfReviewSource =
  | { kind: "file"; file: File }
  | { kind: "url"; url: string };

interface Props {
  source: PdfReviewSource;
  preview: PDFExtractOut;
  onClose: () => void;
}

function sourceFallbackName(source: PdfReviewSource): string {
  if (source.kind === "file") return source.file.name.replace(/\.pdf$/i, "");
  try {
    const path = new URL(source.url).pathname.replace(/\/+$/, "");
    const slug = path.split("/").filter(Boolean).pop() ?? "";
    return slug.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  } catch {
    return "";
  }
}

export function PdfReviewDialog({ source, preview, onClose }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const aiAvailable = useAIAvailable();

  const enclosures = useQuery({
    queryKey: ["enclosures"],
    queryFn: api.enclosures.list,
  });

  const [name, setName] = useState(
    preview.suggested_name ?? sourceFallbackName(source),
  );
  const [enclosure, setEnclosure] = useState(
    preview.enclosure_in_catalog && preview.suggested_enclosure
      ? preview.suggested_enclosure
      : "125B",
  );

  // Re-sync defaults when the preview changes (e.g., re-upload).
  useEffect(() => {
    if (preview.suggested_name) setName(preview.suggested_name);
    if (preview.enclosure_in_catalog && preview.suggested_enclosure) {
      setEnclosure(preview.suggested_enclosure);
    }
  }, [preview]);

  const create = useMutation({
    mutationFn: () =>
      source.kind === "file"
        ? api.projects.createFromPdf(source.file, name, enclosure)
        : api.projects.createFromUrl(source.url, name, enclosure),
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      onClose();
      navigate(`/projects/${project.slug}`);
    },
  });

  const bomByGroup: Record<string, number> = {};
  for (const b of preview.bom) {
    const t = b.type.toLowerCase();
    let k = "other";
    // Order matters: more specific matches first. "ceramic capacitor"
    // contains "ic" as a substring, so cap detection must precede the
    // op-amp / IC check.
    if (t.includes("resistor")) k = "resistors";
    else if (t.includes("diode") || t.includes("led")) k = "diodes";
    else if (t.includes("electrolytic") || t.includes("tantalum")) k = "electro caps";
    else if (t.includes("cap") || t.includes("ceramic") || t.includes("film")) k = "caps";
    else if (t.includes("op-amp") || t.includes("opamp") ||
             t.includes("integrated circuit") || /\bic\b/.test(t) ||
             t.includes("voltage regulator") || t.includes("reverb module")) k = "ICs";
    else if (t.includes("transistor")) k = "transistors";
    else if (t.includes("trim")) k = "trim pots";
    else if (t.includes("pot")) k = "pots";
    else if (t.includes("switch") || t.includes("toggle") || t.includes("relay")) k = "switches";
    else if (t.includes("inductor")) k = "inductors";
    bomByGroup[k] = (bomByGroup[k] ?? 0) + 1;
  }

  return (
    <Dialog open={true} onClose={onClose} title="Review extracted build" maxWidth="xl">
      <div className="space-y-5">
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Project name
            </span>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
            {preview.suggested_name && preview.suggested_name !== name && (
              <span className="mt-1 block text-xs text-zinc-500">
                Detected:{" "}
                <button
                  type="button"
                  className="underline hover:text-emerald-700"
                  onClick={() => setName(preview.suggested_name!)}
                >
                  {preview.suggested_name}
                </button>
              </span>
            )}
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Enclosure
            </span>
            <Select value={enclosure} onChange={(e) => setEnclosure(e.target.value)}>
              {enclosures.data?.map((e) => (
                <option key={e.key} value={e.key}>
                  {e.key} — {e.name}
                </option>
              ))}
            </Select>
            {preview.suggested_enclosure && (
              <span className="mt-1 block text-xs text-zinc-500">
                {preview.enclosure_in_catalog
                  ? `Detected: ${preview.suggested_enclosure}`
                  : `Detected ${preview.suggested_enclosure} (not in catalog — pick manually)`}
              </span>
            )}
          </label>
        </section>

        <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
              BOM preview
            </div>
            {preview.bom.length === 0 ? (
              <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                No BOM rows detected.
                {aiAvailable === false && (
                  <div className="mt-1 text-xs">
                    This PDF uses an older "Parts List" layout that needs AI
                    to read.{" "}
                    <Link to="/settings" className="font-medium underline">
                      Set up an Anthropic key →
                    </Link>{" "}
                    or create the project anyway and add the BOM by hand.
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm dark:border-zinc-800 dark:bg-zinc-900">
                <div className="mb-2 font-semibold">{preview.bom.length} rows:</div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(bomByGroup)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, n]) => (
                      <span
                        key={k}
                        className="inline-flex items-center gap-1 rounded bg-white px-2 py-0.5 text-xs dark:bg-zinc-800"
                      >
                        <span className="font-medium">{n}</span>
                        <span className="text-zinc-500">{k}</span>
                      </span>
                    ))}
                </div>
              </div>
            )}
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Drill holes
            </div>
            {preview.holes.length === 0 ? (
              <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                No drill-template holes detected. You can place them on the Drill tab.
              </div>
            ) : (
              <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm dark:border-zinc-800 dark:bg-zinc-900">
                <div className="mb-2 font-semibold">
                  {preview.holes.length} holes extracted:
                </div>
                <div className="flex flex-wrap gap-2">
                  {summarizeHoles(preview.holes).map(([k, n]) => (
                    <span
                      key={k}
                      className="inline-flex items-center gap-1 rounded bg-white px-2 py-0.5 text-xs dark:bg-zinc-800"
                    >
                      <span className="font-medium">{n}</span>
                      <span className="text-zinc-500">{k}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        {preview.next_steps && preview.next_steps.length > 0 && (
          <section className="rounded-md border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-200">
            <div className="mb-1 font-semibold text-sky-800 dark:text-sky-300">
              What to do next
            </div>
            <ul className="list-inside list-disc space-y-1">
              {preview.next_steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </section>
        )}

        {preview.warnings.length > 0 && (
          <section className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200">
            <div className="mb-1 font-semibold text-amber-800 dark:text-amber-300">
              Extraction warnings
            </div>
            <ul className="list-inside list-disc space-y-0.5">
              {preview.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </section>
        )}

        {create.isError && (
          <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
            {(create.error as Error).message}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!name.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Creating…" : "Create project"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function summarizeHoles(holes: Hole[]): [string, number][] {
  const tally: Record<string, number> = {};
  for (const h of holes) {
    const key = h.icon ?? "hole";
    tally[key] = (tally[key] ?? 0) + 1;
  }
  return Object.entries(tally).sort((a, b) => b[1] - a[1]);
}
