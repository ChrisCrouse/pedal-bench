import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type DebugIC, type DebugPin, type Project } from "@/api/client";
import { useOutletContext } from "react-router-dom";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { DiagnoseCard } from "@/components/debug/DiagnoseCard";
import { useAIAvailable } from "@/components/ui/AIRequiredNotice";

interface Ctx {
  slug: string;
  project: Project;
}

type PinReading = { pin: number; measured: string };

export function DebugTab() {
  const { slug, project } = useOutletContext<Ctx>();
  const dataset = useQuery({
    queryKey: ["debug", "dataset"],
    queryFn: api.debug.dataset,
    staleTime: Infinity,
  });

  // Pre-select an IC that's actually in the project's BOM, if we can find one.
  const bomValues = useMemo(
    () => project.bom.map((b) => b.value.toUpperCase()),
    [project.bom],
  );
  const defaultIcKey = useMemo(() => {
    if (!dataset.data) return null;
    const match = dataset.data.ics.find((ic) => bomValues.includes(ic.key.toUpperCase()));
    return match?.key ?? dataset.data.ics[0]?.key ?? null;
  }, [dataset.data, bomValues]);

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const effectiveKey = selectedKey ?? defaultIcKey;
  const selectedIc = dataset.data?.ics.find((ic) => ic.key === effectiveKey) ?? null;

  const [readings, setReadings] = useState<Record<string, PinReading[]>>({});
  const pinReadings = effectiveKey ? readings[effectiveKey] ?? [] : [];
  const aiAvailable = useAIAvailable();

  const updatePin = (pin: number, measured: string) => {
    if (!effectiveKey) return;
    setReadings((prev) => {
      const existing = prev[effectiveKey] ?? [];
      const next = existing.filter((r) => r.pin !== pin);
      if (measured.trim()) next.push({ pin, measured });
      next.sort((a, b) => a.pin - b.pin);
      return { ...prev, [effectiveKey]: next };
    });
  };

  if (dataset.isLoading)
    return <div className="p-10 text-center text-sm text-zinc-500">Loading debug data…</div>;
  if (dataset.isError)
    return (
      <div className="p-10 text-center text-sm text-red-600 dark:text-red-400">
        Couldn't load debug dataset: {(dataset.error as Error).message}
      </div>
    );
  if (!dataset.data) return null;

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-6 py-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="font-semibold">Expected IC pin voltages</div>
            <div className="text-xs text-zinc-500">
              V+ = {dataset.data.supply.vcc_v} V · VREF = {dataset.data.supply.vref_v} V
            </div>
          </div>
        </CardHeader>
        <CardBody>
          <label className="mb-3 block">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
              IC
            </span>
            <Select
              value={effectiveKey ?? ""}
              onChange={(e) => setSelectedKey(e.target.value || null)}
              className="w-80"
            >
              {dataset.data.ics.map((ic) => (
                <option key={ic.key} value={ic.key}>
                  {ic.key} — {ic.description.split(".")[0]}
                </option>
              ))}
            </Select>
          </label>

          {selectedIc && (
            <>
              <div className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
                {selectedIc.description}
                {selectedIc.common_in.length > 0 && (
                  <span className="ml-2 text-xs text-zinc-500">
                    Common in: {selectedIc.common_in.join(", ")}
                  </span>
                )}
              </div>
              <PinTable
                ic={selectedIc}
                readings={pinReadings}
                onMeasure={updatePin}
              />
            </>
          )}
        </CardBody>
      </Card>

      {aiAvailable && (
        <DiagnoseCard
          slug={slug}
          project={project}
          selectedIc={selectedIc}
          readings={pinReadings}
        />
      )}

      <Card>
        <CardHeader>
          <div className="font-semibold">Audio-probe procedure</div>
        </CardHeader>
        <CardBody>
          <ol className="list-inside list-decimal space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
            {dataset.data.audio_probe_procedure.map((step, i) => (
              <li key={i} className="pl-1">
                {step}
              </li>
            ))}
          </ol>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <div className="font-semibold">Common failure triage</div>
        </CardHeader>
        <CardBody className="space-y-4">
          {dataset.data.common_failures.map((f, i) => (
            <div key={i} className="border-l-2 border-amber-500 pl-3">
              <div className="font-medium">{f.symptom}</div>
              <ul className="mt-1 list-inside list-disc text-sm text-zinc-600 dark:text-zinc-400">
                {f.likely_causes.map((c, j) => (
                  <li key={j}>{c}</li>
                ))}
              </ul>
            </div>
          ))}
        </CardBody>
      </Card>
    </div>
  );
}

function PinTable({
  ic,
  readings,
  onMeasure,
}: {
  ic: DebugIC;
  readings: PinReading[];
  onMeasure: (pin: number, measured: string) => void;
}) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
        <tr>
          <Th className="w-12 text-center">Pin</Th>
          <Th>Name</Th>
          <Th className="w-24 text-right">Expected (V)</Th>
          <Th className="w-32">Measured (V)</Th>
          <Th className="w-32">Status</Th>
        </tr>
      </thead>
      <tbody>
        {ic.pins.map((p) => {
          const measured = readings.find((r) => r.pin === p.pin)?.measured ?? "";
          const measuredNum = measured.trim() === "" ? null : Number(measured);
          const status = pinStatus(p, measuredNum);
          return (
            <tr key={p.pin} className="border-b border-zinc-100 dark:border-zinc-800">
              <Td className="text-center font-mono font-semibold">{p.pin}</Td>
              <Td className="font-mono">{p.name}</Td>
              <Td className="text-right">
                {p.expected_v === null ? (
                  <span className="text-zinc-400">—</span>
                ) : (
                  <span className="font-mono">
                    {p.expected_v.toFixed(1)} ± {(p.tolerance_v ?? 0).toFixed(1)}
                  </span>
                )}
              </Td>
              <Td>
                <Input
                  type="number"
                  step="0.01"
                  placeholder={p.expected_v !== null ? String(p.expected_v.toFixed(1)) : "—"}
                  value={measured}
                  onChange={(e) => onMeasure(p.pin, e.target.value)}
                  className="py-1 text-sm"
                />
              </Td>
              <Td>
                <StatusChip status={status} />
              </Td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

type PinCheck = "unknown" | "ok" | "out_of_range" | "no_expected";

function pinStatus(p: DebugPin, measured: number | null): PinCheck {
  if (measured === null || Number.isNaN(measured)) return "unknown";
  if (p.expected_v === null) return "no_expected";
  const tol = p.tolerance_v ?? 0.1;
  return Math.abs(measured - p.expected_v) <= tol ? "ok" : "out_of_range";
}

function StatusChip({ status }: { status: PinCheck }) {
  if (status === "unknown") return null;
  const styles: Record<PinCheck, string> = {
    unknown: "",
    no_expected: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
    ok: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-300",
    out_of_range: "bg-red-100 text-red-900 dark:bg-red-900/30 dark:text-red-300",
  };
  const labels: Record<PinCheck, string> = {
    unknown: "",
    no_expected: "no target",
    ok: "ok",
    out_of_range: "out of range",
  };
  return (
    <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      className={`border-b border-zinc-200 px-3 py-2 text-left dark:border-zinc-800 ${className ?? ""}`}
    >
      {children}
    </th>
  );
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-3 py-1.5 align-middle ${className ?? ""}`}>{children}</td>;
}
