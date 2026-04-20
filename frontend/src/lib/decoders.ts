/**
 * Resistor and capacitor value parsers / formatters / color-code converters.
 *
 * Ported from backend/pedal_bench/core/decoders.py — kept locally in TS
 * so the bench-side decoder panel has zero latency. Behavior must match
 * the Python version (which is covered by pytest).
 */

// ---- Resistor text <-> ohms ------------------------------------------

const R_UNITS: Record<string, number> = { R: 1, K: 1e3, M: 1e6 };
const R_EMBEDDED = /^(\d+)([RKM])(\d+)$/;
const R_PLAIN = /^(\d+(?:\.\d+)?)([RKM]?)$/;

export function parseResistor(text: string): number {
  const t = text
    .trim()
    .toUpperCase()
    .replace(/Ω/g, "")
    .replace(/OHMS?/g, "")
    .replace(/\s+/g, "");
  if (!t) throw new Error("Empty resistor value");

  const m1 = R_EMBEDDED.exec(t);
  if (m1) {
    const mantissa = parseFloat(`${m1[1]}.${m1[3]}`);
    return mantissa * R_UNITS[m1[2]];
  }
  const m2 = R_PLAIN.exec(t);
  if (m2) {
    const mantissa = parseFloat(m2[1]);
    const unit = m2[2] || "R";
    return mantissa * R_UNITS[unit];
  }
  throw new Error(`Cannot parse resistor value "${text}"`);
}

export function resistorToText(ohms: number): string {
  if (ohms <= 0) throw new Error(`ohms must be > 0, got ${ohms}`);
  if (ohms < 1_000) return formatUnit(ohms, "R");
  if (ohms < 1_000_000) return formatUnit(ohms / 1_000, "K");
  return formatUnit(ohms / 1_000_000, "M");
}

export function resistorDisplay(ohms: number): string {
  if (ohms < 1_000) return `${g(ohms)} Ω`;
  if (ohms < 1_000_000) return `${g(ohms / 1_000)} kΩ`;
  return `${g(ohms / 1_000_000)} MΩ`;
}

// ---- Capacitor text <-> farads ---------------------------------------

const C_UNITS: Record<string, number> = { P: 1e-12, N: 1e-9, U: 1e-6 };
const C_EMBEDDED = /^(\d+)([PNU])(\d+)$/;
const C_PLAIN = /^(\d+(?:\.\d+)?)([PNU])$/;

export function parseCapacitor(text: string): number {
  let t = text
    .trim()
    .toUpperCase()
    .replace(/µ/g, "U")
    .replace(/Μ/g, "U")
    .replace(/\s+/g, "");
  if (t.endsWith("FD")) t = t.slice(0, -2);
  else if (t.endsWith("F")) t = t.slice(0, -1);
  if (!t) throw new Error("Empty capacitor value");

  const m1 = C_EMBEDDED.exec(t);
  if (m1) {
    const mantissa = parseFloat(`${m1[1]}.${m1[3]}`);
    return mantissa * C_UNITS[m1[2]];
  }
  const m2 = C_PLAIN.exec(t);
  if (m2) return parseFloat(m2[1]) * C_UNITS[m2[2]];
  throw new Error(`Cannot parse capacitor value "${text}"`);
}

export function capacitorToText(farads: number): string {
  if (farads <= 0) throw new Error(`farads must be > 0, got ${farads}`);
  if (farads >= 1e-6) return formatUnit(farads / 1e-6, "u");
  if (farads >= 1e-9) return formatUnit(farads / 1e-9, "n");
  return formatUnit(farads / 1e-12, "p");
}

export function capacitorDisplay(farads: number): string {
  if (farads >= 1e-6) return `${g(farads * 1e6)} µF`;
  if (farads >= 1e-9) return `${g(farads * 1e9)} nF`;
  return `${g(farads * 1e12)} pF`;
}

// ---- Resistor 4-band color bands -------------------------------------

export type BandColor =
  | "black" | "brown" | "red" | "orange" | "yellow"
  | "green" | "blue" | "violet" | "grey" | "white"
  | "gold" | "silver";

