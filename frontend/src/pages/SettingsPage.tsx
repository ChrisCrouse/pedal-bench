import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { getApiKey, setApiKey, subscribeToApiKey } from "@/lib/apiKey";
import { getMouserKey, setMouserKey, subscribeToMouserKey } from "@/lib/mouserKey";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

export function SettingsPage() {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(getApiKey() ?? "");
  const [reveal, setReveal] = useState(false);
  const [saved, setSaved] = useState<"saved" | "cleared" | null>(null);

  // Live status from the backend (includes server-side env if no header sent).
  const status = useQuery({
    queryKey: ["aiStatus"],
    queryFn: api.aiStatus.get,
    staleTime: 0,
  });

  // Repaint if the key changes in another tab.
  useEffect(() => {
    return subscribeToApiKey(() => {
      setDraft(getApiKey() ?? "");
      qc.invalidateQueries({ queryKey: ["aiStatus"] });
    });
  }, [qc]);

  const onSave = () => {
    const trimmed = draft.trim();
    setApiKey(trimmed || null);
    setSaved(trimmed ? "saved" : "cleared");
    qc.invalidateQueries({ queryKey: ["aiStatus"] });
    setTimeout(() => setSaved(null), 3000);
  };

  const onClear = () => {
    setDraft("");
    setApiKey(null);
    setSaved("cleared");
    qc.invalidateQueries({ queryKey: ["aiStatus"] });
    setTimeout(() => setSaved(null), 3000);
  };

  const currentKey = getApiKey();
  const dirty = draft.trim() !== (currentKey ?? "");

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-6 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>

      <Card>
        <CardHeader>
          <div className="font-semibold">Anthropic API key</div>
        </CardHeader>
        <CardBody className="space-y-4 text-sm">
          <p className="text-zinc-600 dark:text-zinc-400">
            AI features (component photo verification, fault diagnosis, BOM/drill
            extraction fallbacks for older PDFs) call Anthropic's API on your
            behalf. Bring your own key — pedal-bench never stores it on its
            servers. The key sits in this browser's localStorage and rides on
            every API call as a request header.
          </p>

          <div className="rounded-md bg-zinc-50 p-3 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
            <div>
              <strong>Get a key:</strong>{" "}
              <a
                href="https://console.anthropic.com/settings/keys"
                target="_blank"
                rel="noopener noreferrer"
                className="text-emerald-700 hover:underline dark:text-emerald-400"
              >
                console.anthropic.com/settings/keys
              </a>
            </div>
            <div className="mt-1">
              <strong>Set a usage limit:</strong>{" "}
              <a
                href="https://console.anthropic.com/settings/limits"
                target="_blank"
                rel="noopener noreferrer"
                className="text-emerald-700 hover:underline dark:text-emerald-400"
              >
                console.anthropic.com/settings/limits
              </a>{" "}
              — recommended: $20/month while you're getting a feel for it.
              Realistic usage is around $1–5/month per active build.
            </div>
            <div className="mt-1">
              <strong>Modern PedalPCB PDFs work without a key.</strong> Only
              older "Parts List" layouts and the verify/diagnose features
              need AI.
            </div>
          </div>

          <label className="block">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Key
            </span>
            <div className="flex gap-2">
              <Input
                type={reveal ? "text" : "password"}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="sk-ant-api03-..."
                autoComplete="off"
                spellCheck={false}
                className="flex-1 font-mono text-xs"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setReveal((v) => !v)}
              >
                {reveal ? "Hide" : "Show"}
              </Button>
            </div>
          </label>

          <div className="flex items-center justify-between gap-2">
            <div className="text-xs">
              {status.data?.available ? (
                status.data.source === "header" ? (
                  <span className="text-emerald-700 dark:text-emerald-400">
                    Browser key active — AI features ready.
                  </span>
                ) : (
                  <span className="text-emerald-700 dark:text-emerald-400">
                    Server has a key configured (env var). AI features ready.
                  </span>
                )
              ) : (
                <span className="text-zinc-500">
                  No key configured. AI features will return errors.
                </span>
              )}
              {saved === "saved" && (
                <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200">
                  Saved
                </span>
              )}
              {saved === "cleared" && (
                <span className="ml-2 rounded bg-zinc-200 px-1.5 py-0.5 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                  Cleared
                </span>
              )}
            </div>
            <div className="flex gap-2">
              {currentKey && (
                <Button type="button" variant="ghost" onClick={onClear}>
                  Clear
                </Button>
              )}
              <Button
                type="button"
                variant="primary"
                onClick={onSave}
                disabled={!dirty}
              >
                {currentKey ? "Update" : "Save"}
              </Button>
            </div>
          </div>
        </CardBody>
      </Card>

      <MouserCard />

      <Card>
        <CardHeader>
          <div className="font-semibold">What uses the key?</div>
        </CardHeader>
        <CardBody className="space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
          <ul className="list-inside list-disc space-y-1">
            <li>
              <strong>BOM extraction fallback</strong> — for older PedalPCB
              PDFs that use a multi-column "Parts List" layout. ~$0.01/PDF.
            </li>
            <li>
              <strong>Drill template fallback</strong> — for image-only or
              unusually laid-out PDFs. ~$0.01/PDF.
            </li>
            <li>
              <strong>Component photo verification</strong> — verify button
              on each BOM row. ~$0.005–0.01/check.
            </li>
            <li>
              <strong>AI diagnosis</strong> — Debug tab. ~$0.02–0.05/call,
              less on repeat calls thanks to schematic prompt caching.
            </li>
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}

