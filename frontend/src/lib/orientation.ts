// Polarity / orientation hints for BOM components, shared between
// BOMTab (column tooltips) and BenchTab (inline reminders).

const DEFAULT_ORIENTATION_HINTS: { match: string[]; hint: string }[] = [
  { match: ["signal diode", "diode"], hint: "Band = cathode — match the stripe on the PCB silkscreen" },
  { match: ["schottky"], hint: "Band = cathode — match the stripe on the PCB silkscreen" },
  { match: ["electrolytic", "tantalum"], hint: "+ leg (longer) → + marked pad on PCB" },
  { match: ["op-amp", "opamp", "dip"], hint: "Notch / dot = pin 1" },
  { match: ["transistor"], hint: "Flat side matches the flat on the PCB silkscreen" },
  { match: ["led"], hint: "+ leg (longer) = anode → + pad on PCB" },
];

export function defaultOrientationHint(bomType: string): string | null {
  const t = bomType.toLowerCase();
  for (const { match, hint } of DEFAULT_ORIENTATION_HINTS) {
    if (match.some((k) => t.includes(k))) return hint;
  }
  return null;
}

export function orientationHintFor(item: {
  type: string;
  orientation_hint?: string | null;
}): string | null {
  return item.orientation_hint ?? defaultOrientationHint(item.type);
}