const DIGIT_COLORS: BandColor[] = [
  "black", "brown", "red", "orange", "yellow",
  "green", "blue", "violet", "grey", "white",
];
const MULT_EXP_TO_COLOR: Record<number, BandColor> = {
  [-2]: "silver",
  [-1]: "gold",
  0: "black",
  1: "brown",
  2: "red",
  3: "orange",
  4: "yellow",
  5: "green",
  6: "blue",
  7: "violet",
  8: "grey",
  9: "white",
};
const MULT_COLOR_TO_EXP: Record<string, number> = Object.fromEntries(
  Object.entries(MULT_EXP_TO_COLOR).map(([e, c]) => [c, Number(e)]),
);

export const TOLERANCE_BY_COLOR: Record<string, number> = {
  brown: 1, red: 2, gold: 5, silver: 10,
};

export const BAND_HEX: Record<BandColor, string> = {
  black: "#111111",
  brown: "#7a4a1d",
  red: "#d32f2f",
  orange: "#ef6c00",
  yellow: "#fbc02d",
  green: "#388e3c",
  blue: "#1976d2",
  violet: "#7b1fa2",
  grey: "#616161",
  white: "#f5f5f5",
  gold: "#b8860b",
  silver: "#9e9e9e",
};

export const BAND_FG: Record<BandColor, string> = {
  black: "#ffffff",
  brown: "#ffffff",
  red: "#ffffff",
  orange: "#000000",
  yellow: "#000000",
  green: "#ffffff",
  blue: "#ffffff",
  violet: "#ffffff",
  grey: "#ffffff",
  white: "#000000",
  gold: "#000000",
  silver: "#000000",
};

export function resistorToBands(
  ohms: number,
  tolerancePct = 5,
): [BandColor, BandColor, BandColor, BandColor] {
  if (ohms <= 0) throw new Error(`ohms must be > 0, got ${ohms}`);
  let exp = 0;
  let v = ohms;
  while (v >= 100) {
    v /= 10;
    exp += 1;
  }
  while (v < 10) {
    v *= 10;
    exp -= 1;
  }
  let d1 = Math.floor(v / 10);
  let d2 = Math.round(v - d1 * 10);
  if (d2 === 10) {
    d2 = 0;
    d1 += 1;
    if (d1 === 10) {
      d1 = 1;
      exp += 1;
    }
  }
  if (!(exp in MULT_EXP_TO_COLOR)) throw new Error(`out of 4-band range: ${ohms}`);
  const tol =
    (Object.entries(TOLERANCE_BY_COLOR).find(
      ([, t]) => Math.abs(t - tolerancePct) < 0.01,
    )?.[0] as BandColor | undefined) ?? "gold";
  return [DIGIT_COLORS[d1], DIGIT_COLORS[d2], MULT_EXP_TO_COLOR[exp], tol];
}

export function bandsToResistor(bands: BandColor[]): number {
  if (bands.length !== 3 && bands.length !== 4)
    throw new Error(`Expected 3 or 4 bands, got ${bands.length}`);
  const d1 = DIGIT_COLORS.indexOf(bands[0]);
  const d2 = DIGIT_COLORS.indexOf(bands[1]);
  if (d1 < 0 || d2 < 0) throw new Error("Invalid digit band color");
  const exp = MULT_COLOR_TO_EXP[bands[2]];
  if (exp === undefined) throw new Error(`Invalid multiplier color: ${bands[2]}`);
  return (d1 * 10 + d2) * Math.pow(10, exp);
}

// ---- helpers ----------------------------------------------------------

function formatUnit(val: number, unit: string): string {
  // Absorb IEEE-754 scaling noise (e.g., 100e-9 / 1e-9 = 99.9999…).
  const v = Math.round(val * 1e6) / 1e6;
  if (v === Math.floor(v)) return `${Math.floor(v)}${unit}`;
  const whole = Math.floor(v);
  const frac = v - whole;
  const fracStr = frac.toFixed(3).slice(2).replace(/0+$/, "");
  return fracStr ? `${whole}${unit}${fracStr}` : `${whole}${unit}`;
}

function g(x: number): string {
  // Python-style %g: strip trailing zeros, no scientific.
  return parseFloat(x.toPrecision(6)).toString();
}
