import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

/** Hook for surfaces that need to gate themselves on AI availability.
 *
 *  Returns:
 *    null   while loading (don't render either branch yet)
 *    true   when an Anthropic key is reachable (env or BYOK header)
 *    false  when no key is configured
 *
 *  Usage pattern: hide AI-only UI surfaces entirely when this returns false.
 *  We deliberately don't ship a visible "AI required" notice anymore — the
 *  no-key path is a first-class experience and shouldn't be peppered with
 *  amber nags. The header AIStatusPill + Settings page handle discovery.
 */
export function useAIAvailable(): boolean | null {
  const status = useQuery({
    queryKey: ["aiStatus"],
    queryFn: api.aiStatus.get,
    staleTime: 30_000,
  });
  if (status.isLoading || !status.data) return null;
  return status.data.available;
}
