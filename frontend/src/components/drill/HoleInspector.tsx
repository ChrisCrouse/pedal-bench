import type { Enclosure, Hole, Side } from "@/api/client";
import { isOverflowing } from "./geometry";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

interface Props {
  enclosure: Enclosure;
  hole: Hole | null;
  onChange: (patch: Partial<Hole>) => void;
  onDelete: () => void;
}

export function HoleInspector({ enclosure, hole, onChange, onDelete }: Props) {
  if (!hole) {
    return (
      <div className="px-4 py-6 text-sm text-zinc-500">
        <div className="font-medium text-zinc-700 dark:text-zinc-300">No hole selected</div>
        <p className="mt-2">
          Click a face in the canvas to add a hole. Click an existing hole to edit it.
        </p>
      </div>
    );
  }

  const face = enclosure.faces[hole.side];
  const overflow = face
    ? isOverflowing(face, hole.x_mm, hole.y_mm, hole.diameter_mm)
    : false;
  const effective = hole.diameter_mm + (hole.powder_coat_margin ? 0.4 : 0);

  return (
    <div className="space-y-4 px-4 py-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold">Hole</div>
        <Button size="sm" variant="danger" onClick={onDelete}>
          Delete
        </Button>
      </div>

      {overflow && (
        <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
          This hole falls outside the face boundary.
        </div>
      )}

      <Field label="Side">
        <Select
          value={hole.side}
          onChange={(e) => onChange({ side: e.target.value as Side })}
        >
          {(["A", "B", "C", "D", "E"] as Side[]).map((s) => (
            <option key={s} value={s}>
              {s} — {enclosure.faces[s]?.label ?? "(not defined)"}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Label">
        <Input
          value={hole.label ?? ""}
          placeholder="e.g. LEVEL, INPUT, FOOTSWITCH"
          onChange={(e) => onChange({ label: e.target.value || null })}
        />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="X (mm)">
          <NumberInput
            value={hole.x_mm}
            step={0.1}
            onChange={(v) => onChange({ x_mm: v })}
          />
        </Field>
        <Field label="Y (mm)">
          <NumberInput
            value={hole.y_mm}
            step={0.1}
            onChange={(v) => onChange({ y_mm: v })}
          />
        </Field>
      </div>

      <Field label="Diameter (mm)">
        <div className="space-y-1">
          <NumberInput
            value={hole.diameter_mm}
            step={0.1}
            min={0.5}
            onChange={(v) => onChange({ diameter_mm: Math.max(0.5, v) })}
          />
          <div className="text-xs text-zinc-500">
            Effective (after PC margin): <span className="font-mono">{effective.toFixed(1)} mm</span>
          </div>
        </div>
      </Field>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={hole.powder_coat_margin}
          onChange={(e) => onChange({ powder_coat_margin: e.target.checked })}
          className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
        />
        <span>Add 0.4 mm for powder coat</span>
      </label>

      {face && (
        <div className="mt-4 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
          <div className="font-semibold text-zinc-700 dark:text-zinc-300">
            Face {hole.side} · {face.label}
          </div>
          <div className="mt-1 font-mono">
            {face.width_mm.toFixed(1)} × {face.height_mm.toFixed(1)} mm (W × H)
          </div>
          <div className="mt-1">
            Max coord from center: ±{(face.width_mm / 2).toFixed(1)} × ±
            {(face.height_mm / 2).toFixed(1)} mm
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
        {label}
      </span>
      {children}
    </label>
  );
}

function NumberInput({
  value,
  step = 1,
  min,
  onChange,
}: {
  value: number;
  step?: number;
  min?: number;
  onChange: (v: number) => void;
}) {
  return (
    <Input
      type="number"
      inputMode="decimal"
      step={step}
      min={min}
      value={Number.isFinite(value) ? value : 0}
      onChange={(e) => {
        const v = Number(e.target.value);
        if (!Number.isNaN(v)) onChange(v);
      }}
    />
  );
}
