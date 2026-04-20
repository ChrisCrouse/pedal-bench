import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Enclosure, Hole, IconKind } from "@/api/client";
import {
  faceToLayout,
  isOverflowing,
  layoutToFace,
  unfoldedLayout,
  type FaceLayout,
} from "./geometry";
import { ICON_DEFAULT_DIAMETER, paletteFor, renderIconGlyph } from "./icons";
import {
  getGuideForSide,
  snapToGuides,
  type SnapGuides,
} from "./snap";

interface Props {
  enclosure: Enclosure;
  holes: Hole[];
  selectedIdx: number | null;
  onSelect: (idx: number | null) => void;
  onAdd: (hole: Hole) => void;
  onMove: (idx: number, x_mm: number, y_mm: number) => void;
  onChangeDiameter: (idx: number, diameter_mm: number) => void;
  /** Default icon to assign to holes created by click. */
  defaultIcon: IconKind | null;
  /** When enabled, snap guides render and drag/place snap to them. */
  snapEnabled: boolean;
  snapGuides: SnapGuides | null;
}

/**
 * SVG unfolded-enclosure canvas.
 *
 * Interactions:
 * - Click on an empty area of a face → add a new hole (default icon applied).
 * - Click on an existing hole → select it.
 * - Drag a selected hole → reposition with snap if enabled.
 * - Mouse wheel over a hole → adjust diameter (±0.5 mm; Shift ±0.1; Ctrl ±1).
 * - Click background (outside any face) → deselect.
 */
