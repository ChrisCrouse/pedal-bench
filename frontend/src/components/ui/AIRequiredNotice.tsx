import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { api } from "@/api/client";

interface Props {
  feature: string;
  className?: string;
}

/** Shown inline above an AI-dependent surface when no key is configured.
 *  Encourages a one-click jump to /settings without scolding the user. */
export function AIRequiredNotice({ feature, className }: Props) {
  const status = useQuery({
    queryKey: ["aiStatus"],
    queryFn: api.aiStatus.get,
    staleTime: 30_000,
  });

  if (status.isLoading || status.data?.available !== false) return null;

  return (
    <div
      className={
        "rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200 " +
        (className ?? "")
      }
    >
      {feature} needs an Anthropic API key.{" "}
      <NavLink
        to="/settings"
        className="font-medium underline hover:text-amber-950 dark:hover:text-amber-100"
      >
        Set one up →
      </NavLink>
    </div>
  );
}

/** Hook for the surfaces that need to disable buttons when AI is missing. */
export function useAIAvailable(): boolean | null {
  const status = useQuery({
    queryKey: ["aiStatus"],
    queryFn: api.aiStatus.get,
    staleTime: 30_000,
  });
  if (status.isLoading || !status.data) return null;
  return status.data.available;
}
