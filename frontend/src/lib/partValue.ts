import type { ComponentKind } from "@/components/bom/componentColors";

/**
 * Mirror of backend `normalize_value` in pedal_bench/core/inventory_index.py.
 * Both must agree so the frontend can match BOM rows against owned-stock
 * keys without a server round-trip.
 */
export function normalizeValue(raw: string, kind: ComponentKind): string {
  if (!raw) return "";
  let v = raw.trim().replace(/µ/gi, "u");
  if (kind === "ic" || kind === "transistor" || kind === "diode") {
    return v.toUpperCase().replace(/\s+/g, "");
  }
  v = v
    .toLowerCase()
    .replace(
      /(?:[\d/.]+\s*)?(ohm|ohms|Ω|watt|watts|w|volts|volt|v|tolerance|tol)\s*[\d/.]*/gi,
      "",
    )
    .replace(/\s+/g, "");
  return v;
}