export function EnclosureCanvas({
  enclosure,
  holes,
  selectedIdx,
  onSelect,
  onAdd,
  onMove,
  onChangeDiameter,
  defaultIcon,
  snapEnabled,
  snapGuides,
}: Props) {
  const layout = useMemo(() => unfoldedLayout(enclosure), [enclosure]);
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragIdx, setDragIdx] = useState<number | null>(null);

  const viewBox = `${layout.minX} ${layout.minY} ${
    layout.maxX - layout.minX
  } ${layout.maxY - layout.minY}`;

  const clientToLayout = useCallback(
    (clientX: number, clientY: number): { x: number; y: number } | null => {
      const svg = svgRef.current;
      if (!svg) return null;
      const pt = svg.createSVGPoint();
      pt.x = clientX;
      pt.y = clientY;
      const ctm = svg.getScreenCTM();
      if (!ctm) return null;
      const p = pt.matrixTransform(ctm.inverse());
      return { x: p.x, y: p.y };
    },
    [],
  );

  // Global mousemove/mouseup while dragging.
  useEffect(() => {
    if (dragIdx === null) return;
    const onMove_ = (e: MouseEvent) => {
      const p = clientToLayout(e.clientX, e.clientY);
      if (!p) return;
      const hole = holes[dragIdx];
      if (!hole) return;
      const faceLayout = layout.faces.find((f) => f.side === hole.side);
      if (!faceLayout) return;
      // Use the face the hole is assigned to (preserve side).
      const rawX = p.x - faceLayout.centerX;
      const rawY = -(p.y - faceLayout.centerY); // flip to Tayda convention
      const snapGuide = getGuideForSide(snapGuides, enclosure.key, hole.side);
      const { x_mm, y_mm } = snapToGuides(snapEnabled, snapGuide, rawX, rawY);
      onMove(dragIdx, x_mm, y_mm);
    };
    const onUp = () => setDragIdx(null);
    window.addEventListener("mousemove", onMove_);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove_);
      window.removeEventListener("mouseup", onUp);
    };
  }, [
    dragIdx,
    holes,
    layout,
    clientToLayout,
    onMove,
    snapEnabled,
    snapGuides,
    enclosure.key,
  ]);

  const handleBackgroundClick = (e: React.MouseEvent) => {
    const p = clientToLayout(e.clientX, e.clientY);
    if (!p) return;
    const hit = layoutToFace(layout, p.x, p.y);
    if (!hit) {
      onSelect(null);
      return;
    }
    // Click inside a face → create a new hole at this position.
    const snapGuide = getGuideForSide(snapGuides, enclosure.key, hit.face.side);
    const { x_mm, y_mm } = snapToGuides(
      snapEnabled,
      snapGuide,
      hit.x_mm,
      hit.y_mm,
    );
    const diameter = defaultIcon
      ? ICON_DEFAULT_DIAMETER[defaultIcon]
      : 7.2;
    onAdd({
      side: hit.face.side,
      x_mm,
      y_mm,
      diameter_mm: diameter,
      label: null,
      powder_coat_margin: true,
      icon: defaultIcon,
    });
  };

  const handleHoleMouseDown = (idx: number) => (e: React.MouseEvent) => {
    e.stopPropagation();
    onSelect(idx);
    setDragIdx(idx);
  };

  const handleHoleWheel = (idx: number) => (e: React.WheelEvent) => {
    // Prevent the page from scrolling when wheeling over a hole.
    e.preventDefault();
    e.stopPropagation();
    const step = e.ctrlKey ? 1 : e.shiftKey ? 0.1 : 0.5;
    const delta = e.deltaY < 0 ? +step : -step;
    const hole = holes[idx];
    if (!hole) return;
    const next = Math.max(0.5, Math.round((hole.diameter_mm + delta) * 10) / 10);
    onChangeDiameter(idx, next);
  };

  return (
    <div className="relative h-full w-full">
      <svg
        ref={svgRef}
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        className="h-full w-full select-none"
        onMouseDown={handleBackgroundClick}
        onWheelCapture={(e) => {
          if ((e.target as SVGElement).tagName === "circle") e.preventDefault();
        }}
      >
        <defs>
          <pattern
            id="face-grid"
            width="10"
            height="10"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 10 0 L 0 0 0 10"
              fill="none"
              stroke="currentColor"
              strokeWidth="0.2"
              className="text-zinc-300 dark:text-zinc-700"
              opacity="0.6"
            />
          </pattern>
        </defs>

        {layout.faces.map((f) => (
          <FaceRect key={f.side} face={f} />
        ))}

        {/* Snap guides (face-local) rendered behind holes */}
        {snapEnabled &&
          layout.faces.map((f) => {
            const guide = getGuideForSide(snapGuides, enclosure.key, f.side);
            if (!guide) return null;
            return (
              <SnapGuideOverlay
                key={`snap-${f.side}`}
                face={f}
                guide={guide}
              />
            );
          })}

        {holes.map((h, idx) => {
          const faceLayout = layout.faces.find((f) => f.side === h.side);
          if (!faceLayout) return null;
          const { x, y } = faceToLayout(faceLayout, h.x_mm, h.y_mm);
          const overflow = isOverflowing(faceLayout.dims, h.x_mm, h.y_mm, h.diameter_mm);
          const isSelected = idx === selectedIdx;
          return (
            <HoleGlyph
              key={idx}
              hole={h}
              x={x}
              y={y}
              isSelected={isSelected}
              isOverflowing={overflow}
              onMouseDown={handleHoleMouseDown(idx)}
              onWheel={handleHoleWheel(idx)}
            />
          );
        })}
      </svg>

      {/* Legend */}
      <div className="absolute bottom-3 right-3 rounded-md border border-zinc-200 bg-white/90 px-3 py-2 text-xs shadow-sm backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/90">
        <div className="font-semibold">Keyboard</div>
        <div className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-zinc-600 dark:text-zinc-400">
          <span className="font-mono">click</span> <span>add hole on a face</span>
          <span className="font-mono">drag</span> <span>reposition hole</span>
          <span className="font-mono">wheel</span> <span>diameter (shift=0.1, ctrl=1)</span>
          <span className="font-mono">↑↓←→</span> <span>nudge 1 mm (shift=0.1)</span>
          <span className="font-mono">del</span> <span>remove selected</span>
        </div>
      </div>
    </div>
  );
}

function FaceRect({ face }: { face: FaceLayout }) {
  const x = face.centerX - face.dims.width_mm / 2;
  const y = face.centerY - face.dims.height_mm / 2;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={face.dims.width_mm}
        height={face.dims.height_mm}
        fill="url(#face-grid)"
        stroke="currentColor"
        strokeWidth="0.4"
        className="pointer-events-auto fill-zinc-100 text-zinc-500 dark:fill-zinc-800/60 dark:text-zinc-600"
      />
      <text
        x={x + 2}
        y={y + 4}
        className="pointer-events-none fill-zinc-500"
        style={{ fontSize: 3.5, fontFamily: "Segoe UI, sans-serif" }}
      >
        {face.side} · {face.dims.label}
      </text>
      {/* Center crosshair */}
      <line
        x1={face.centerX - 2}
        y1={face.centerY}
        x2={face.centerX + 2}
        y2={face.centerY}
        stroke="currentColor"
        strokeWidth="0.15"
        className="text-zinc-400"
      />
      <line
        x1={face.centerX}
        y1={face.centerY - 2}
        x2={face.centerX}
        y2={face.centerY + 2}
        stroke="currentColor"
        strokeWidth="0.15"
        className="text-zinc-400"
      />
    </g>
  );
}

