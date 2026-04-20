/**
 * Component-type classification + color palette for the BOM view.
 *
 * The BOM table uses these to color-code rows by what kind of part each
 * row represents. The PCB-layout viewer uses the same palette for the
 * overlay dots so a "blue dot" on the image is always a resistor.
 */

import type { BOMItem } from "@/api/client";

export type ComponentKind =
  | "resistor"
  | "film-cap"
  | "electrolytic"
  | "diode"
  | "transistor"
  | "ic"
  | "pot"
  | "inductor"
  | "switch"
  | "other";

export const KIND_COLORS: Record<ComponentKind, { fill: string; stroke: string; text: string }> = {
  "resistor":     { fill: "#3b82f6", stroke: "#1d4ed8", text: "#ffffff" },
  "film-cap":     { fill: "#10b981", stroke: "#065f46", text: "#ffffff" },
  "electrolytic": { fill: "#06b6d4", stroke: "#0e7490", text: "#ffffff" },
  "diode":        { fill: "#f59e0b", stroke: "#b45309", text: "#000000" },
  "transistor":   { fill: "#f97316", stroke: "#c2410c", text: "#ffffff" },
  "ic":           { fill: "#8b5cf6", stroke: "#6d28d9", text: "#ffffff" },
  "pot":          { fill: "#ef4444", stroke: "#991b1b", text: "#ffffff" },
  "inductor":     { fill: "#eab308", stroke: "#854d0e", text: "#000000" },
  "switch":       { fill: "#a855f7", stroke: "#6b21a8", text: "#ffffff" },
  "other":        { fill: "#9ca3af", stroke: "#4b5563", text: "#ffffff" },
};

export const KIND_LABELS: Record<ComponentKind, string> = {
  "resistor":     "Resistor",
  "film-cap":     "Film / ceramic cap",
  "electrolytic": "Electrolytic cap",
  "diode":        "Diode",
  "transistor":   "Transistor",
  "ic":           "IC / op-amp",
  "pot":          "Pot",
  "inductor":     "Inductor",
  "switch":       "Switch",
  "other":        "Other",
};

export function classifyComponent(item: BOMItem): ComponentKind {
  const t = item.type.toLowerCase();
  const loc = item.location.toLowerCase();
  // Location prefix takes priority because PedalPCB refdes are consistent.
  if (loc.startsWith("ic")) return "ic";
  if (loc.startsWith("q")) return "transistor";
  if (loc.startsWith("d")) return "diode";
  if (loc.startsWith("l") && /^l\d+$/.test(loc)) return "inductor";
  if (loc.startsWith("sw") || loc.startsWith("s")) {
    if (/^s\d+$/.test(loc) || /^sw\d+$/.test(loc)) return "switch";
  }
  if (loc.startsWith("r") && /^r\d+$/.test(loc)) return "resistor";
  if (loc === "clr") return "resistor";
  if (loc.startsWith("c") && /^c\d+$/.test(loc)) {
    return t.includes("electrolytic") || t.includes("tantalum")
      ? "electrolytic"
      : "film-cap";
  }
  // Fall back to type string.
  if (t.includes("resistor")) return "resistor";
  if (t.includes("electrolytic") || t.includes("tantalum")) return "electrolytic";
  if (t.includes("cap") || t.includes("ceramic") || t.includes("film")) return "film-cap";
  if (t.includes("diode")) return "diode";
  if (t.includes("transistor") || t.includes("mosfet") || t.includes("jfet") || t.includes("bjt"))
    return "transistor";
  if (t.includes("op-amp") || t.includes("opamp") || t.includes("ic")) return "ic";
  if (t.includes("pot") || t.includes("potentiometer")) return "pot";
  if (t.includes("inductor") || t.includes("coil")) return "inductor";
  if (t.includes("switch") || t.includes("toggle")) return "switch";
  // Pots also identified by location being a word (LEVEL, DRIVE, etc.)
  if (/^[a-z]+$/i.test(loc)) return "pot";
  return "other";
}
