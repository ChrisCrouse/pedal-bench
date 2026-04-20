import { useCallback, useRef, useState } from "react";
import type { BOMItem } from "@/api/client";
import { KIND_COLORS, classifyComponent } from "./componentColors";

interface Props {
  imageUrl: string;
  bom: BOMItem[];
  refdesMap: Record<string, [number, number]>;
  highlightLocation: string | null;
  tagMode: string | null; // refdes currently being tagged
  onTag: (refdes: string, x_pct: number, y_pct: number) => void;
  onHoverLocation: (location: string | null) => void;
  onSelectLocation: (location: string) => void;
}

/**
 * PCB-layout image with per-refdes overlay dots.
 *
 * Click-to-tag workflow:
 *   1. User picks a BOM row (tagMode = the row's location)
 *   2. Image cursor becomes a crosshair; click anywhere on the image
 *   3. onTag fires with normalized (x_pct, y_pct); mode clears
 *
 * Otherwise: hovering a dot surfaces its BOM row via onHoverLocation,
 * and hovering a BOM row in the table highlights its dot here (the
 * parent component drives `highlightLocation`).
 */
export function PcbLayoutViewer({
  imageUrl,
  bom,
  refdesMap,
  highlightLocation,
  tagMode,
  onTag,
  onHoverLocation,
  onSelectLocation,
}: Props) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const handleClick = useCallback(
    (e: React.MouseEvent<SVGElement>) => {
      if (!tagMode) return;
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      const y = (e.clientY - rect.top) / rect.height;
      if (x < 0 || x > 1 || y < 0 || y > 1) return;
      onTag(tagMode, x, y);
    },
    [tagMode, onTag],
  );

  return (
    <div className="relative h-full w-full overflow-hidden bg-zinc-100 dark:bg-zinc-900">
      {!loaded && !error && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-zinc-500">
          Loading PCB layout…
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 px-6 text-center text-sm text-zinc-500">
          <div>No PCB layout available.</div>
          <div className="text-xs">
            Attach a PDF on the Overview tab and the PCB layout page will render here.
          </div>
        </div>
      )}
      <img
        ref={imgRef}
        src={imageUrl}
        alt="PCB layout"
        className={`h-full w-full object-contain ${loaded ? "" : "opacity-0"}`}
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
        draggable={false}
      />
      {loaded && (
        <svg
          ref={svgRef}
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          onClick={handleClick}
          style={{ cursor: tagMode ? "crosshair" : "default" }}
        >
          {Object.entries(refdesMap).map(([refdes, [x, y]]) => {
            const item = bom.find((b) => b.location.toUpperCase() === refdes.toUpperCase());
            const kind = item ? classifyComponent(item) : "other";
            const color = KIND_COLORS[kind];
            const isHighlighted = highlightLocation
              ? refdes.toUpperCase() === highlightLocation.toUpperCase()
              : false;
            return (
              <g key={refdes}>
                {isHighlighted && (
                  <circle
                    cx={x}
                    cy={y}
                    r={0.035}
                    fill="none"
                    stroke={color.fill}
                    strokeWidth={0.005}
                    strokeOpacity={0.8}
                  >
                    <animate
                      attributeName="r"
                      values="0.02;0.05;0.02"
                      dur="1.2s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
                <circle
                  cx={x}
                  cy={y}
                  r={isHighlighted ? 0.014 : 0.009}
                  fill={color.fill}
                  stroke={color.stroke}
                  strokeWidth={0.0015}
                  fillOpacity={0.9}
                  className="cursor-pointer"
                  onMouseEnter={() => onHoverLocation(refdes)}
                  onMouseLeave={() => onHoverLocation(null)}
                  onClick={(e) => {
                    if (tagMode) return;
                    e.stopPropagation();
                    onSelectLocation(refdes);
                  }}
                />
              </g>
            );
          })}
        </svg>
      )}
      {tagMode && (
        <div className="pointer-events-none absolute left-2 top-2 rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white shadow-md">
          Click to place <span className="font-mono">{tagMode}</span>
        </div>
      )}
      {loaded && !error && Object.keys(refdesMap).length === 0 && !tagMode && (
        <div className="pointer-events-none absolute bottom-2 right-2 max-w-xs rounded-md bg-white/90 px-3 py-2 text-xs text-zinc-700 shadow-md backdrop-blur dark:bg-zinc-900/90 dark:text-zinc-300">
          Click a <b>tag</b> button on any BOM row to place it on this PCB image.
          Tagged positions persist with the project.
        </div>
      )}
    </div>
  );
}
