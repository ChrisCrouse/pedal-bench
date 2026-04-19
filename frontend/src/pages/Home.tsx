import { useQuery } from "@tanstack/react-query";
import { api, type Enclosure } from "@/api/client";

export function Home() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const enclosures = useQuery({
    queryKey: ["enclosures"],
    queryFn: api.enclosures.list,
  });

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-2xl font-semibold tracking-tight">Welcome</h2>
        <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
          v2 scaffolding is live. The drill designer is the next UI screen
          — this page confirms the frontend and backend are talking.
        </p>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <h3 className="text-lg font-semibold">Backend health</h3>
        <div className="mt-2 font-mono text-sm">
          {health.isLoading && <span className="text-zinc-500">loading…</span>}
          {health.isError && (
            <span className="text-red-600 dark:text-red-400">
              error: {(health.error as Error).message}
            </span>
          )}
          {health.data && (
            <span className="text-emerald-700 dark:text-emerald-400">
              {health.data.service} → {health.data.status}
            </span>
          )}
        </div>
      </section>

      <section>
        <h3 className="mb-3 text-lg font-semibold">Enclosure catalog</h3>
        {enclosures.isLoading && (
          <div className="text-sm text-zinc-500">loading enclosures…</div>
        )}
        {enclosures.isError && (
          <div className="text-sm text-red-600 dark:text-red-400">
            error: {(enclosures.error as Error).message}
          </div>
        )}
        {enclosures.data && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {enclosures.data.map((e) => (
              <EnclosureCard key={e.key} enclosure={e} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function EnclosureCard({ enclosure: e }: { enclosure: Enclosure }) {
  return (
    <article className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm transition hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900">
      <header className="flex items-baseline justify-between">
        <h4 className="font-semibold">{e.key}</h4>
        <span className="text-xs text-zinc-500">{Object.keys(e.faces).length} faces</span>
      </header>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{e.name}</p>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <Dim label="L" v={e.length_mm} />
        <Dim label="W" v={e.width_mm} />
        <Dim label="H" v={e.height_mm} />
      </dl>
      {e.notes && (
        <p className="mt-3 text-xs italic text-zinc-500 dark:text-zinc-500">{e.notes}</p>
      )}
    </article>
  );
}

function Dim({ label, v }: { label: string; v: number }) {
  return (
    <div className="rounded bg-zinc-100 p-2 text-center dark:bg-zinc-800">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="font-mono text-sm">{v} mm</div>
    </div>
  );
}