function SnapGuideOverlay({
  face,
  guide,
}: {
  face: FaceLayout;
  guide: { vertical_lines_mm: number[]; horizontal_lines_mm: number[] };
}) {
  const left = face.centerX - face.dims.width_mm / 2;
  const right = face.centerX + face.dims.width_mm / 2;
  const top = face.centerY - face.dims.height_mm / 2;
  const bottom = face.centerY + face.dims.height_mm / 2;
  return (
    <g>
      {guide.vertical_lines_mm.map((xOffset, i) => {
        const x = face.centerX + xOffset; // vertical line at face_center_x + offset
        if (x <= left || x >= right) return null;
        return (
          <line
            key={`v-${i}`}
            x1={x}
            y1={top}
            x2={x}
            y2={bottom}
            stroke="#10b981"
            strokeWidth="0.15"
            strokeDasharray="0.6 0.8"
            opacity={xOffset === 0 ? 0.55 : 0.35}
          />
        );
      })}
      {guide.horizontal_lines_mm.map((yOffset, i) => {
        // Tayda Y+ is up; SVG Y+ is down. So layout_y = face_center_y - yOffset.
        const y = face.centerY - yOffset;
        if (y <= top || y >= bottom) return null;
        return (
          <line
            key={`h-${i}`}
            x1={left}
            y1={y}
            x2={right}
            y2={y}
            stroke="#10b981"
            strokeWidth="0.15"
            strokeDasharray="0.6 0.8"
            opacity={yOffset === 0 ? 0.55 : 0.35}
          />
        );
      })}
    </g>
  );
}

function HoleGlyph({
  hole,
  x,
  y,
  isSelected,
  isOverflowing,
  onMouseDown,
  onWheel,
}: {
  hole: Hole;
  x: number;
  y: number;
  isSelected: boolean;
  isOverflowing: boolean;
  onMouseDown: (e: React.MouseEvent) => void;
  onWheel: (e: React.WheelEvent) => void;
}) {
  const palette = paletteFor(hole.icon);
  const fillColor = isOverflowing
    ? "rgba(239,68,68,0.7)"
    : isSelected
      ? "rgba(16,185,129,0.75)"
      : palette.fill + "b8"; // append alpha ~72%
  const strokeColor = isOverflowing
    ? "#991b1b"
    : isSelected
      ? "#065f46"
      : palette.stroke;

  return (
    <g>
      {isSelected && (
        <>
          <line
            x1={x - hole.diameter_mm / 2 - 2}
            y1={y}
            x2={x + hole.diameter_mm / 2 + 2}
            y2={y}
            stroke="#10b981"
            strokeWidth="0.4"
            strokeDasharray="1 1"
          />
          <line
            x1={x}
            y1={y - hole.diameter_mm / 2 - 2}
            x2={x}
            y2={y + hole.diameter_mm / 2 + 2}
            stroke="#10b981"
            strokeWidth="0.4"
            strokeDasharray="1 1"
          />
        </>
      )}
      <circle
        cx={x}
        cy={y}
        r={hole.diameter_mm / 2}
        fill={fillColor}
        stroke={strokeColor}
        strokeWidth={0.4}
        className="cursor-grab"
        onMouseDown={onMouseDown}
        onWheel={onWheel}
      />
      {/* Icon glyph (hit-transparent so drag/click still target the circle) */}
      <g
        transform={`translate(${x} ${y})`}
        pointerEvents="none"
      >
        {renderIconGlyph(hole.icon ?? null, hole.diameter_mm, isSelected)}
      </g>
      {hole.label && (
        <text
          x={x}
          y={y + hole.diameter_mm / 2 + 3.5}
          textAnchor="middle"
          className="pointer-events-none fill-zinc-700 dark:fill-zinc-300"
          style={{ fontSize: 3, fontFamily: "Segoe UI, sans-serif" }}
        >
          {hole.label}
        </text>
      )}
    </g>
  );
}
