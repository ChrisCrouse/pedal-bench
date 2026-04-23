import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { api, type TaydaPushOut } from "@/api/client";
import { getTaydaToken, subscribeToTaydaToken } from "@/lib/taydaToken";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";

interface Props {
  open: boolean;
  onClose: () => void;
  slug: string;
  projectName: string;
  holeCount: number;
}

/**
 * "Send to Tayda" dialog: posts the current drill layout into the user's
 * Tayda Kits Box Designer account as a new draft. Shows success with a
 * link to open the draft in Tayda's UI; shows their error body verbatim
 * on failure so we can diagnose API drift without a round-trip.
 */
export function TaydaPushDialog({
  open,
  onClose,
  slug,
  projectName,
  holeCount,
}: Props) {
  const [hasToken, setHasToken] = useState(!!getTaydaToken());
  const [isPublic, setIsPublic] = useState(false);
  const [name, setName] = useState(projectName);

  useEffect(() => {
    setName(projectName);
  }, [projectName]);

  useEffect(() => {
    return subscribeToTaydaToken(() => setHasToken(!!getTaydaToken()));
  }, []);

  const push = useMutation({
    mutationFn: () =>
      api.tayda.push(slug, {
        is_public: isPublic,
        name_override: name.trim() || undefined,
      }),
  });

  const result = push.data as TaydaPushOut | undefined;
  const errorMessage = push.isError ? (push.error as Error).message : null;

  const handleClose = () => {
    push.reset();
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} title="Send to Tayda" maxWidth="lg">
      <div className="space-y-4">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Push this project's drill layout into your Tayda Kits Box Designer
          account as a new draft. You can edit it in Tayda's UI afterwards
          or submit it for drilling directly from there.
        </p>

        {!hasToken && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200">
            No Tayda token set.{" "}
            <NavLink
              to="/settings"
              className="font-medium underline hover:text-amber-950 dark:hover:text-amber-100"
            >
              Paste one in Settings →
            </NavLink>
          </div>
        )}

        <div className="rounded-md bg-zinc-50 p-3 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
          <strong>Sending:</strong> {holeCount} hole{holeCount === 1 ? "" : "s"}{" "}
          from <span className="font-mono">{slug}</span>. Third-party API — may
          change without notice.
        </div>

        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Name (shown in Tayda)
          </span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            maxLength={80}
          />
        </label>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isPublic}
            onChange={(e) => setIsPublic(e.target.checked)}
            className="h-4 w-4"
          />
          <span>
            Make this design public on Tayda (default: private to your account)
          </span>
        </label>

        {errorMessage && (
          <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
            <div className="font-semibold">Push failed</div>
            <div className="mt-1 whitespace-pre-wrap font-mono">
              {errorMessage}
            </div>
          </div>
        )}

        {result && (
          <div className="rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200">
            <div className="font-semibold">Sent to Tayda.</div>
            {result.design_url ? (
              <div className="mt-1 text-xs">
                <a
                  href={result.design_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-emerald-950 dark:hover:text-emerald-100"
                >
                  Open in Tayda ↗
                </a>
                {result.design_id && (
                  <span className="ml-2 opacity-70">
                    (id: <span className="font-mono">{result.design_id}</span>)
                  </span>
                )}
              </div>
            ) : (
              <div className="mt-1 text-xs opacity-80">
                Saved, but Tayda's response didn't include a URL we
                recognize. Check your Tayda account to find the draft.
                {result.design_id && (
                  <span className="ml-1">
                    Design id: <span className="font-mono">{result.design_id}</span>
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={handleClose}>
            Close
          </Button>
          <Button
            variant="primary"
            disabled={!hasToken || push.isPending || holeCount === 0}
            onClick={() => push.mutate()}
          >
            {push.isPending ? "Sending…" : "Send to Tayda"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
