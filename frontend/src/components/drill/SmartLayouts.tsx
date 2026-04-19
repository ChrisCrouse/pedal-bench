import { useState } from "react";
import type { Enclosure, Hole, Side } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

interface Props {
  enclosure: Enclosure;
  holes: Hole[];
  selectedIdx: number | null;
  onReplaceAll: (holes: Hole[]) => void;
  onAppend: (holes: Hole[]) => void;
  onMutateSelected: (patch: Partial<Hole>) => void;
}

/**
 * Smart-layout primitives. Each button is a common pedal-builder task
 * that would otherwise take 20 seconds of math.
 */
export function SmartLayouts({
  enclosure,
  holes,
  selectedIdx,
  onAppend,
  onMutateSelected,
}: Props) {
  const [spacingX, setSpacingX] = useState(25.4);
  const [spacingY, setSpacingY] = useState(25.4);
  const [gridFace, setGridFace] = useState<Side>("A");
  const [jackSide, setJackSide] = useState<Side>("B");
  const [jackCount, setJackCount] = useState(3);
  const [jackSpacing, setJackSpacing] = useState(22);
  const [jackDiameter, setJackDiameter] = useState(9.7);

  const selectedHole: Hole | null = selectedIdx === null ? null : holes[selectedIdx] ?? null;

  const pot2x2 = () => {
    const hx = spacingX / 2;
    const hy = spacingY / 2;
    const newHoles: Hole[] = [
      { side: gridFace, x_mm: -hx, y_mm: +hy, diameter_mm: 7.2, label: "POT 1", powder_coat_margin: true },
      { side: gridFace, x_mm: +hx, y_mm: +hy, diameter_mm: 7.2, label: "POT 2", powder_coat_margin: true },
      { side: gridFace, x_mm: -hx, y_mm: -hy, diameter_mm: 7.2, label: "POT 3", powder_coat_margin: true },
      { side: gridFace, x_mm: +hx, y_mm: -hy, diameter_mm: 7.2, label: "POT 4", powder_coat_margin: true },
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
    }));
    onAppend(newHoles);
  };

  const centerSelected = () => onMutateSelected({ x_mm: 0, y_mm: 0 });
  const mirrorX = () =>
    selectedHole && onMutateSelected({ x_mm: -selectedHole.x_mm });
  const mirrorY = () =>
    selectedHole && onMutateSelected({ y_mm: -selectedHole.y_mm });

  const faceOptions = (["A", "B", "C", "D", "E"] as Side[]).filter((s) => !!enclosure.faces[s]);

  return (
    <div className="space-y-5 px-4 py-4 text-sm">
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
          <Button
            size="sm"
            disabled={!selectedHole}
            onClick={centerSelected}
            title="Move to face center"
          >
            Center
          </Button>
          <Button
            size="sm"
            disabled={!selectedHole}
            onClick={mirrorX}
            title="Flip across Y axis"
          >
            Mirror X
          </Button>
          <Button
            size="sm"
            disabled={!selectedHole}
            onClick={mirrorY}
            title="Flip across X axis"
          >
            Mirror Y
          </Button>
        </div>
      </Section>
    </div>
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
