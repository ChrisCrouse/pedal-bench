import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { api } from "@/api/client";
import { subscribeToApiKey } from "@/lib/apiKey";

/**
 * Tiny header pill showing whether AI features are reachable.
 *
 * Three states (driven by GET /api/v1/ai/status):
 *   - server env key configured  → emerald "AI: ready" (no link, nothing to do)
 *   - browser BYOK key set       → emerald "AI: your key" linking to /settings
 *   - no key                     → neutral zinc "AI: off" linking to /settings
 *
 * The no-key state is intentionally neutral — pedal-bench works without a
 * key for almost everything. The pill is honest signposting, not a nag.
 *
 * Also subscribes to in-tab key changes so the pill flips immediately
 * after Save / Clear without a manual reload.
 */
export function AIStatusPill() {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["aiStatus"],
    queryFn: api.aiStatus.get,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    return subscribeToApiKey(() => {
      qc.invalidateQueries({ queryKey: ["aiStatus"] });
    });
  }, [qc]);

  if (status.isLoading || !status.data) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-500 dark:bg-zinc-900">
        AI: …
      </span>
    );
  }

  if (!status.data.available) {
    return (
      <NavLink
        to="/settings"
        className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
        title="AI features are optional. Click to learn what's available with a key."
      >
        AI: off
      </NavLink>
    );
  }

  if (status.data.source === "env") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-200"
        title="Server has an Anthropic API key configured (env). AI features ready."
      >
        AI: ready
      </span>
    );
  }

  return (
    <NavLink
      to="/settings"
      className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-900 hover:bg-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-200 dark:hover:bg-emerald-900/50"
      title="Your browser-stored Anthropic key is active. Click to manage."
    >
      AI: your key
    </NavLink>
  );
}
