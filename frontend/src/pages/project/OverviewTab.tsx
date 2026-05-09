import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
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
  const [active, setActive] = useState(project.active);
  const [enclosure, setEnclosure] = useState(project.enclosure);

  const enclosuresQuery = useQuery({
    queryKey: ["enclosures"],
    queryFn: api.enclosures.list,
    staleTime: Infinity,
  });

  const updateMutation = useMutation({
    mutationFn: (
      payload: Partial<Pick<Project, "name" | "status" | "notes" | "active" | "enclosure">>,
    ) => api.projects.update(slug, payload),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["projects", updated.slug] });
      if (updated.slug !== slug) navigate(`/projects/${updated.slug}/overview`);
    },
  });

  const consumeMutation = useMutation({
    mutationFn: () => api.projects.consumeReservations(slug),
    onSuccess: () => {
      // Consume drops inventory on_hand pool-wide, which shifts every
      // project's readiness % and the global shopping list. Invalidate
      // both trees so the UI catches up immediately.
      qc.invalidateQueries({ queryKey: ["inventory"] });
      qc.invalidateQueries({ queryKey: ["projects"] });
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
    name !== project.name ||
    status !== project.status ||
    notes !== project.notes ||
    active !== project.active ||
    enclosure !== project.enclosure;

  // Per-project shortage drives the readiness card. Same endpoint the Parts
  // tab uses, so it shares cache.
  const shortageQuery = useQuery({
    queryKey: ["projects", slug, "shortage"],
    queryFn: () => api.projects.shortage(slug),
  });

  // Global shortage drives the conflict card. Each row lists every active
  // project that needs the part; if multiple projects share a row AND the
  // total need exceeds stock, that's a contention point.
  const globalShortageQuery = useQuery({
    queryKey: ["inventory", "shortage"],
    queryFn: api.inventory.shortage,
  });

  // Project list — used to resolve competing slugs back into names. Same
  // cache key the sidebar uses, so this is free after first paint.
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: api.projects.list,
  });

  const conflicts = useMemo(() => {
    const rows = globalShortageQuery.data?.rows ?? [];
    const projectsByName = new Map<string, string>();
    for (const p of projectsQuery.data ?? []) projectsByName.set(p.slug, p.name);
    return rows.filter(
      (r) =>
        r.shortfall > 0 &&
        r.needed_by.includes(slug) &&
        r.needed_by.length > 1,
    ).map((r) => ({
      kind: r.kind,
      value: r.display_value,
      shortfall: r.shortfall,
      onHand: r.on_hand,
      needed: r.needed,
      competitors: r.needed_by
        .filter((s) => s !== slug)
        .map((s) => ({ slug: s, name: projectsByName.get(s) ?? s })),
    }));
  }, [globalShortageQuery.data, projectsQuery.data, slug]);

  const stats = useMemo(() => {
    const rows = shortageQuery.data?.rows ?? [];
    let needed = 0;
    let covered = 0;
    let costToFinish = 0;
    let hasAnyCost = false;
    let costEstimated = false;
    for (const r of rows) {
      needed += r.needed;
      // What we can actually cover for this build = free stock + what we've
      // already reserved for ourselves, capped at what we need.
      const have = Math.min(r.needed, r.available + r.reserved_for_self);
      covered += have;
      if (r.unit_cost_usd != null && r.shortfall > 0) {
        costToFinish += r.unit_cost_usd * r.shortfall;
        hasAnyCost = true;
        if (r.unit_cost_estimated) costEstimated = true;
      }
    }
    const readyPct = needed > 0 ? Math.round((100 * covered) / needed) : null;
    const totalParts = project.bom.length;
    const soldered = project.progress.soldered_locations.length;
    const solderPct = totalParts > 0 ? Math.round((100 * soldered) / totalParts) : null;
    return {
      readyPct,
      needed,
      covered,
      shortBy: Math.max(0, needed - covered),
      solderPct,
      soldered,
      totalParts,
      costToFinish: hasAnyCost ? costToFinish : null,
      costEstimated,
    };
  }, [shortageQuery.data, project.bom.length, project.progress.soldered_locations]);

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <div className="grid grid-cols-3 gap-3">
        <ReadinessCard
          pct={stats.readyPct}
          covered={stats.covered}
          needed={stats.needed}
          shortBy={stats.shortBy}
          isLoading={shortageQuery.isLoading}
        />
        <ProgressCard
          pct={stats.solderPct}
          soldered={stats.soldered}
          totalParts={stats.totalParts}
        />
        <CostCard cost={stats.costToFinish} estimated={stats.costEstimated} />
      </div>

      {conflicts.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <span className="inline-flex h-2 w-2 rounded-full bg-amber-500" />
              <span className="font-semibold">
                Reservation conflicts ({conflicts.length})
              </span>
            </div>
          </CardHeader>
          <CardBody>
            <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
              These parts are needed by this build <em>and</em> at least one
              other active project. Total demand exceeds your current stock —
              you'll need to order more, deactivate one of the competing
              projects, or accept that they can't both be built right now.
            </p>
            <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {conflicts.map((c) => (
                <li
                  key={`${c.kind}-${c.value}`}
                  className="flex items-center gap-3 py-2 text-sm"
                >
                  <span className="w-20 shrink-0 font-mono font-semibold">
                    {c.value}
                  </span>
                  <span className="w-24 shrink-0 text-xs text-zinc-500">
                    {c.kind.replace("-", " ")}
                  </span>
                  <span className="flex-1 truncate text-zinc-600 dark:text-zinc-400">
                    Also needed by{" "}
                    {c.competitors.map((p, i) => (
                      <span key={p.slug}>
                        <Link
                          to={`/projects/${p.slug}`}
                          className="text-emerald-700 hover:underline dark:text-emerald-400"
                        >
                          {p.name}
                        </Link>
                        {i < c.competitors.length - 1 ? ", " : ""}
                      </span>
                    ))}
                  </span>
                  <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-amber-900 dark:bg-amber-900/40 dark:text-amber-300">
                    short {c.shortfall}
                  </span>
                  <span className="shrink-0 text-xs text-zinc-500 tabular-nums">
                    {c.onHand}/{c.needed}
                  </span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}

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
            <Select
              value={enclosure}
              onChange={(e) => setEnclosure(e.target.value)}
              disabled={!enclosuresQuery.data}
            >
              {!enclosure && <option value="">— choose enclosure —</option>}
              {enclosuresQuery.data?.map((e) => (
                <option key={e.key} value={e.key}>
                  {e.key} — {e.name}
                </option>
              ))}
            </Select>
            {project.holes.length > 0 && enclosure !== project.enclosure && (
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                This project has {project.holes.length} hole
                {project.holes.length === 1 ? "" : "s"} placed on{" "}
                <span className="font-mono">{project.enclosure}</span>. Their
                coordinates won't move — re-check the Drill designer if face
                dimensions differ.
              </p>
            )}
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
          <Field label="Active">
            <label className="inline-flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
              />
              <span className="text-zinc-600 dark:text-zinc-400">
                Include this project's BOM in the global shopping list. Turn off
                for someday/maybe builds you don't want inflating shortages.
              </span>
            </label>
          </Field>
          <div className="flex items-center justify-between pt-2">
            <div className="text-xs text-zinc-500">
              Created {new Date(project.created_at).toLocaleString()} · Updated{" "}
              {new Date(project.updated_at).toLocaleString()}
            </div>
            <Button
              variant="primary"
              disabled={!dirty || updateMutation.isPending}
              onClick={() =>
                updateMutation.mutate({ name, status, notes, active, enclosure })
              }
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
              {project.source_pdf && (
                <a
                  href={`/api/v1/projects/${encodeURIComponent(slug)}/source.pdf`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center justify-center gap-1.5 rounded-md bg-zinc-200 px-3.5 py-1.5 text-sm font-medium text-zinc-900 transition hover:bg-zinc-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700"
                  title="Open the build doc in a new tab. Use your browser's print dialog (set scale to 100%) to print the whole doc or specific pages."
                >
                  Open build doc
                </a>
              )}
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
          <div className="font-semibold">Inventory</div>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="text-sm text-zinc-600 dark:text-zinc-400">
              When the build is done, click <strong>Consume reservations</strong>{" "}
              to subtract every part you reserved for this project from your
              owned stock and clear the reservations. Reservations themselves
              are managed from the Parts tab.
            </div>
            <Button
              variant="secondary"
              disabled={consumeMutation.isPending}
              onClick={() => {
                if (
                  confirm(
                    `Subtract this build's reserved parts from your inventory? This is appropriate after you've physically used them.`,
                  )
                ) {
                  consumeMutation.mutate();
                }
              }}
            >
              {consumeMutation.isPending ? "Consuming…" : "Consume reservations"}
            </Button>
          </div>
          {consumeMutation.isSuccess && (
            <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200">
              Consumed {consumeMutation.data.consumed.length} part type
              {consumeMutation.data.consumed.length === 1 ? "" : "s"} from
              inventory.
            </div>
          )}
          {consumeMutation.isError && (
            <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
              Failed: {(consumeMutation.error as Error).message}
            </div>
          )}
        </CardBody>
      </Card>

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

// ---------------------------------------------------------------------------
// Stat cards: readiness / progress / cost-to-finish.
//
// Heat-color thresholds (used by Readiness):
//   < 50   → red (need to order most of the BOM)
//   50–79  → amber (partial coverage)
//   80–99  → emerald (close, but a few short)
//   100    → solid emerald (ready to build)
// ---------------------------------------------------------------------------

type Tone = "red" | "amber" | "emerald" | "zinc";

function heatTone(pct: number | null): Tone {
  if (pct === null) return "zinc";
  if (pct < 50) return "red";
  if (pct < 80) return "amber";
  return "emerald";
}

function toneClasses(tone: Tone): {
  text: string;
  bar: string;
  bg: string;
  border: string;
} {
  switch (tone) {
    case "red":
      return {
        text: "text-red-700 dark:text-red-400",
        bar: "bg-red-500",
        bg: "bg-red-50 dark:bg-red-950/30",
        border: "border-red-300 dark:border-red-900",
      };
    case "amber":
      return {
        text: "text-amber-700 dark:text-amber-400",
        bar: "bg-amber-500",
        bg: "bg-amber-50 dark:bg-amber-950/30",
        border: "border-amber-300 dark:border-amber-900",
      };
    case "emerald":
      return {
        text: "text-emerald-700 dark:text-emerald-400",
        bar: "bg-emerald-500",
        bg: "bg-emerald-50 dark:bg-emerald-950/30",
        border: "border-emerald-300 dark:border-emerald-900",
      };
    default:
      return {
        text: "text-zinc-700 dark:text-zinc-300",
        bar: "bg-zinc-400",
        bg: "bg-white dark:bg-zinc-950",
        border: "border-zinc-200 dark:border-zinc-800",
      };
  }
}

function StatCardShell({
  label,
  tone,
  children,
}: {
  label: string;
  tone: Tone;
  children: React.ReactNode;
}) {
  const t = toneClasses(tone);
  return (
    <div
      className={`rounded-lg border ${t.border} ${t.bg} px-4 py-3 transition`}
    >
      <div className="text-xs font-medium uppercase tracking-wider text-zinc-500">
        {label}
      </div>
      {children}
    </div>
  );
}

function ReadinessCard({
  pct,
  covered,
  needed,
  shortBy,
  isLoading,
}: {
  pct: number | null;
  covered: number;
  needed: number;
  shortBy: number;
  isLoading: boolean;
}) {
  const tone = heatTone(pct);
  const t = toneClasses(tone);
  return (
    <StatCardShell label="Parts ready" tone={tone}>
      <div className={`mt-1 text-3xl font-semibold tabular-nums ${t.text}`}>
        {isLoading ? "…" : pct === null ? "—" : `${pct}%`}
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div
          className={`h-full ${t.bar} transition-all`}
          style={{ width: `${pct ?? 0}%` }}
        />
      </div>
      <div className="mt-1.5 text-xs text-zinc-500">
        {needed === 0
          ? "No trackable parts"
          : shortBy === 0
            ? `${covered}/${needed} covered`
            : `${covered}/${needed} covered · short ${shortBy}`}
      </div>
    </StatCardShell>
  );
}

function ProgressCard({
  pct,
  soldered,
  totalParts,
}: {
  pct: number | null;
  soldered: number;
  totalParts: number;
}) {
  // Build progress is independent of heat — just neutral with emerald fill.
  // Use emerald tone only when fully done so a finished build pops.
  const tone: Tone = pct === 100 ? "emerald" : "zinc";
  const t = toneClasses(tone);
  return (
    <StatCardShell label="Build progress" tone={tone}>
      <div className={`mt-1 text-3xl font-semibold tabular-nums ${t.text}`}>
        {pct === null ? "—" : `${pct}%`}
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div
          className="h-full bg-emerald-500 transition-all"
          style={{ width: `${pct ?? 0}%` }}
        />
      </div>
      <div className="mt-1.5 text-xs text-zinc-500">
        {totalParts === 0 ? "No BOM yet" : `${soldered}/${totalParts} soldered`}
      </div>
    </StatCardShell>
  );
}

function CostCard({
  cost,
  estimated,
}: {
  cost: number | null;
  estimated: boolean;
}) {
  // The "~" prefix is the visual contract — once you see it on a number,
  // you know that number isn't your actual paid price. Keep it consistent
  // with the InventoryPage shopping list.
  const display =
    cost === null
      ? "—"
      : `${estimated ? "~" : ""}$${cost.toFixed(2)}`;
  const subtitle =
    cost === null
      ? "Set unit costs on inventory items"
      : estimated
        ? "Includes typical-Tayda estimates · set unit costs to refine"
        : "Sum of unit cost × shortfall";
  return (
    <StatCardShell label="Cost to finish" tone="zinc">
      <div className="mt-1 text-3xl font-semibold tabular-nums text-zinc-700 dark:text-zinc-300">
        {display}
      </div>
      <div className="mt-1.5 text-xs text-zinc-500">{subtitle}</div>
    </StatCardShell>
  );
}
