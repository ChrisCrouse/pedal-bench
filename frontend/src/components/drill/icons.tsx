/**
 * Icon registry for drill-designer hole markers.
 *
 * Each icon is an SVG fragment rendered INSIDE the physical hole circle
 * so the circle stays at accurate drill-bit size while the inner glyph
 * communicates the part type. Colors are category-consistent (controls
 * blue, LED amber, footswitch red, audio jacks green, DC gray, toggles
 * violet, expression teal) so the layout is scannable at a glance.
 *
 * Coordinates are in **mm** (the canvas viewBox is mm-space).
 */

import type { ReactElement } from "react";
import type { IconKind } from "@/api/client";

export const ICON_KINDS: IconKind[] = [
  "pot",
  "chicken-head",
  "led",
  "footswitch",
  "toggle",
  "jack",
  "dc-jack",
  "expression",
];

export const ICON_LABELS: Record<IconKind, string> = {
  "pot": "Potentiometer",
  "chicken-head": "Chicken-head knob",
  "led": "LED",
  "footswitch": "Footswitch",
  "toggle": "Toggle switch",
  "jack": '1/4" jack',
  "dc-jack": "DC jack",
  "expression": "Expression (TRS)",
};

/** Approximate typical drill diameters for each icon type (mm). */
export const ICON_DEFAULT_DIAMETER: Record<IconKind, number> = {
  "pot": 7.2,
  "chicken-head": 9.5,
  "led": 5.0,
  "footswitch": 12.2,
  "toggle": 6.1,
  "jack": 9.7,
  "dc-jack": 8.1,
  "expression": 9.7,
};

interface Palette {
  fill: string;
  stroke: string;
  accent: string;
  outline: string;
}

const PALETTE: Record<IconKind, Palette> = {
  "pot":          { fill: "#3b82f6", stroke: "#1d4ed8", accent: "#ffffff", outline: "#1e3a8a" },
  "chicken-head": { fill: "#6366f1", stroke: "#4338ca", accent: "#ffffff", outline: "#312e81" },
  "led":          { fill: "#fbbf24", stroke: "#b45309", accent: "#fff7ed", outline: "#78350f" },
  "footswitch":   { fill: "#ef4444", stroke: "#991b1b", accent: "#ffffff", outline: "#7f1d1d" },
  "toggle":       { fill: "#a855f7", stroke: "#6b21a8", accent: "#ffffff", outline: "#581c87" },
  "jack":         { fill: "#10b981", stroke: "#047857", accent: "#ffffff", outline: "#064e3b" },
  "dc-jack":      { fill: "#71717a", stroke: "#3f3f46", accent: "#f4f4f5", outline: "#27272a" },
  "expression":   { fill: "#14b8a6", stroke: "#0f766e", accent: "#ffffff", outline: "#134e4a" },
};

const NEUTRAL: Palette = {
  fill: "#3b82f6",
  stroke: "#1d4ed8",
  accent: "#ffffff",
  outline: "#1e3a8a",
};

export function paletteFor(icon: IconKind | null | undefined): Palette {
  return icon ? PALETTE[icon] : NEUTRAL;
}

/** SVG nodes drawn at the hole center; callers wrap them with the circle. */
export function renderIconGlyph(
  icon: IconKind | null | undefined,
  diameter: number,
  isSelected: boolean,
): ReactElement | null {
  if (!icon) return null;
  const r = diameter / 2;
  const palette = paletteFor(icon);
  const strokeColor = isSelected ? "#065f46" : palette.outline;
  const accent = palette.accent;

  switch (icon) {
    case "pot": {
      // Small inner disc + tick mark pointing up (knob indicator)
      const inner = r * 0.55;
      const tickLen = r * 0.55;
      return (
        <g>
          <circle r={inner} fill={accent} stroke={strokeColor} strokeWidth={0.15} />
          <line
            x1={0}
            y1={-inner * 0.1}
            x2={0}
            y2={-tickLen}
            stroke={strokeColor}
            strokeWidth={0.35}
            strokeLinecap="round"
          />
        </g>
      );
    }
    case "chicken-head": {
      // Triangular pointer
      const tip = r * 0.85;
      const base = r * 0.45;
      return (
        <g>
          <circle r={r * 0.32} fill={accent} stroke={strokeColor} strokeWidth={0.15} />
          <path
            d={`M 0 ${-tip} L ${base} ${base * 0.55} L ${-base} ${base * 0.55} Z`}
            fill={accent}
            stroke={strokeColor}
            strokeWidth={0.2}
          />
        </g>
      );
    }
    case "led": {
      // Bright filled dome + halo
      return (
        <g>
          <circle r={r * 0.95} fill="#fde68a" opacity={0.55} />
          <circle r={r * 0.55} fill={accent} stroke={strokeColor} strokeWidth={0.18} />
          <circle r={r * 0.25} fill="#fef3c7" />
        </g>
      );
    }
    case "footswitch": {
      // Concentric rings + center dot — "big button"
      return (
        <g>
          <circle r={r * 0.75} fill="none" stroke={accent} strokeWidth={0.3} />
          <circle r={r * 0.45} fill={accent} stroke={strokeColor} strokeWidth={0.2} />
          <circle r={r * 0.12} fill={strokeColor} />
        </g>
      );
    }
    case "toggle": {
      // Square lever + bat handle
      const w = r * 0.6;
      const h = r * 0.35;
      return (
        <g>
          <rect x={-w / 2} y={-h / 2} width={w} height={h} fill={accent} stroke={strokeColor} strokeWidth={0.15} rx={0.3} />
          <circle cx={0} cy={-r * 0.55} r={r * 0.18} fill={accent} stroke={strokeColor} strokeWidth={0.15} />
          <line x1={0} y1={-h / 2} x2={0} y2={-r * 0.4} stroke={strokeColor} strokeWidth={0.2} />
        </g>
      );
    }
    case "jack": {
      // TS ring (outer ring + inner ring)
      return (
        <g>
          <circle r={r * 0.78} fill="none" stroke={accent} strokeWidth={0.25} />
          <circle r={r * 0.42} fill={accent} stroke={strokeColor} strokeWidth={0.15} />
        </g>
      );
    }
    case "dc-jack": {
      // Barrel jack — outer circle + smaller inner pin
      return (
        <g>
          <circle r={r * 0.72} fill="none" stroke={accent} strokeWidth={0.22} />
          <circle r={r * 0.22} fill={strokeColor} />
        </g>
      );
    }
    case "expression": {
      // TRS jack — ring + two small dots (tip / ring markers)
      return (
        <g>
          <circle r={r * 0.78} fill="none" stroke={accent} strokeWidth={0.22} />
          <circle r={r * 0.3} fill={accent} stroke={strokeColor} strokeWidth={0.15} />
          <circle cx={r * 0.35} cy={0} r={r * 0.12} fill={strokeColor} />
        </g>
      );
    }
  }
}
