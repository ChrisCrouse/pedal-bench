import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Enclosure, Hole } from "@/api/client";
import {
  faceToLayout,
  isOverflowing,
  layoutToFace,
  snapTenth,
  unfoldedLayout,
  type FaceLayout,
} from "./geometry";

interface Props {
  enclosure: Enclosure;
  holes: Hole[];
  selectedIdx: number | null;
  onSelect: (idx: number | null) => void;
  onAdd: (hole: Hole) => void;
  onMove: (idx: number, x_mm: number, y_mm: number) => void;
  onChangeDiameter: (idx: number, diameter_mm: number) => void;
}

/**
 * SVG unfolded-enclosure canvas.
 *
 * Interactions:
 * - Click on an empty area of a face → add a new hole there.
 * - Click on an existing hole → select it.
 * - Drag a selected hole → reposition it, snapping to 0.1 mm.
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
      const localX = snapTenth(p.x - faceLayout.centerX);
      const localY = snapTenth(-(p.y - faceLayout.centerY));
      onMove(dragIdx, localX, localY);
    };
    const onUp = () => setDragIdx(null);
    window.addEventListener("mousemove", onMove_);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove_);
      window.removeEventListener("mouseup", onUp);
    };
  }, [dragIdx, holes, layout, clientToLayout, onMove]);

  const handleBackgroundClick = (e: React.MouseEvent) => {
    const p = clientToLayout(e.clientX, e.clientY);
    if (!p) return;
    const hit = layoutToFace(layout, p.x, p.y);
    if (!hit) {
      onSelect(null);
      return;
    }
    // Click inside a face → create a new hole at this position.
    onAdd({
      side: hit.face.side,
      x_mm: snapTenth(hit.x_mm),
      y_mm: snapTenth(hit.y_mm),
      diameter_mm: 7.2,
      label: null,
      powder_coat_margin: true,
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
    const next = Math.max(0.5, snapTenth(hole.diameter_mm + delta));
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
        // Disable wheel passive listener on SVG root via onWheel directly
        onWheelCapture={(e) => {
          // Only stop propagation; let individual hole handlers deal with it.
          // If we wheel outside a hole, allow page scroll.
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

        {holes.map((h, idx) => {
          const faceLayout = layout.faces.find((f) => f.side === h.side);
          if (!faceLayout) return null;
          const { x, y } = faceToLayout(faceLayout, h.x_mm, h.y_mm);
          const overflow = isOverflowing(faceLayout.dims, h.x_mm, h.y_mm, h.diameter_mm);
          const isSelected = idx === selectedIdx;
          return (
            <g key={idx}>
              {/* Target crosshair on selected hole for precise placement feel */}
              {isSelected && (
                <>
                  <line
                    x1={x - h.diameter_mm / 2 - 2}
                    y1={y}
                    x2={x + h.diameter_mm / 2 + 2}
                    y2={y}
                    stroke="#10b981"
                    strokeWidth="0.4"
                    strokeDasharray="1 1"
                  />
                  <line
                    x1={x}
                    y1={y - h.diameter_mm / 2 - 2}
                    x2={x}
                    y2={y + h.diameter_mm / 2 + 2}
                    stroke="#10b981"
                    strokeWidth="0.4"
                    strokeDasharray="1 1"
                  />
                </>
              )}
              <circle
                cx={x}
                cy={y}
                r={h.diameter_mm / 2}
                className={[
                  "cursor-grab",
                  overflow
                    ? "fill-red-500/70 stroke-red-700"
                    : isSelected
                      ? "fill-emerald-500/70 stroke-emerald-700"
                      : "fill-blue-500/70 stroke-blue-700",
                ].join(" ")}
                strokeWidth="0.4"
                onMouseDown={handleHoleMouseDown(idx)}
                onWheel={handleHoleWheel(idx)}
              />
              {h.label && (
                <text
                  x={x}
                  y={y + h.diameter_mm / 2 + 3.5}
                  textAnchor="middle"
                  className="pointer-events-none fill-zinc-700 dark:fill-zinc-300"
                  style={{ fontSize: 3, fontFamily: "Segoe UI, sans-serif" }}
                >
                  {h.label}
                </text>
              )}
            </g>
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
