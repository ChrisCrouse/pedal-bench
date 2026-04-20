/**
 * Snap-to-guide engine for the drill designer.
 *
 * The backend ships per-enclosure snap-guide sets (vertical/horizontal
 * lines in mm, face-local). When snapping is enabled, drag/place
 * operations round the hole position to the nearest guide line — but
 * only if the nearest line is within a tolerance of the raw position.
 * Otherwise the raw position is used, with a fallback to 0.1 mm precision.
 */

import type { Side } from "@/api/client";

export interface SnapGuide {
  vertical_lines_mm: number[];
  horizontal_lines_mm: number[];
}

export type SnapGuides = Record<string, Record<string, SnapGuide>>;

/** Within this many mm of a guide line, snap to it. */
export const SNAP_TOLERANCE_MM = 2.0;

/** Round mm value to 0.1 mm precision as the default (no-snap) quantum. */
export function snapTenth(v: number): number {
  return Math.round(v * 10) / 10;
}

/**
 * Snap a face-local coordinate pair to the nearest guide, if any is within
 * tolerance. Axes are independent — X may snap, Y may not, and vice versa.
 */
export function snapToGuides(
  enabled: boolean,
  guides: SnapGuide | null | undefined,
  x_mm: number,
  y_mm: number,
): { x_mm: number; y_mm: number; snappedX: number | null; snappedY: number | null } {
  if (!enabled || !guides) {
    return {
      x_mm: snapTenth(x_mm),
      y_mm: snapTenth(y_mm),
      snappedX: null,
      snappedY: null,
    };
  }
  const sx = nearestWithin(guides.vertical_lines_mm, x_mm, SNAP_TOLERANCE_MM);
  const sy = nearestWithin(guides.horizontal_lines_mm, y_mm, SNAP_TOLERANCE_MM);
  return {
    x_mm: sx === null ? snapTenth(x_mm) : sx,
    y_mm: sy === null ? snapTenth(y_mm) : sy,
    snappedX: sx,
    snappedY: sy,
  };
}

function nearestWithin(values: number[], target: number, tolerance: number): number | null {
  let best: number | null = null;
  let bestDist = tolerance;
  for (const v of values) {
    const d = Math.abs(v - target);
    if (d <= bestDist) {
      best = v;
      bestDist = d;
    }
  }
  return best;
}

export function getGuideForSide(
  guides: SnapGuides | null | undefined,
  enclosureKey: string,
  side: Side,
): SnapGuide | null {
  if (!guides) return null;
  const forEncl = guides[enclosureKey];
  if (!forEncl) return null;
  return forEncl[side] ?? null;
}
