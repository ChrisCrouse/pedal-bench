import { Home } from "./pages/Home";

export function App() {
  return (
    <div className="min-h-full">
      <header className="border-b border-zinc-200/70 bg-white/80 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/60">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-baseline gap-3">
            <h1 className="text-xl font-semibold tracking-tight">pedal-bench</h1>
            <span className="text-sm text-zinc-500 dark:text-zinc-400">
              v0.2 · web UI
            </span>
          </div>
          <nav className="text-sm text-zinc-600 dark:text-zinc-400">
            <a href="/api/v1/docs" className="hover:text-zinc-900 dark:hover:text-zinc-100">
              API docs
            </a>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Home />
      </main>
    </div>
  );
}
