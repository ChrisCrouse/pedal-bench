import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Enclosure, Hole, IconKind, LayoutPreset, Side } from "@/api/client";
import { api } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { ICON_KINDS, ICON_LABELS, paletteFor } from "./icons";
import type { MirrorState } from "./mirrors";

interface Props {
  enclosure: Enclosure;
  holes: Hole[];
  selectedIdx: number | null;
  onReplaceAll: (holes: Hole[]) => void;
  onAppend: (holes: Hole[]) => void;
  onMutateSelected: (patch: Partial<Hole>) => void;
  /** Current mirror-placement state; toggled creates twins on new holes. */
  mirrorState: MirrorState;
  onToggleMirror: (mode: "x" | "y" | "ce") => void;
  /** Default icon applied to new click-to-add holes. */
  defaultIcon: IconKind | null;
  onDefaultIconChange: (v: IconKind | null) => void;
  /** Snap toggle. */
  snapEnabled: boolean;
  onToggleSnap: (v: boolean) => void;
}

export function SmartLayouts({
  enclosure,
  holes,
  selectedIdx,
  onReplaceAll,
  onAppend,
  onMutateSelected,
  mirrorState,
  onToggleMirror,
  defaultIcon,
  onDefaultIconChange,
  snapEnabled,
  onToggleSnap,
}: Props) {
  const presets = useQuery({
    queryKey: ["layout-presets"],
    queryFn: api.layoutPresets.all,
    staleTime: Infinity,
  });

  const relevantPresets = useMemo(() => {
    if (!presets.data) return [] as LayoutPreset[];
    return presets.data.presets.filter(
      (p) => p.enclosure === enclosure.key,
    );
  }, [presets.data, enclosure.key]);

  const selectedHole: Hole | null = selectedIdx === null ? null : holes[selectedIdx] ?? null;

  const [spacingX, setSpacingX] = useState(25.4);
  const [spacingY, setSpacingY] = useState(25.4);
  const [gridFace, setGridFace] = useState<Side>("A");
  const [jackSide, setJackSide] = useState<Side>("B");
  const [jackCount, setJackCount] = useState(3);
  const [jackSpacing, setJackSpacing] = useState(22);
  const [jackDiameter, setJackDiameter] = useState(9.7);
  const [presetId, setPresetId] = useState<string>("");

  const pot2x2 = () => {
    const hx = spacingX / 2;
    const hy = spacingY / 2;
    const newHoles: Hole[] = [
      { side: gridFace, x_mm: -hx, y_mm: +hy, diameter_mm: 7.2, label: "POT 1", powder_coat_margin: true, icon: "pot" },
      { side: gridFace, x_mm: +hx, y_mm: +hy, diameter_mm: 7.2, label: "POT 2", powder_coat_margin: true, icon: "pot" },
      { side: gridFace, x_mm: -hx, y_mm: -hy, diameter_mm: 7.2, label: "POT 3", powder_coat_margin: true, icon: "pot" },
      { side: gridFace, x_mm: +hx, y_mm: -hy, diameter_mm: 7.2, label: "POT 4", powder_coat_margin: true, icon: "pot" },
    ];
    onAppend(newHoles);
  };

  const jackRow = () => {
    const total = (jackCount - 1) * jackSpacing;
    const startX = -total / 2;
    const newHoles: Hole[] = Array.from({ length: jackCount }, (_, i) => ({
      side: jackSide,
      x_mm: +(startX + i * jackSpacing).toFixed(1),
      y_mm: 0,
      diameter_mm: jackDiameter,
      label: `JACK ${i + 1}`,
      powder_coat_margin: true,
      icon: "jack" as const,
    }));
    onAppend(newHoles);
  };

  const centerBoth = () => onMutateSelected({ x_mm: 0, y_mm: 0 });
  const centerX = () => onMutateSelected({ x_mm: 0 });
  const centerY = () => onMutateSelected({ y_mm: 0 });

  const applyPreset = (mode: "replace" | "append") => {
    if (!presetId || !presets.data) return;
    const preset = presets.data.presets.find((p) => p.id === presetId);
    if (!preset) return;
    // Normalize holes to the client's Hole type (defaults where missing).
    const normalized: Hole[] = preset.holes.map((h) => ({
      side: h.side,
      x_mm: h.x_mm,
      y_mm: h.y_mm,
      diameter_mm: h.diameter_mm,
      label: h.label ?? null,
      powder_coat_margin: h.powder_coat_margin ?? true,
      icon: h.icon ?? null,
    }));
    if (mode === "replace") onReplaceAll(normalized);
    else onAppend(normalized);
  };

  const faceOptions = (["A", "B", "C", "D", "E"] as Side[]).filter((s) => !!enclosure.faces[s]);

  return (
    <div className="space-y-5 px-4 py-4 text-sm">
      <Section title="Placement aids">
        <div className="space-y-2">
          <ToggleRow
            label="Snap to guides"
            hint="Snap drag / place to common positions"
            checked={snapEnabled}
            onChange={onToggleSnap}
          />
          <ToggleRow
            label="Mirror X (vertical centerline)"
            hint="Also place a twin with x flipped"
            checked={mirrorState.x}
            onChange={() => onToggleMirror("x")}
          />
          <ToggleRow
            label="Mirror Y (horizontal centerline)"
            hint="Also place a twin with y flipped"
            checked={mirrorState.y}
            onChange={() => onToggleMirror("y")}
          />
          <ToggleRow
            label="Mirror C ↔ E (opposite sides)"
            hint="Also place a twin on the opposite side face"
            checked={mirrorState.ce}
            onChange={() => onToggleMirror("ce")}
          />
        </div>
      </Section>

      <Section title="Default icon for new holes">
        <DefaultIconPicker value={defaultIcon} onChange={onDefaultIconChange} />
      </Section>

      <Section title="Enclosure presets">
        {presets.isLoading && (
          <div className="text-xs text-zinc-500">loading presets…</div>
        )}
        {presets.isError && (
          <div className="text-xs text-red-600">
            couldn't load presets: {(presets.error as Error).message}
          </div>
        )}
        {presets.data && relevantPresets.length === 0 && (
          <div className="text-xs text-zinc-500">
            No presets yet for {enclosure.key}. (Add to
            <code> backend/pedal_bench/data/layout_presets.json</code>.)
          </div>
        )}
        {relevantPresets.length > 0 && (
          <>
            <Select value={presetId} onChange={(e) => setPresetId(e.target.value)}>
              <option value="">— choose a preset —</option>
              {groupByCategory(relevantPresets).map(([category, items]) => (
                <optgroup key={category} label={category}>
                  {items.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
            <div className="mt-2 flex gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={!presetId}
                onClick={() => applyPreset("append")}
              >
                Append
              </Button>
              <Button
                size="sm"
                variant="primary"
                disabled={!presetId}
                onClick={() => applyPreset("replace")}
              >
                Replace
              </Button>
            </div>
            {presetId && (
              <PresetDescription presets={relevantPresets} id={presetId} />
            )}
          </>
        )}
      </Section>

      <Section title="Potentiometer grid">
        <div className="grid grid-cols-2 gap-2">
          <LabeledMini label="Face">
            <Select value={gridFace} onChange={(e) => setGridFace(e.target.value as Side)}>
              {faceOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </LabeledMini>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <LabeledMini label="Spacing X (mm)">
            <Input
              type="number"
              step={0.5}
              value={spacingX}
              onChange={(e) => setSpacingX(Number(e.target.value))}
            />
          </LabeledMini>
          <LabeledMini label="Spacing Y (mm)">
            <Input
              type="number"
              step={0.5}
              value={spacingY}
              onChange={(e) => setSpacingY(Number(e.target.value))}
            />
          </LabeledMini>
        </div>
        <Button className="w-full" onClick={pot2x2}>
          Add 2×2 pot grid
        </Button>
      </Section>

      <Section title="Jack row">
        <div className="grid grid-cols-2 gap-2">
          <LabeledMini label="Face">
            <Select value={jackSide} onChange={(e) => setJackSide(e.target.value as Side)}>
              {faceOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </LabeledMini>
          <LabeledMini label="# of jacks">
            <Input
              type="number"
              step={1}
              min={1}
              max={8}
              value={jackCount}
              onChange={(e) => setJackCount(Math.max(1, Math.floor(Number(e.target.value))))}
            />
          </LabeledMini>
          <LabeledMini label="Spacing (mm)">
            <Input
              type="number"
              step={0.5}
              value={jackSpacing}
              onChange={(e) => setJackSpacing(Number(e.target.value))}
            />
          </LabeledMini>
          <LabeledMini label="Ø (mm)">
            <Input
              type="number"
              step={0.1}
              value={jackDiameter}
              onChange={(e) => setJackDiameter(Number(e.target.value))}
            />
          </LabeledMini>
        </div>
        <Button className="w-full" onClick={jackRow}>
          Add jack row
        </Button>
      </Section>

      <Section title="Selected hole">
        <div className="grid grid-cols-3 gap-2">
          <Button size="sm" disabled={!selectedHole} onClick={centerX} title="Set x = 0 (centerline)">
            Center X
          </Button>
          <Button size="sm" disabled={!selectedHole} onClick={centerY} title="Set y = 0 (centerline)">
            Center Y
          </Button>
          <Button size="sm" disabled={!selectedHole} onClick={centerBoth} title="Move to face center (0, 0)">
            Center
          </Button>
        </div>
        <p className="text-[11px] leading-snug text-zinc-500">
          Mirror actions live in Placement aids above (live linked pairs) or in the Hole inspector (one-off twin).
        </p>
      </Section>
    </div>
  );
}

function groupByCategory(
  list: LayoutPreset[],
): [string, LayoutPreset[]][] {
  const groups = new Map<string, LayoutPreset[]>();
  for (const p of list) {
    if (!groups.has(p.category)) groups.set(p.category, []);
    groups.get(p.category)!.push(p);
  }
  return Array.from(groups.entries()).map(([k, v]) => [titleCase(k), v]);
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function PresetDescription({
  presets,
  id,
}: {
  presets: LayoutPreset[];
  id: string;
}) {
  const preset = presets.find((p) => p.id === id);
  if (!preset) return null;
  return (
    <div className="mt-2 rounded-md bg-zinc-100 px-2.5 py-1.5 text-[11px] leading-snug text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
      <div className="font-semibold text-zinc-700 dark:text-zinc-300">
        {preset.holes.length} holes
      </div>
      {preset.description && <div>{preset.description}</div>}
    </div>
  );
}

function DefaultIconPicker({
  value,
  onChange,
}: {
  value: IconKind | null;
  onChange: (v: IconKind | null) => void;
}) {
  return (
    <div className="grid grid-cols-4 gap-1.5">
      <IconChip
        label="none"
        color="#a1a1aa"
        selected={value === null}
        onClick={() => onChange(null)}
      />
      {ICON_KINDS.map((k) => (
        <IconChip
          key={k}
          label={shortIconLabel(k)}
          tooltip={ICON_LABELS[k]}
          color={paletteFor(k).fill}
          selected={value === k}
          onClick={() => onChange(k)}
        />
      ))}
    </div>
  );
}

function shortIconLabel(k: IconKind): string {
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

function IconChip({
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
        "flex h-9 flex-col items-center justify-center gap-0.5 rounded border text-[10px] font-medium transition",
        selected
          ? "border-emerald-500 bg-emerald-50 text-emerald-900 ring-2 ring-emerald-500/40 dark:bg-emerald-900/30 dark:text-emerald-200"
          : "border-zinc-200 bg-white text-zinc-700 hover:border-emerald-300 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300",
      ].join(" ")}
    >
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
      <span>{label}</span>
    </button>
  );
}

function ToggleRow({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      className={[
        "flex cursor-pointer items-start gap-2 rounded border px-2 py-1.5",
        checked
          ? "border-emerald-400 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-900/20"
          : "border-transparent hover:border-zinc-300 dark:hover:border-zinc-700",
      ].join(" ")}
    >
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="flex-1">
        <span className="block text-sm">{label}</span>
        {hint && (
          <span className="block text-xs text-zinc-500">{hint}</span>
        )}
      </span>
    </label>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        {title}
      </h4>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function LabeledMini({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-0.5 block text-[10px] uppercase tracking-wider text-zinc-500">
        {label}
      </span>
      {children}
    </label>
  );
}
