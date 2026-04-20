import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, type PDFExtractOut } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

interface Props {
  file: File;
  preview: PDFExtractOut;
  onClose: () => void;
}

export function PdfReviewDialog({ file, preview, onClose }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const enclosures = useQuery({
    queryKey: ["enclosures"],
    queryFn: api.enclosures.list,
  });

  const [name, setName] = useState(preview.suggested_name ?? file.name.replace(/\.pdf$/i, ""));
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
    mutationFn: () => api.projects.createFromPdf(file, name, enclosure),
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
    if (t.includes("resistor")) k = "resistors";
    else if (t.includes("diode")) k = "diodes";
    else if (t.includes("electrolytic") || t.includes("tantalum")) k = "electro caps";
    else if (t.includes("op-amp") || t.includes("opamp") || t.includes("ic")) k = "ICs";
    else if (t.includes("transistor")) k = "transistors";
    else if (t.includes("cap") || t.includes("ceramic") || t.includes("film")) k = "caps";
    else if (t.includes("pot")) k = "pots";
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

        <section>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            BOM preview
          </div>
          {preview.bom.length === 0 ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
              No BOM rows detected. You can add them manually on the BOM tab.
            </div>
          ) : (
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm dark:border-zinc-800 dark:bg-zinc-900">
              <div className="mb-2 font-semibold">
                {preview.bom.length} rows:
              </div>
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
        </section>

        {preview.warnings.length > 0 && (
          <section className="rounded-md border border-zinc-200 bg-white p-3 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
            <div className="mb-1 font-semibold text-zinc-700 dark:text-zinc-300">
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
