import type { Enclosure, Hole, IconKind, Side } from "@/api/client";
import { isOverflowing } from "./geometry";
import { ICON_DEFAULT_DIAMETER, ICON_KINDS, ICON_LABELS, paletteFor } from "./icons";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

interface Props {
  enclosure: Enclosure;
  hole: Hole | null;
  onChange: (patch: Partial<Hole>) => void;
  onDelete: () => void;
  onMirror: (mode: "x" | "y" | "ce") => void;
}

export function HoleInspector({ enclosure, hole, onChange, onDelete, onMirror }: Props) {
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

  const setIcon = (next: IconKind | null) => {
    if (next === null) {
      onChange({ icon: null });
      return;
    }
    // When picking an icon, also snap the diameter to the typical one if
    // the current diameter matches the previous icon's default (user
    // hasn't manually changed it).
    const prevDefault = hole.icon ? ICON_DEFAULT_DIAMETER[hole.icon] : null;
    const shouldAdoptDefault =
      prevDefault !== null && Math.abs(hole.diameter_mm - prevDefault) < 0.01;
    const patch: Partial<Hole> = { icon: next };
    if (shouldAdoptDefault || hole.icon === null) {
      patch.diameter_mm = ICON_DEFAULT_DIAMETER[next];
    }
    onChange(patch);
  };

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

      <Field label="Icon">
        <IconPicker value={hole.icon ?? null} onChange={setIcon} />
      </Field>

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

      <Field label="Mirror this hole">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={() => onMirror("x")} title="Create a twin with x flipped">
            Mirror X
          </Button>
          <Button size="sm" variant="secondary" onClick={() => onMirror("y")} title="Create a twin with y flipped">
            Mirror Y
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={hole.side !== "C" && hole.side !== "E"}
            onClick={() => onMirror("ce")}
            title="Duplicate this hole to the opposite side (C ↔ E)"
          >
            Mirror C↔E
          </Button>
        </div>
      </Field>

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

function IconPicker({
  value,
  onChange,
}: {
  value: IconKind | null;
  onChange: (v: IconKind | null) => void;
}) {
  return (
    <div className="grid grid-cols-4 gap-1.5">
      <IconTile
        label="none"
        color="#a1a1aa"
        selected={value === null}
        onClick={() => onChange(null)}
      />
      {ICON_KINDS.map((k) => (
        <IconTile
          key={k}
          label={shortLabel(k)}
          tooltip={ICON_LABELS[k]}
          color={paletteFor(k).fill}
          selected={value === k}
          onClick={() => onChange(k)}
        />
      ))}
    </div>
  );
}

function shortLabel(k: IconKind): string {
  switch (k) {
    case "pot":
      return "Pot";
    case "chicken-head":
      return "Chick";
    case "led":
      return "LED";
    case "footswitch":
      return "FSW";
    case "toggle":
      return "Tog";
    case "jack":
      return "Jack";
    case "dc-jack":
      return "DC";
    case "expression":
      return "Exp";
  }
}

function IconTile({
  label,
  tooltip,
  color,
  selected,
  onClick,
}: {
  label: string;
  tooltip?: string;
  color: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={tooltip}
      onClick={onClick}
      className={[
        "relative flex h-10 flex-col items-center justify-center gap-0.5 rounded border text-[10px] font-medium transition",
        selected
          ? "border-emerald-500 bg-emerald-50 text-emerald-900 ring-2 ring-emerald-500/40 dark:bg-emerald-900/30 dark:text-emerald-200"
          : "border-zinc-200 bg-white text-zinc-700 hover:border-emerald-300 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300",
      ].join(" ")}
    >
      <span
        className="h-3 w-3 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span>{label}</span>
    </button>
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
