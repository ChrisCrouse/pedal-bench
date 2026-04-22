import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useOutletContext } from "react-router-dom";
import { api, type Project, type Status } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { PhotosSection } from "@/components/overview/PhotosSection";

const STATUS_OPTIONS: Status[] = ["planned", "ordered", "building", "finishing", "done"];

interface ProjectCtx {
  slug: string;
  project: Project;
}

export function OverviewTab() {
  const { slug, project } = useOutletContext<ProjectCtx>();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const [name, setName] = useState(project.name);
  const [status, setStatus] = useState<Status>(project.status);
  const [notes, setNotes] = useState(project.notes);

  const updateMutation = useMutation({
    mutationFn: (payload: Partial<Pick<Project, "name" | "status" | "notes">>) =>
      api.projects.update(slug, payload),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["projects", updated.slug] });
      if (updated.slug !== slug) navigate(`/projects/${updated.slug}/overview`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.projects.delete(slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      navigate("/");
    },
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const attachMutation = useMutation({
    mutationFn: (file: File) => api.projects.attachPdf(slug, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", slug] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const dirty =
    name !== project.name || status !== project.status || notes !== project.notes;

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <Card>
        <CardHeader>
          <div className="font-semibold">Project details</div>
        </CardHeader>
        <CardBody className="space-y-4">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Slug">
            <div className="font-mono text-sm text-zinc-500">{project.slug}</div>
          </Field>
          <Field label="Enclosure">
            <div className="text-sm">
              {project.enclosure || <span className="text-zinc-500">not set</span>}
            </div>
          </Field>
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value as Status)}>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Notes">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={8}
              className="block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
              placeholder="Build notes, mods, measured voltages, stuff to remember for next time…"
            />
          </Field>
          <div className="flex items-center justify-between pt-2">
            <div className="text-xs text-zinc-500">
              Created {new Date(project.created_at).toLocaleString()} · Updated{" "}
              {new Date(project.updated_at).toLocaleString()}
            </div>
            <Button
              variant="primary"
              disabled={!dirty || updateMutation.isPending}
              onClick={() => updateMutation.mutate({ name, status, notes })}
            >
              {updateMutation.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <div className="font-semibold">Source PDF</div>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm text-zinc-600 dark:text-zinc-400">
              {project.source_pdf ? (
                <>
                  Attached:{" "}
                  <code className="rounded bg-zinc-100 px-1.5 py-0.5 dark:bg-zinc-800">
                    {project.source_pdf}
                  </code>
                  . Replace it to re-run BOM and drill extraction.
                </>
              ) : (
                <>No PDF attached yet. Drop one here to auto-extract drill holes.</>
              )}
            </div>
            <div className="flex items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                className="sr-only"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) attachMutation.mutate(f);
                  e.target.value = "";
                }}
              />
              <Button
                variant={project.source_pdf ? "secondary" : "primary"}
                onClick={() => fileInputRef.current?.click()}
                disabled={attachMutation.isPending}
              >
                {attachMutation.isPending
                  ? "Attaching…"
                  : project.source_pdf
                    ? "Replace PDF"
                    : "Attach PDF"}
              </Button>
            </div>
          </div>
          {attachMutation.isError && (
            <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
              Attach failed: {(attachMutation.error as Error).message}
            </div>
          )}
          {attachMutation.isSuccess && (
            <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200">
              PDF attached — drill holes auto-extracted (if the drill
              template page could be read). Open the Drill tab to review.
            </div>
          )}
        </CardBody>
      </Card>

      <PhotosSection slug={slug} />

      <Card>
        <CardHeader>
          <div className="font-semibold text-red-700 dark:text-red-400">Danger zone</div>
        </CardHeader>
        <CardBody>
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm text-zinc-600 dark:text-zinc-400">
              Delete this project. The folder at <code>projects/{slug}</code> will be
              removed, along with any attached PDFs, photos, and STLs.
            </div>
            <Button
              variant="danger"
              onClick={() => {
                if (confirm(`Delete project "${project.name}"? This cannot be undone.`)) {
                  deleteMutation.mutate();
                }
              }}
            >
              Delete project
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
        {label}
      </span>
      {children}
    </label>
  );
}
