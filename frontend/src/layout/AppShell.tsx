import { NavLink, Outlet, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { StatusBadge } from "@/components/ui/StatusBadge";

export function AppShell() {
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: api.projects.list,
  });

  const { slug } = useParams<{ slug?: string }>();

  return (
    <div className="flex h-screen flex-col">
      <Header />
      <div className="flex min-h-0 flex-1">
        <aside className="w-64 shrink-0 overflow-y-auto border-r border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950">
          <div className="p-3">
            <NavLink
              to="/"
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
                  isActive
                    ? "bg-zinc-200 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
                }`
              }
              end
            >
              <span>Home</span>
            </NavLink>
          </div>
          <div className="px-3 pb-2 pt-4 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Projects
          </div>
          <nav className="space-y-0.5 px-2 pb-4">
            {projects.isLoading && (
              <div className="px-3 py-2 text-sm text-zinc-500">loading…</div>
            )}
            {projects.data?.length === 0 && (
              <div className="px-3 py-2 text-sm text-zinc-500">
                No projects yet. Create one from Home.
              </div>
            )}
            {projects.data?.map((p) => (
              <NavLink
                key={p.slug}
                to={`/projects/${p.slug}`}
                className={({ isActive }) =>
                  `flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm ${
                    isActive || p.slug === slug
                      ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-900/20 dark:text-emerald-200"
                      : "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
                  }`
                }
              >
                <span className="truncate">{p.name}</span>
                <StatusBadge status={p.status} />
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function Header() {
  return (
    <header className="flex items-center justify-between border-b border-zinc-200 bg-white/90 px-6 py-3 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/80">
      <NavLink to="/" className="flex items-baseline gap-2 font-semibold tracking-tight">
        <span className="text-lg">pedal-bench</span>
        <span className="text-xs text-zinc-500">v0.2</span>
      </NavLink>
      <nav className="flex items-center gap-4 text-sm text-zinc-600 dark:text-zinc-400">
        <NavLink
          to="/decoder"
          className={({ isActive }) =>
            isActive
              ? "font-medium text-emerald-700 dark:text-emerald-400"
              : "hover:text-zinc-900 dark:hover:text-zinc-100"
          }
        >
          Decoder
        </NavLink>
        <a
          href="http://127.0.0.1:8642/docs"
          target="_blank"
          rel="noreferrer"
          className="hover:text-zinc-900 dark:hover:text-zinc-100"
        >
          API docs
        </a>
        <a
          href="https://github.com/ChrisCrouse/pedal-bench"
          target="_blank"
          rel="noreferrer"
          className="hover:text-zinc-900 dark:hover:text-zinc-100"
        >
          GitHub
        </a>
      </nav>
    </header>
  );
}
