import type { ComponentKind } from "@/components/bom/componentColors";

/**
 * Mirror of `value_magnitude` + `normalize_value` from
 * pedal_bench/core/inventory_index.py. Both must stay in lockstep so the
 * frontend can match BOM rows against owned-stock keys without a server
 * round-trip. Full grammar lives in the README under "Resistor and
 * Capacitor Value Conversion Rules".
 */

const RES_MULTIPLIER: Record<string, number> = {
  R: 1,
  K: 1e3,
  M: 1e6,
  G: 1e9,
};

const CAP_MULTIPLIER: Record<string, number> = {
  p: 1e-12,
  n: 1e-9,
  u: 1e-6,
  m: 1e-3,
};

function stripMicro(s: string): string {
  // Both U+00B5 (micro sign) and U+03BC (Greek mu) → ASCII u
  return s.replace(/µ/g, "u").replace(/μ/g, "u");
}

// Resistor tolerance suffix stripping. F/J always tolerance after digits;
// K/M/G are multipliers when bare, tolerance only when a multiplier letter
// already appears earlier in the string.
const RES_TOL_AFTER_MULT_RE = /^([\d.]*[RKMG][\d.]*)([FGJKM])$/i;
const RES_TOL_PURE_DIGITS_RE = /^([\d.]+)([FJ])$/i;

function stripResistorTolerance(s: string): string {
  let m = s.match(RES_TOL_AFTER_MULT_RE);
  if (m) return m[1];
  m = s.match(RES_TOL_PURE_DIGITS_RE);
  if (m) return m[1];
  return s;
}

function parseResistorMagnitude(s: string): number | null {
  s = stripResistorTolerance(s);

  // R-prefix: "R22" = 0.22Ω
  let m = s.match(/^([RKMG])(\d+)$/i);
  if (m) {
    const mult = RES_MULTIPLIER[m[1].toUpperCase()];
    const v = parseFloat(`0.${m[2]}`);
    return isFinite(v) ? v * mult : null;
  }

  // Letter-as-decimal-point: "4K7" = 4.7k
  m = s.match(/^(\d+)([RKMG])(\d+)$/i);
  if (m) {
    const mult = RES_MULTIPLIER[m[2].toUpperCase()];
    const v = parseFloat(`${m[1]}.${m[3]}`);
    return isFinite(v) ? v * mult : null;
  }

  // Standard form: "10k" / "100" / "4.7k"
  m = s.match(/^([\d.]+)\s*([RKMG])?$/i);
  if (m) {
    const num = parseFloat(m[1]);
    if (!isFinite(num)) return null;
    if (m[2]) return num * RES_MULTIPLIER[m[2].toUpperCase()];
    return num;
  }

  return null;
}

function parseCapacitorMagnitude(s: string): number | null {
  // Trailing F is optional; strip it before the rest of parsing.
  const sNoF = s.length > 1 ? s.replace(/[Ff]$/, "") : s;

  // 3-digit code: "104" = 100nF (AB × 10^N pF)
  if (/^\d{3}$/.test(sNoF)) {
    const ab = parseInt(sNoF.slice(0, 2), 10);
    const n = parseInt(sNoF[2], 10);
    return ab * Math.pow(10, n) * 1e-12;
  }

  // u-prefix decimal: "u47" = 0.47uF
  let m = sNoF.match(/^([pnumPNUM])(\d+)$/);
  if (m) {
    const mult = CAP_MULTIPLIER[m[1].toLowerCase()];
    const v = parseFloat(`0.${m[2]}`);
    return isFinite(v) ? v * mult : null;
  }

  // Letter-as-decimal-point: "4u7" = 4.7uF
  m = sNoF.match(/^(\d+)([pnumPNUM])(\d+)$/);
  if (m) {
    const mult = CAP_MULTIPLIER[m[2].toLowerCase()];
    const v = parseFloat(`${m[1]}.${m[3]}`);
    return isFinite(v) ? v * mult : null;
  }

  // Standard form: "100n" / "10u" / "47p" / bare number
  m = sNoF.match(/^([\d.]+)\s*([pnumPNUM])?$/);
  if (m) {
    const num = parseFloat(m[1]);
    if (!isFinite(num)) return null;
    if (m[2]) return num * CAP_MULTIPLIER[m[2].toLowerCase()];
    return num;
  }

  return null;
}

/**
 * Parse a passive value to a numeric magnitude in base units (ohms or
 * farads). Returns null for IC/transistor/diode part numbers, empty input,
 * or anything that doesn't match a known form.
 */
export function valueMagnitude(raw: string, kind: ComponentKind): number | null {
  if (!raw || kind === "ic" || kind === "transistor" || kind === "diode") {
    return null;
  }
  const s = stripMicro(raw.trim());
  if (!s) return null;
  if (kind === "resistor") return parseResistorMagnitude(s);
  if (kind === "film-cap" || kind === "electrolytic") {
    return parseCapacitorMagnitude(s);
  }
  return null;
}

function formatEngineering(mag: number, kind: ComponentKind): string {
  if (mag === 0) return "0";
  const prefixes: [number, string][] =
    kind === "resistor"
      ? [
          [1e9, "G"],
          [1e6, "M"],
          [1e3, "k"],
          [1, ""],
        ]
      : [
          [1, "F"],
          [1e-3, "m"],
          [1e-6, "u"],
          [1e-9, "n"],
          [1e-12, "p"],
        ];
  for (const [div, prefix] of prefixes) {
    if (Math.abs(mag) >= div) {
      const val = mag / div;
      // %g-equivalent: trim trailing zeros, max 6 sig figs.
      const formatted = parseFloat(val.toPrecision(6)).toString();
      return `${formatted}${prefix}`;
    }
  }
  return parseFloat(mag.toPrecision(6)).toString();
}

const UNIT_NOISE_RE =
  /(?:[\d/.]+\s*)?(ohm|ohms|Ω|watt|watts|w|volts|volt|v|tolerance|tol)\s*[\d/.]*/gi;
const WS_RE = /\s+/g;

/**
 * Mirror of backend `normalize_value`. For passives, parses to a numeric
 * magnitude and re-renders in canonical engineering form so equivalent
 * inputs ("4K7", "4700", "4.7k") all produce the same key.
 */
export function normalizeValue(raw: string, kind: ComponentKind): string {
  if (!raw) return "";
  const v = stripMicro(raw.trim());
  if (kind === "ic" || kind === "transistor" || kind === "diode") {
    return v.toUpperCase().replace(WS_RE, "");
  }
  // Pots and switches store free-form descriptors (B25K, SPDT (On/Off/On)).
  // Skip the unit-noise stripper so W-taper pots and any V/W-bearing switch
  // descriptions don't lose meaningful characters. See
  // pedal_bench/core/inventory_index.py for the matching backend logic.
  if (kind === "pot" || kind === "switch") {
    return v.toLowerCase().replace(WS_RE, "");
  }
  let cleaned = v.replace(UNIT_NOISE_RE, "").trim().replace(WS_RE, "");
  if (kind === "resistor") cleaned = stripResistorTolerance(cleaned);
  const mag = valueMagnitude(cleaned, kind);
  if (mag !== null) return formatEngineering(mag, kind);
  return cleaned.toLowerCase();
}