function MouserCard() {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(getMouserKey() ?? "");
  const [reveal, setReveal] = useState(false);
  const [saved, setSaved] = useState<"saved" | "cleared" | null>(null);

  const status = useQuery({
    queryKey: ["mouserStatus"],
    queryFn: api.mouser.status,
    staleTime: 0,
  });

  useEffect(() => {
    return subscribeToMouserKey(() => {
      setDraft(getMouserKey() ?? "");
      qc.invalidateQueries({ queryKey: ["mouserStatus"] });
    });
  }, [qc]);

  const onSave = () => {
    const trimmed = draft.trim();
    setMouserKey(trimmed || null);
    setSaved(trimmed ? "saved" : "cleared");
    qc.invalidateQueries({ queryKey: ["mouserStatus"] });
    setTimeout(() => setSaved(null), 3000);
  };

  const onClear = () => {
    setDraft("");
    setMouserKey(null);
    setSaved("cleared");
    qc.invalidateQueries({ queryKey: ["mouserStatus"] });
    setTimeout(() => setSaved(null), 3000);
  };

  const currentKey = getMouserKey();
  const dirty = draft.trim() !== (currentKey ?? "");

  return (
    <Card>
      <CardHeader>
        <div className="font-semibold">Mouser Search API key</div>
      </CardHeader>
      <CardBody className="space-y-4 text-sm">
        <p className="text-zinc-600 dark:text-zinc-400">
          Adds a "Stock @ Mouser" column to your BOM with live availability,
          pricing, and a buy link per part. Free key, instant signup.
          Mouser's terms forbid shared keys, so each user brings their own.
        </p>

        <div className="rounded-md bg-zinc-50 p-3 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
          <div>
            <strong>Get a free key:</strong>{" "}
            <a
              href="https://www.mouser.com/api-hub/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-emerald-700 hover:underline dark:text-emerald-400"
            >
              mouser.com/api-hub/
            </a>{" "}
            — sign in, pick "Search API," accept terms.
          </div>
          <div className="mt-1">
            <strong>Limits:</strong> 30 requests/minute, 1,000/day. We cache
            results for 6 hours so day-to-day BOM browsing stays well under.
          </div>
        </div>

        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Key
          </span>
          <div className="flex gap-2">
            <Input
              type={reveal ? "text" : "password"}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              autoComplete="off"
              spellCheck={false}
              className="flex-1 font-mono text-xs"
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setReveal((v) => !v)}
            >
              {reveal ? "Hide" : "Show"}
            </Button>
          </div>
        </label>

        <div className="flex items-center justify-between gap-2">
          <div className="text-xs">
            {status.data?.available ? (
              <span className="text-emerald-700 dark:text-emerald-400">
                Mouser key active — Stock column ready.
              </span>
            ) : (
              <span className="text-zinc-500">
                No Mouser key. Stock column will be hidden.
              </span>
            )}
            {saved === "saved" && (
              <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200">
                Saved
              </span>
            )}
            {saved === "cleared" && (
              <span className="ml-2 rounded bg-zinc-200 px-1.5 py-0.5 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                Cleared
              </span>
            )}
          </div>
          <div className="flex gap-2">
            {currentKey && (
              <Button type="button" variant="ghost" onClick={onClear}>
                Clear
              </Button>
            )}
            <Button
              type="button"
              variant="primary"
              onClick={onSave}
              disabled={!dirty}
            >
              {currentKey ? "Update" : "Save"}
            </Button>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
