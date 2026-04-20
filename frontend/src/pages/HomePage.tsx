import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type PDFExtractOut } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PdfDropZone } from "@/components/pdf/PdfDropZone";
import { PdfReviewDialog } from "@/components/pdf/PdfReviewDialog";

export function HomePage() {
  const [newOpen, setNewOpen] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PDFExtractOut | null>(null);
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects.list });

  const extract = useMutation({
    mutationFn: (file: File) => api.pdf.extract(file),
    onSuccess: (data, variables) => {
      setPendingFile(variables);
      setPreview(data);
    },
  });

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <section className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Your builds</h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            Start a new pedal build. Drop a PedalPCB PDF and we'll extract the BOM,
            enclosure, and title automatically — or build one up manually.
          </p>
        </div>
        <Button variant="secondary" size="lg" onClick={() => setNewOpen(true)}>
          + New (manual)
        </Button>
      </section>

      <section className="mt-6">
        <PdfDropZone
          disabled={extract.isPending}
          onFile={(file) => extract.mutate(file)}
        />
        {extract.isPending && (
          <div className="mt-2 text-center text-sm text-zinc-500">
            Extracting build package from PDF…
          </div>
        )}
        {extract.isError && (
          <div className="mt-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
            PDF extraction failed: {(extract.error as Error).message}
          </div>
        )}
      </section>

      <section className="mt-8">
        {projects.isLoading && <div className="text-sm text-zinc-500">loading…</div>}
        {projects.data?.length === 0 && (
          <Card>
            <CardBody className="py-16 text-center">
              <div className="text-lg font-medium">No builds yet</div>
              <div className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                Create your first project to get started.
              </div>
              <div className="mt-4 flex justify-center">
                <Button variant="primary" onClick={() => setNewOpen(true)}>
                  Create a project
                </Button>
              </div>
            </CardBody>
          </Card>
        )}
        {projects.data && projects.data.length > 0 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {projects.data.map((p) => (
              <Link key={p.slug} to={`/projects/${p.slug}`} className="block">
                <Card className="transition hover:shadow-md">
                  <CardBody>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate font-semibold">{p.name}</div>
                        <div className="mt-1 text-xs text-zinc-500">
                          {p.enclosure || "no enclosure set"} · updated{" "}
                          {new Date(p.updated_at).toLocaleDateString()}
                        </div>
                      </div>
                      <StatusBadge status={p.status} />
                    </div>
                  </CardBody>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>

      <NewProjectDialog open={newOpen} onClose={() => setNewOpen(false)} />
      {pendingFile && preview && (
        <PdfReviewDialog
          file={pendingFile}
          preview={preview}
          onClose={() => {
            setPendingFile(null);
            setPreview(null);
          }}
        />
      )}
    </div>
  );
}

function NewProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const enclosures = useQuery({
    queryKey: ["enclosures"],
    queryFn: api.enclosures.list,
  });

  const [name, setName] = useState("");
  const [enclosure, setEnclosure] = useState("125B");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () => api.projects.create({ name, enclosure }),
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setName("");
      setError(null);
      onClose();
      navigate(`/projects/${project.slug}`);
    },
    onError: (err) => setError(err instanceof Error ? err.message : String(err)),
  });

  return (
    <Dialog open={open} onClose={onClose} title="New project">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) return;
          createMutation.mutate();
        }}
        className="space-y-4"
      >
        <label className="block">
          <span className="mb-1 block text-sm font-medium">Name</span>
          <Input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Sherwood Overdrive"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-medium">Enclosure</span>
          <Select value={enclosure} onChange={(e) => setEnclosure(e.target.value)}>
            {enclosures.data?.map((e) => (
              <option key={e.key} value={e.key}>
                {e.key} — {e.name}
              </option>
            ))}
          </Select>
        </label>
        {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={!name.trim() || createMutation.isPending}
          >
            {createMutation.isPending ? "Creating…" : "Create"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
