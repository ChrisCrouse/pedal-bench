/**
 * Heat-colored readiness indicator. Used in:
 *  - the sidebar next to each project so you can scan the list
 *  - the home page to sort/highlight which build is most ready
 *  - the Overview tab as the bigger Parts-ready card
 *
 * Color thresholds match the OverviewTab readiness card so a 65% dot in the
 * sidebar visually means the same thing as a 65% bar on Overview.
 */

interface Props {
  pct: number | null;
  /** Compact "•" (10px) for the sidebar; "lg" (14px + percent label) for
   *  inline use on cards. */
  size?: "sm" | "lg";
}

export function ReadinessDot({ pct, size = "sm" }: Props) {
  const color = readinessColor(pct);
  const dim = size === "sm" ? "h-2.5 w-2.5" : "h-3.5 w-3.5";
  const label =
    pct === null ? "No trackable BOM yet" : `${pct}% of parts ready`;
  return (
    <span
      title={label}
      aria-label={label}
      className="inline-flex shrink-0 items-center gap-1.5"
    >
      <span
        className={`${dim} shrink-0 rounded-full ${color.bg}`}
        style={pct === null ? { opacity: 0.4 } : undefined}
      />
      {size === "lg" && (
        <span className={`text-xs font-medium tabular-nums ${color.text}`}>
          {pct === null ? "—" : `${pct}%`}
        </span>
      )}
    </span>
  );
}

export function readinessColor(pct: number | null): {
  bg: string;
  text: string;
  border: string;
} {
  if (pct === null) {
    return {
      bg: "bg-zinc-300 dark:bg-zinc-700",
      text: "text-zinc-500",
      border: "border-zinc-300 dark:border-zinc-700",
    };
  }
  if (pct >= 100) {
    return {
      bg: "bg-emerald-500",
      text: "text-emerald-700 dark:text-emerald-400",
      border: "border-emerald-500",
    };
  }
  if (pct >= 80) {
    return {
      bg: "bg-emerald-400",
      text: "text-emerald-700 dark:text-emerald-400",
      border: "border-emerald-400",
    };
  }
  if (pct >= 50) {
    return {
      bg: "bg-amber-500",
      text: "text-amber-700 dark:text-amber-400",
      border: "border-amber-500",
    };
  }
  return {
    bg: "bg-red-500",
    text: "text-red-700 dark:text-red-400",
    border: "border-red-500",
  };
}
