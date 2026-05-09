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

/**
 * Extract a short pill-friendly label from a long orientation hint. Hints
 * conventionally use ` — ` (em dash) or ` → ` to separate a punchy summary
 * from the longer "how to apply" sentence. We render the summary in the
 * column and let the tooltip carry the full text.
 *
 *   "Band = cathode — match the stripe on the PCB silkscreen" → "Band = cathode"
 *   "+ leg (longer) → + marked pad on PCB"                     → "+ leg (longer)"
 *   "Notch / dot = pin 1"                                      → "Notch / dot = pin 1"
 *   "Flat side matches the flat on the PCB silkscreen"         → "Flat side"
 */
export function orientationHintSummary(hint: string): string {
  // Cut at the first separator if present.
  const sepMatch = hint.match(/^([^—→]+?)\s*[—→]/);
  if (sepMatch) return sepMatch[1].trim();
  // No separator — keep the first short phrase (max 22 chars on a word boundary).
  if (hint.length <= 22) return hint;
  const cut = hint.slice(0, 22);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > 8 ? cut.slice(0, lastSpace) : cut) + "…";
}
