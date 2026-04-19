import type { Status } from "@/api/client";

const STYLES: Record<Status, string> = {
  planned: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  ordered: "bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-300",
  building: "bg-blue-100 text-blue-900 dark:bg-blue-900/30 dark:text-blue-300",
  finishing: "bg-violet-100 text-violet-900 dark:bg-violet-900/30 dark:text-violet-300",
  done: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-300",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${STYLES[status]}`}
    >
      {status}
    </span>
  );
}
