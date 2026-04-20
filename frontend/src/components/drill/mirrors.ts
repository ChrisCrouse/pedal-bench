/**
 * Mirror utilities for drill-designer holes.
 *
 * Three mirror kinds:
 *   mirror-x      flip a hole's x across the face's vertical centerline
 *   mirror-y      flip a hole's y across the face's horizontal centerline
 *   mirror-ce     duplicate a hole on side C to side E (or vice versa),
 *                 flipping x so the hole ends up symmetric on the
 *                 physical enclosure (Tayda: each side has its own x+ axis
 *                 pointing right when viewed head-on, so C+10 maps to E-10
 *                 to stay on the same "front" of the box).
 *
 * Each can be used as:
 *   one-off  — applied to a currently-selected hole
 *   aid      — toggled on, so placing a new hole also creates its mirror
 *
 * Mirror combinations: when multiple modes are on, we produce the full
 * set of mirrored positions. For example, mirror-x + mirror-y on face A
 * creates 4 holes in a symmetric quadrant pattern.
 */

import type { Hole, Side } from "@/api/client";

export type MirrorMode = "x" | "y" | "ce";

export interface MirrorState {
  x: boolean;
  y: boolean;
  ce: boolean;
}

export const NO_MIRROR: MirrorState = { x: false, y: false, ce: false };

/** Apply one mirror to a single hole, returning the mirrored twin. */
export function mirrorHole(hole: Hole, mode: MirrorMode): Hole {
  switch (mode) {
    case "x":
      return { ...hole, x_mm: -hole.x_mm };
    case "y":
      return { ...hole, y_mm: -hole.y_mm };
    case "ce":
      return mirrorAcrossCE(hole);
  }
}

function mirrorAcrossCE(hole: Hole): Hole {
  if (hole.side === "C") return { ...hole, side: "E", x_mm: -hole.x_mm };
  if (hole.side === "E") return { ...hole, side: "C", x_mm: -hole.x_mm };
  // Non-C/E holes mirror x on the same side as a best-effort fallback.
  return { ...hole, x_mm: -hole.x_mm };
}

/**
 * Generate the full set of mirrored twins for a seed hole under a given
 * mirror state. Returns ONLY the additional twins (seed not included).
 * Deduplicates holes that land at the same (side, x, y).
 */
export function generateMirrorTwins(seed: Hole, state: MirrorState): Hole[] {
  // Start with the seed; at each enabled mirror, fold existing holes
  // across that axis. This produces {seed}, {seed, mx}, {seed, mx, my, mx+my}, etc.
  let set: Hole[] = [seed];
  if (state.x) set = dedupe([...set, ...set.map((h) => mirrorHole(h, "x"))]);
  if (state.y) set = dedupe([...set, ...set.map((h) => mirrorHole(h, "y"))]);
  if (state.ce && (seed.side === "C" || seed.side === "E")) {
    set = dedupe([...set, ...set.map((h) => mirrorHole(h, "ce"))]);
  }
  // Drop the seed — caller appends it separately.
  return set.filter((h) => !sameSpot(h, seed));
}

function sameSpot(a: Hole, b: Hole): boolean {
  return (
    a.side === b.side &&
    Math.abs(a.x_mm - b.x_mm) < 1e-3 &&
    Math.abs(a.y_mm - b.y_mm) < 1e-3
  );
}

function dedupe(holes: Hole[]): Hole[] {
  const out: Hole[] = [];
  for (const h of holes) {
    if (!out.some((existing) => sameSpot(existing, h))) out.push(h);
  }
  return out;
}

/** Does CE-mirror apply on this side? (only C and E sides support it.) */
export function canMirrorCE(side: Side): boolean {
  return side === "C" || side === "E";
}
