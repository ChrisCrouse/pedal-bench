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
  selectedIndices: number[];
  onSelect: (indices: number[]) => void;
  onAdd: (hole: Hole) => void;
  onMoveMany: (moves: { idx: number; x_mm: number; y_mm: number }[]) => void;
  onChangeDiameter: (idx: number, diameter_mm: number) => void;
  onDragBegin: () => void;
  onDragEnd: () => void;
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
 * - Click on empty face area: add a new hole there (default icon applied).
 * - Click on a hole: single-select.
 * - Shift-click on a hole: toggle in/out of current selection.
 * - Drag a selected hole: move every selected hole in lockstep.
 * - Shift-drag on empty area (anywhere): draw a selection rectangle.
 * - Mouse wheel over a hole: adjust diameter (±0.5 mm; Shift ±0.1; Ctrl ±1).
 * - Click background outside any face: clear selection.
 */
export function EnclosureCanvas({
  enclosure,
  holes,
  selectedIndices,
  onSelect,
  onAdd,
  onMoveMany,
  onChangeDiameter,
  onDragBegin,
  onDragEnd,
  defaultIcon,
  snapEnabled,
  snapGuides,
}: Props) {
  const layout = useMemo(() => unfoldedLayout(enclosure), [enclosure]);
  const svgRef = useRef<SVGSVGElement>(null);
  const selectedSet = useMemo(() => new Set(selectedIndices), [selectedIndices]);

  const [dragging, setDragging] = useState<null | {
    // Index of the hole being dragged; every other selected hole moves
    // relative to this one with the same delta.
    leaderIdx: number;
    // Starting positions per selected index (for incremental delta math).
    start: Map<number, { x_mm: number; y_mm: number }>;
    // Cursor start in layout coords.
    startLayoutX: number;
    startLayoutY: number;
  }>(null);

  const [boxSelect, setBoxSelect] = useState<null | {
    startX: number;
    startY: number;
    curX: number;
    curY: number;
  }>(null);

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

  // Global mousemove / mouseup while dragging or box-selecting.
  useEffect(() => {
    if (!dragging && !boxSelect) return;

    const onMove = (e: MouseEvent) => {
      const p = clientToLayout(e.clientX, e.clientY);
      if (!p) return;

      if (dragging) {
        // Compute delta using the leader hole's drag semantics.
        const leaderFace = layout.faces.find(
          (f) => f.side === holes[dragging.leaderIdx]?.side,
        );
        if (!leaderFace) return;
        const leaderStart = dragging.start.get(dragging.leaderIdx);
        if (!leaderStart) return;
        // Where should the leader land? (snap-aware)
        const rawLeaderX = p.x - leaderFace.centerX;
        const rawLeaderY = -(p.y - leaderFace.centerY);
        const guide = getGuideForSide(snapGuides, enclosure.key, holes[dragging.leaderIdx].side);
        const { x_mm: newLeaderX, y_mm: newLeaderY } = snapToGuides(
          snapEnabled,
          guide,
          rawLeaderX,
          rawLeaderY,
        );
        const dx = newLeaderX - leaderStart.x_mm;
        const dy = newLeaderY - leaderStart.y_mm;

        // Apply delta to every selected hole.
        const moves: { idx: number; x_mm: number; y_mm: number }[] = [];
        for (const [idx, start] of dragging.start.entries()) {
          moves.push({
            idx,
            x_mm: round1(start.x_mm + dx),
            y_mm: round1(start.y_mm + dy),
          });
        }
        onMoveMany(moves);
      } else if (boxSelect) {
        setBoxSelect({ ...boxSelect, curX: p.x, curY: p.y });
      }
    };

    const onUp = () => {
      if (dragging) {
        setDragging(null);
        onDragEnd();
      }
      if (boxSelect) {
        // Commit the box-select: select every hole whose center is inside.
        const { startX, startY, curX, curY } = boxSelect;
        const minX = Math.min(startX, curX);
        const maxX = Math.max(startX, curX);
        const minY = Math.min(startY, curY);
        const maxY = Math.max(startY, curY);
        const hits: number[] = [];
        holes.forEach((h, idx) => {
          const face = layout.faces.find((f) => f.side === h.side);
          if (!face) return;
          const { x, y } = faceToLayout(face, h.x_mm, h.y_mm);
          if (x >= minX && x <= maxX && y >= minY && y <= maxY) hits.push(idx);
        });
        setBoxSelect(null);
        // Meaningfully small drag? Treat as a click — ignore.
        if (Math.abs(curX - startX) < 1 && Math.abs(curY - startY) < 1) return;
        onSelect(hits);
      }
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [
    dragging,
    boxSelect,
    holes,
    layout,
    clientToLayout,
    onMoveMany,
    onSelect,
    onDragEnd,
    snapEnabled,
    snapGuides,
    enclosure.key,
  ]);

  const handleBackgroundMouseDown = (e: React.MouseEvent) => {
    const p = clientToLayout(e.clientX, e.clientY);
    if (!p) return;

    // Shift-drag anywhere: start a box-selection rectangle.
    if (e.shiftKey) {
      setBoxSelect({ startX: p.x, startY: p.y, curX: p.x, curY: p.y });
      onSelect([]);
      return;
    }

    const hit = layoutToFace(layout, p.x, p.y);
    if (!hit) {
      // Clicked outside every face: deselect.
      onSelect([]);
      return;
    }
    // Click inside a face: add a new hole at this position (snap-aware).
    const guide = getGuideForSide(snapGuides, enclosure.key, hit.face.side);
    const { x_mm, y_mm } = snapToGuides(snapEnabled, guide, hit.x_mm, hit.y_mm);
    const diameter = defaultIcon ? ICON_DEFAULT_DIAMETER[defaultIcon] : 7.2;
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
    let nextSelection: number[];
    if (e.shiftKey) {
      // Toggle.
      if (selectedSet.has(idx)) nextSelection = selectedIndices.filter((i) => i !== idx);
      else nextSelection = [...selectedIndices, idx];
    } else if (selectedSet.has(idx) && selectedIndices.length > 1) {
      // Start drag with existing multi-selection intact.
      nextSelection = selectedIndices;
    } else {
      nextSelection = [idx];
    }
    onSelect(nextSelection);

    // If we would be dragging, begin transaction + capture starting positions.
    const dragSet = new Set(nextSelection);
    if (dragSet.size > 0 && !e.shiftKey) {
      onDragBegin();
      const start = new Map<number, { x_mm: number; y_mm: number }>();
      dragSet.forEach((i) => {
        const h = holes[i];
        if (h) start.set(i, { x_mm: h.x_mm, y_mm: h.y_mm });
      });
      const p = clientToLayout(e.clientX, e.clientY) ?? { x: 0, y: 0 };
      setDragging({
        leaderIdx: idx,
        start,
        startLayoutX: p.x,
        startLayoutY: p.y,
      });
    }
  };

  const handleHoleWheel = (idx: number) => (e: React.WheelEvent) => {
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
        onMouseDown={handleBackgroundMouseDown}
        onWheelCapture={(e) => {
          if ((e.target as SVGElement).tagName === "circle") e.preventDefault();
        }}
      >
        <defs>
          <pattern id="face-grid" width="10" height="10" patternUnits="userSpaceOnUse">
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

        {snapEnabled &&
          layout.faces.map((f) => {
            const guide = getGuideForSide(snapGuides, enclosure.key, f.side);
            if (!guide) return null;
            return <SnapGuideOverlay key={`snap-${f.side}`} face={f} guide={guide} />;
          })}

        {holes.map((h, idx) => {
          const faceLayout = layout.faces.find((f) => f.side === h.side);
          if (!faceLayout) return null;
          const { x, y } = faceToLayout(faceLayout, h.x_mm, h.y_mm);
          const overflow = isOverflowing(faceLayout.dims, h.x_mm, h.y_mm, h.diameter_mm);
          const isSelected = selectedSet.has(idx);
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

        {/* Box-select rectangle */}
        {boxSelect && (
          <rect
            x={Math.min(boxSelect.startX, boxSelect.curX)}
            y={Math.min(boxSelect.startY, boxSelect.curY)}
            width={Math.abs(boxSelect.curX - boxSelect.startX)}
            height={Math.abs(boxSelect.curY - boxSelect.startY)}
            fill="rgba(16,185,129,0.10)"
            stroke="#10b981"
            strokeWidth="0.4"
            strokeDasharray="1 1"
            pointerEvents="none"
          />
        )}
      </svg>

      {/* Legend */}
      <div className="absolute bottom-3 right-3 rounded-md border border-zinc-200 bg-white/90 px-3 py-2 text-xs shadow-sm backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/90">
        <div className="font-semibold">Keyboard</div>
        <div className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-zinc-600 dark:text-zinc-400">
          <span className="font-mono">click</span> <span>add hole on a face</span>
          <span className="font-mono">drag</span> <span>reposition selected hole(s)</span>
          <span className="font-mono">shift+drag</span> <span>box-select</span>
          <span className="font-mono">shift+click</span> <span>toggle hole in selection</span>
          <span className="font-mono">wheel</span> <span>diameter (shift=0.1, ctrl=1)</span>
          <span className="font-mono">↑↓←→</span> <span>nudge 1 mm (shift=0.1)</span>
          <span className="font-mono">del</span> <span>remove selected</span>
          <span className="font-mono">ctrl+z / ctrl+shift+z</span> <span>undo / redo</span>
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
        const x = face.centerX + xOffset;
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
      : palette.fill + "b8";
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
      <g transform={`translate(${x} ${y})`} pointerEvents="none">
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

function round1(v: number) {
  return Math.round(v * 10) / 10;
}
