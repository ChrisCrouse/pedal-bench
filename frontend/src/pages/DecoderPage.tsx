import { useState } from "react";
import {
  BAND_FG,
  BAND_HEX,
  bandsToResistor,
  capacitorDisplay,
  capacitorToText,
  parseCapacitor,
  parseResistor,
  resistorDisplay,
  resistorToBands,
  resistorToText,
  type BandColor,
} from "@/lib/decoders";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

const DIGIT_COLORS: BandColor[] = [
  "black", "brown", "red", "orange", "yellow",
  "green", "blue", "violet", "grey", "white",
];
const MULT_COLORS: BandColor[] = [
  "silver", "gold", "black", "brown", "red", "orange",
  "yellow", "green", "blue", "violet", "grey", "white",
];

export function DecoderPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Value Decoder</h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
          Bench reference. Type a value or pick color bands — both directions work.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ResistorCard />
        <CapacitorCard />
      </div>
    </div>
  );
}

function ResistorCard() {
  const [text, setText] = useState("4K7");
  const [bands, setBands] = useState<[BandColor, BandColor, BandColor]>([
    "yellow",
    "violet",
    "red",
  ]);

  let ohms: number | null = null;
  let parseError: string | null = null;
  try {
    ohms = parseResistor(text);
  } catch (e) {
    parseError = (e as Error).message;
  }

  const showBands = ohms !== null ? safeBands(ohms) : bands;

  const onBandChange = (idx: 0 | 1 | 2, color: BandColor) => {
    const next = [...bands] as [BandColor, BandColor, BandColor];
    next[idx] = color;
    setBands(next);
    try {
      const o = bandsToResistor(next);
      setText(resistorToText(o));
    } catch {
      // ignore; leave text as-is
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="font-semibold">Resistor</div>
      </CardHeader>
      <CardBody className="space-y-4">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Value (e.g. 4K7, 1M, 100R, 10k)
          </span>
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="font-mono"
          />
        </label>
        <div className="min-h-[1.5em] text-2xl font-semibold">
          {ohms !== null && resistorDisplay(ohms)}
          {parseError && <span className="text-red-600">?</span>}
        </div>

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            4-band color code
          </div>
          <div className="flex gap-1.5">
            {showBands.map((color, i) => (
              <div
                key={i}
                className="flex h-12 flex-1 items-center justify-center rounded text-xs font-medium"
                style={{
                  backgroundColor: BAND_HEX[color],
                  color: BAND_FG[color],
                }}
              >
                {color}
              </div>
            ))}
            <div
              className="flex h-12 w-10 items-center justify-center rounded text-[10px]"
              style={{ backgroundColor: BAND_HEX["gold"], color: BAND_FG["gold"] }}
              title="Tolerance — gold = 5%"
            >
              ±5%
            </div>
          </div>
        </div>

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Or pick bands
          </div>
          <div className="grid grid-cols-3 gap-2">
            <BandPicker
              options={DIGIT_COLORS}
              value={bands[0]}
              onChange={(c) => onBandChange(0, c)}
            />
            <BandPicker
              options={DIGIT_COLORS}
              value={bands[1]}
              onChange={(c) => onBandChange(1, c)}
            />
            <BandPicker
              options={MULT_COLORS}
              value={bands[2]}
              onChange={(c) => onBandChange(2, c)}
            />
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function safeBands(ohms: number): [BandColor, BandColor, BandColor] {
  try {
    const [a, b, c] = resistorToBands(ohms);
    return [a, b, c];
  } catch {
    return ["black", "black", "black"];
  }
}

function BandPicker({
  options,
  value,
  onChange,
}: {
  options: BandColor[];
  value: BandColor;
  onChange: (c: BandColor) => void;
}) {
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value as BandColor)}>
      {options.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </Select>
  );
}

function CapacitorCard() {
  const [text, setText] = useState("100n");
  let farads: number | null = null;
  let parseError: string | null = null;
  try {
    farads = parseCapacitor(text);
  } catch (e) {
    parseError = (e as Error).message;
  }

  const alt = farads !== null ? alternates(farads) : null;

  return (
    <Card>
      <CardHeader>
        <div className="font-semibold">Capacitor</div>
      </CardHeader>
      <CardBody className="space-y-4">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Value (e.g. 100n, 4n7, 10u, 100p)
          </span>
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="font-mono"
          />
        </label>
        <div className="min-h-[1.5em] text-2xl font-semibold">
          {farads !== null && capacitorDisplay(farads)}
          {parseError && <span className="text-red-600">?</span>}
        </div>
        {alt && (
          <div className="rounded-md bg-zinc-50 px-3 py-2 text-sm text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
            <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Also written as
            </div>
            <div className="mt-1 font-mono">
              {alt.join("   ·   ")}
            </div>
          </div>
        )}
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Canonical form
          </div>
          <div className="font-mono text-lg">
            {farads !== null && capacitorToText(farads)}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function alternates(farads: number): string[] {
  const alts: string[] = [];
  if (farads >= 1e-6) alts.push(`${fmt(farads * 1e6)} µF`);
  if (farads >= 1e-9 && farads < 1e-6) {
    alts.push(`${fmt(farads * 1e6)} µF`);
    alts.push(`${fmt(farads * 1e12)} pF`);
  }
  if (farads < 1e-9) alts.push(`${fmt(farads * 1e9)} nF`);
  return alts;
}

function fmt(x: number): string {
  return parseFloat(x.toPrecision(6)).toString();
}
