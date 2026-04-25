import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type DebugIC, type Project } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";

type PinReading = { pin: number; measured: string };

interface Props {
  slug: string;
  project: Project;
  selectedIc: DebugIC | null;
  readings: PinReading[];
}

type Confidence = "high" | "medium" | "low" | "error";

const CONFIDENCE_STYLE: Record<Confidence, { label: string; className: string }> = {
  high: {
    label: "High confidence",
    className:
      "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200",
  },
  medium: {
    label: "Medium confidence",
    className:
      "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200",
  },
  low: {
    label: "Low confidence",
    className:
      "border-zinc-300 bg-zinc-50 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200",
  },
  error: {
    label: "Error",
    className:
      "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-900/30 dark:text-red-200",
  },
};

export function DiagnoseCard({ slug, project, selectedIc, readings }: Props) {
  const [symptom, setSymptom] = useState("");
  const [includeImage, setIncludeImage] = useState(true);
  const hasWiring = project.source_pdf !== null;

  const run = useMutation({
    mutationFn: () =>
      api.diagnose.run(slug, {
        symptom: symptom.trim(),
        selected_ic: selectedIc?.key ?? null,
        readings: readings
          .map((r) => ({
            pin: r.pin,
            measured_v: r.measured.trim() === "" ? null : Number(r.measured),
          }))
          .filter((r) => r.measured_v !== null && !Number.isNaN(r.measured_v)),
        include_wiring_image: includeImage && hasWiring,
      }),
  });

  const result = run.data;
  const style = result ? CONFIDENCE_STYLE[result.confidence] : null;

  const measuredCount = readings.filter((r) => r.measured.trim() !== "").length;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="font-semibold">AI diagnosis</div>
          <div className="text-xs text-zinc-500">
            {measuredCount > 0
              ? `${measuredCount} reading${measuredCount === 1 ? "" : "s"} will be sent`
              : "no readings entered yet"}
          </div>
        </div>
      </CardHeader>
      <CardBody className="space-y-3">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Symptom
          </span>
          <textarea
            value={symptom}
            onChange={(e) => setSymptom(e.target.value)}
            rows={3}
            placeholder="e.g. no sound at output, LED lit · or: distorted only when gain is below 10 o'clock"
            className="block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            maxLength={500}
          />
        </label>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeImage && hasWiring}
            onChange={(e) => setIncludeImage(e.target.checked)}
            disabled={!hasWiring}
            className="h-4 w-4"
          />
          <span className={hasWiring ? "" : "text-zinc-400"}>
            Include cached wiring image (more accurate, costs a bit more)
          </span>
          {!hasWiring && (
            <span className="text-xs text-zinc-500">(no PDF attached)</span>
          )}
        </label>

        <div className="flex items-center justify-end">
          <Button
            variant="primary"
            disabled={run.isPending || !symptom.trim()}
            onClick={() => run.mutate()}
          >
            {run.isPending ? "Thinking…" : "Diagnose"}
          </Button>
        </div>

        {run.isError && (
          <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
            {(run.error as Error).message}
          </div>
        )}

        {result && style && (
          <div className={`space-y-3 rounded-md border p-4 text-sm ${style.className}`}>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider opacity-75">
                Primary suspect · {style.label}
              </div>
              <div className="mt-1 text-base font-semibold">
                {result.primary_suspect}
              </div>
            </div>

            {result.reasoning && (
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider opacity-75">
                  Reasoning
                </div>
                <div className="mt-1 whitespace-pre-wrap">{result.reasoning}</div>
              </div>
            )}

            {result.next_probe && (
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider opacity-75">
                  Probe next
                </div>
                <div className="mt-1">{result.next_probe}</div>
              </div>
            )}

            {result.alternative_suspects.length > 0 && (
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider opacity-75">
                  Also consider
                </div>
                <ul className="mt-1 list-inside list-disc">
                  {result.alternative_suspects.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}

            {result.caveats.length > 0 && (
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider opacity-75">
                  Caveats
                </div>
                <ul className="mt-1 list-inside list-disc text-xs opacity-80">
                  {result.caveats.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="text-xs opacity-60">
              {result.used_wiring_image
                ? "Based on the schematic image + voltage readings."
                : "Based on voltage readings only (no schematic in request)."}{" "}
              Verify before desoldering anything.
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
