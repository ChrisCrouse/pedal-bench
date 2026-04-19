/**
 * Unfolded-layout geometry for the drill designer.
 *
 * Tayda convention: each face has its own (x_mm, y_mm) coordinates from
 * the center of that face. X+ is right, Y+ is up.
 *
 * SVG convention: X+ is right, Y+ is down. So when we render, we flip Y.
 *
 * The unfolded cross layout puts face A at the center, with B above,
 * D below, C to the left, E to the right. Lid is not drawn (not drilled).
 */

import type { Enclosure, FaceDims, Side } from "@/api/client";

/** Visual gap between adjacent unfolded faces, in mm. */
export const FACE_GAP_MM = 4;

/** Canvas padding around the full layout, in mm. */
export const LAYOUT_PAD_MM = 8;

export interface FaceLayout {
  side: Side;
  dims: FaceDims;
  /** Center of this face in unfolded-layout coordinates (mm). */
  centerX: number;
  centerY: number;
}

export interface UnfoldedLayout {
  faces: FaceLayout[];
  /** Bounding box of the entire layout in mm, including padding. */
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/**
 * Compute the center position of each face in unfolded-layout mm coords.
 * Layout origin (0,0) sits at the center of face A.
 * Positive Y in layout coords means DOWN (same as SVG).
 */
export function unfoldedLayout(encl: Enclosure): UnfoldedLayout {
  const A = encl.faces.A;
  const B = encl.faces.B;
  const C = encl.faces.C;
  const D = encl.faces.D;
  const E = encl.faces.E;

  const faces: FaceLayout[] = [
    { side: "A", dims: A, centerX: 0, centerY: 0 },
    {
      side: "B",
      dims: B,
      centerX: 0,
      centerY: -(A.height_mm / 2 + FACE_GAP_MM + B.height_mm / 2),
    },
    {
      side: "D",
      dims: D,
      centerX: 0,
      centerY: +(A.height_mm / 2 + FACE_GAP_MM + D.height_mm / 2),
    },
    {
      side: "C",
      dims: C,
      centerX: -(A.width_mm / 2 + FACE_GAP_MM + C.width_mm / 2),
      centerY: 0,
    },
    {
      side: "E",
      dims: E,
      centerX: +(A.width_mm / 2 + FACE_GAP_MM + E.width_mm / 2),
      centerY: 0,
    },
  ];

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const f of faces) {
    minX = Math.min(minX, f.centerX - f.dims.width_mm / 2);
    maxX = Math.max(maxX, f.centerX + f.dims.width_mm / 2);
    minY = Math.min(minY, f.centerY - f.dims.height_mm / 2);
    maxY = Math.max(maxY, f.centerY + f.dims.height_mm / 2);
  }
  minX -= LAYOUT_PAD_MM;
  minY -= LAYOUT_PAD_MM;
  maxX += LAYOUT_PAD_MM;
  maxY += LAYOUT_PAD_MM;

  return { faces, minX, minY, maxX, maxY };
}

/**
 * Convert a face-local hole coordinate (Tayda: Y+ up) to an unfolded-layout
 * SVG coordinate (Y+ down).
 */
export function faceToLayout(
  face: FaceLayout,
  x_mm: number,
  y_mm: number,
): { x: number; y: number } {
  return {
    x: face.centerX + x_mm,
    y: face.centerY - y_mm, // flip Y for SVG
  };
}

/**
 * Convert an unfolded-layout SVG coordinate back to a face-local (Tayda)
 * coordinate. Returns null if the point is not inside any face.
 */
export function layoutToFace(
  layout: UnfoldedLayout,
  x: number,
  y: number,
): { face: FaceLayout; x_mm: number; y_mm: number } | null {
  for (const f of layout.faces) {
    const halfW = f.dims.width_mm / 2;
    const halfH = f.dims.height_mm / 2;
    if (
      x >= f.centerX - halfW &&
      x <= f.centerX + halfW &&
      y >= f.centerY - halfH &&
      y <= f.centerY + halfH
    ) {
      return {
        face: f,
        x_mm: x - f.centerX,
        y_mm: -(y - f.centerY), // flip Y back to Tayda convention
      };
    }
  }
  return null;
}

/** Does this hole (center + radius) exceed its face's boundary? */
export function isOverflowing(face: FaceDims, x_mm: number, y_mm: number, diameter_mm: number): boolean {
  const r = diameter_mm / 2;
  const halfW = face.width_mm / 2;
  const halfH = face.height_mm / 2;
  return Math.abs(x_mm) + r > halfW || Math.abs(y_mm) + r > halfH;
}

/** Snap mm value to 0.1 mm precision (avoid float drift during drag). */
export function snapTenth(v: number): number {
  return Math.round(v * 10) / 10;
}
