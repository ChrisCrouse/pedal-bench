import { NavLink, Outlet, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { StatusBadge } from "@/components/ui/StatusBadge";

const TABS = [
  { to: "overview", label: "Overview" },
  { to: "drill", label: "Drill designer" },
  { to: "bom", label: "BOM" },
  { to: "bench", label: "Bench" },
  { to: "debug", label: "Debug" },
] as const;

export function ProjectPage() {
  const { slug = "" } = useParams<{ slug: string }>();
  const project = useQuery({
    queryKey: ["projects", slug],
    queryFn: () => api.projects.get(slug),
    enabled: !!slug,
  });

  if (project.isLoading) return <CenteredMessage text="loading project…" />;
  if (project.isError)
    return (
      <CenteredMessage
        text={`could not load project: ${(project.error as Error).message}`}
        tone="error"
      />
    );
  if (!project.data) return <CenteredMessage text="project not found" tone="error" />;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-zinc-200 bg-white px-6 pt-5 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">
              {project.data.name}
            </h1>
            <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500">
              <StatusBadge status={project.data.status} />
              <span>{project.data.enclosure || "no enclosure"}</span>
              <span>·</span>
              <span>{project.data.bom.length} BOM items</span>
              <span>·</span>
              <span>{project.data.holes.length} holes</span>
            </div>
          </div>
        </div>
        <nav className="mt-5 flex gap-1">
          {TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) =>
                `border-b-2 px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? "border-emerald-500 text-emerald-700 dark:text-emerald-400"
                    : "border-transparent text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                }`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Outlet context={{ slug, project: project.data }} />
      </div>
    </div>
  );
}

function CenteredMessage({
  text,
  tone = "muted",
}: {
  text: string;
  tone?: "muted" | "error";
}) {
  return (
    <div
      className={`flex h-full items-center justify-center text-sm ${
        tone === "error" ? "text-red-600 dark:text-red-400" : "text-zinc-500"
      }`}
    >
      {text}
    </div>
  );
}
