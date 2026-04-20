/**
 * Mirror utilities for drill-designer holes.
 *
 * Three mirror kinds:
 *   x      flip across the face's vertical centerline (x → -x)
 *   y      flip across the face's horizontal centerline (y → -y)
 *   ce     duplicate between sides C and E (swap side + flip x, so the
 *          hole ends up physically symmetric on the enclosure)
 *
 * Usage modes:
 *   one-off placement-aid — apply one mirror to the selected hole now
 *   live placement-aid    — when a mirror is TOGGLED ON, placing a new
 *                           hole spawns a mirror_group of linked twins.
 *                           Dragging any member of the group updates the
 *                           others in real time (DrillTab handles the drag).
 *
 * Each group member carries mirror_{x,y,ce}_flipped flags describing the
 * member's position relative to the group's canonical seed. The flags are
 * used to propagate drags: when one member moves, every other member's
 * new position is computed by composing their flags against the moved
 * member's flags (XOR semantics).
 */

import type { Hole, Side } from "@/api/client";

export type MirrorMode = "x" | "y" | "ce";

export interface MirrorState {
  x: boolean;
  y: boolean;
  ce: boolean;
}

export const NO_MIRROR: MirrorState = { x: false, y: false, ce: false };

/** Does CE-mirror apply on this side? (only C and E sides support it.) */
export function canMirrorCE(side: Side): boolean {
  return side === "C" || side === "E";
}

/** One-off: apply a single mirror to a hole (no group linkage). */
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
  return { ...hole, x_mm: -hole.x_mm };
}

/**
 * Generate a group of linked holes from a seed, given the user's current
 * placement-aid state. Returns ALL members (seed + twins). Each member
 * gets the same mirror_group id and per-member flags describing its
 * relationship to the seed.
 *
 * If no placement aids are active, returns [seed] with no linkage.
 */
export function createMirrorGroup(seed: Hole, state: MirrorState): Hole[] {
  const wantX = state.x;
  const wantY = state.y;
  const wantCE = state.ce && canMirrorCE(seed.side);

  if (!wantX && !wantY && !wantCE) {
    return [{ ...seed, mirror_group: null }];
  }

  const groupId = newGroupId();
  const members: Hole[] = [];
  const seen = new Set<string>(); // positional dedupe key

  const combos: Array<[boolean, boolean, boolean]> = [[false, false, false]];
  if (wantX) combos.push(...combos.map(([x, y, c]) => [!x, y, c] as [boolean, boolean, boolean]));
  if (wantY) combos.push(...combos.map(([x, y, c]) => [x, !y, c] as [boolean, boolean, boolean]));
  if (wantCE) combos.push(...combos.map(([x, y, c]) => [x, y, !c] as [boolean, boolean, boolean]));

  for (const [xf, yf, cf] of combos) {
    const pos = applyFlags(seed, xf, yf, cf);
    const key = `${pos.side}:${pos.x_mm.toFixed(3)}:${pos.y_mm.toFixed(3)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    members.push({
      ...seed,
      side: pos.side,
      x_mm: pos.x_mm,
      y_mm: pos.y_mm,
      mirror_group: groupId,
      mirror_x_flipped: xf,
      mirror_y_flipped: yf,
      mirror_ce_flipped: cf,
    });
  }
  return members;
}

/**
 * When hole `moved` is dragged to a new position, compute the updated
 * positions of every other hole in its mirror group. Returns a new list
 * where linked twins have been repositioned to stay symmetric.
 */
export function propagateDrag(
  holes: Hole[],
  movedIndex: number,
): Hole[] {
  const moved = holes[movedIndex];
  if (!moved?.mirror_group) return holes;

  return holes.map((h, i) => {
    if (i === movedIndex) return h;
    if (h.mirror_group !== moved.mirror_group) return h;
    // Relative flags between this hole and the moved one (XOR).
    const relX = Boolean(h.mirror_x_flipped) !== Boolean(moved.mirror_x_flipped);
    const relY = Boolean(h.mirror_y_flipped) !== Boolean(moved.mirror_y_flipped);
    const relCE = Boolean(h.mirror_ce_flipped) !== Boolean(moved.mirror_ce_flipped);
    const { side, x_mm, y_mm } = applyFlags(moved, relX, relY, relCE);
    return { ...h, side, x_mm, y_mm };
  });
}

/**
 * Given that `patched` is a non-positional edit of the hole at index
 * movedIndex (e.g., changing its diameter / icon / label), push the same
 * property changes to the linked twins so the group stays coherent.
 */
export function propagateNonPositional(
  holes: Hole[],
  movedIndex: number,
  patch: Partial<Hole>,
): Hole[] {
  const moved = holes[movedIndex];
  if (!moved?.mirror_group) return holes;
  // We only propagate diameter / icon / label / powder_coat_margin.
  // Positional fields are handled by propagateDrag. Per-hole mirror
  // flags must never cross over.
  const propagated: Partial<Hole> = {};
  if ("diameter_mm" in patch) propagated.diameter_mm = patch.diameter_mm;
  if ("icon" in patch) propagated.icon = patch.icon;
  if ("label" in patch) propagated.label = patch.label;
  if ("powder_coat_margin" in patch)
    propagated.powder_coat_margin = patch.powder_coat_margin;
  if (Object.keys(propagated).length === 0) return holes;

  return holes.map((h, i) => {
    if (i === movedIndex) return h;
    if (h.mirror_group !== moved.mirror_group) return h;
    return { ...h, ...propagated };
  });
}

/**
 * Clean up mirror groups after a deletion: if a group ends up with only
 * one member, drop its mirror_group (no linkage is needed for a singleton).
 */
export function pruneSingletonGroups(holes: Hole[]): Hole[] {
  const counts: Record<string, number> = {};
  for (const h of holes) {
    if (h.mirror_group) counts[h.mirror_group] = (counts[h.mirror_group] ?? 0) + 1;
  }
  return holes.map((h) =>
    h.mirror_group && counts[h.mirror_group] < 2
      ? { ...h, mirror_group: null, mirror_x_flipped: false, mirror_y_flipped: false, mirror_ce_flipped: false }
      : h,
  );
}

function applyFlags(
  seed: Pick<Hole, "side" | "x_mm" | "y_mm">,
  xFlipped: boolean,
  yFlipped: boolean,
  ceFlipped: boolean,
): { side: Side; x_mm: number; y_mm: number } {
  let side = seed.side;
  let x = seed.x_mm;
  let y = seed.y_mm;
  if (xFlipped) x = -x;
  if (yFlipped) y = -y;
  if (ceFlipped) {
    if (side === "C") {
      side = "E";
      x = -x;
    } else if (side === "E") {
      side = "C";
      x = -x;
    }
  }
  return { side, x_mm: round1(x), y_mm: round1(y) };
}

function round1(v: number) {
  return Math.round(v * 10) / 10;
}

function newGroupId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback for older browsers / SSR:
  return "mg-" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}
