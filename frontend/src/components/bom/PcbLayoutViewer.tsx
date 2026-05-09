import { useCallback, useEffect, useRef, useState } from "react";
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
  /** Optional: when provided, the empty-state shows a file picker so the user
   *  can attach their own PCB layout image without going through a PDF. */
  onUploadImage?: (file: File) => Promise<void> | void;
  /** Optional: when provided, shown alongside the upload button so the user
   *  can swap a previously-attached custom image. */
  onClearImage?: () => Promise<void> | void;
  /** True when the image currently being shown is a user-uploaded custom one
   *  (vs. a PDF-rendered cache). Drives the "Replace image" affordance. */
  hasCustomImage?: boolean;
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
// Discrete zoom steps. Click + cycles up, click − cycles down.
const ZOOM_STEPS = [1, 1.25, 1.5, 2, 3, 4] as const;

export function PcbLayoutViewer({
  imageUrl,
  bom,
  refdesMap,
  highlightLocation,
  tagMode,
  onTag,
  onHoverLocation,
  onSelectLocation,
  onUploadImage,
  onClearImage,
  hasCustomImage,
}: Props) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [naturalAspect, setNaturalAspect] = useState<number | null>(null);
  // Reset load/error state when the image URL changes (e.g. after a fresh
  // upload bumped a cache-buster). Without this, an `error: true` from a
  // prior 404 sticks even though the new URL would load fine.
  useEffect(() => {
    setLoaded(false);
    setError(false);
  }, [imageUrl]);
  const [zoomIndex, setZoomIndex] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragStartRef = useRef<{
    x: number;
    y: number;
    scrollLeft: number;
    scrollTop: number;
  } | null>(null);
  // Set true during a drag that actually moved; consumed by the click-capture
  // handler so a pan doesn't also fire onSelectLocation on a refdes dot.
  const justDraggedRef = useRef(false);

  const zoom = ZOOM_STEPS[zoomIndex];
  const zoomIn = () =>
    setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1));
  const zoomOut = () => setZoomIndex((i) => Math.max(0, i - 1));
  const zoomReset = () => setZoomIndex(0);

  // Drag-to-pan when zoomed. Disabled at zoom=1 (nothing to scroll) and
  // during tagMode (the user wants to click-place a refdes, not pan).
  const canPan = zoom > 1 && !tagMode;

  const onPanMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!canPan || e.button !== 0) return;
      const el = containerRef.current;
      if (!el) return;
      dragStartRef.current = {
        x: e.clientX,
        y: e.clientY,
        scrollLeft: el.scrollLeft,
        scrollTop: el.scrollTop,
      };
      setIsDragging(true);
      // Prevent text/image selection while dragging.
      e.preventDefault();
    },
    [canPan],
  );

  const onPanMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const start = dragStartRef.current;
      const el = containerRef.current;
      if (!start || !el) return;
      const dx = e.clientX - start.x;
      const dy = e.clientY - start.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) justDraggedRef.current = true;
      el.scrollLeft = start.scrollLeft - dx;
      el.scrollTop = start.scrollTop - dy;
    },
    [],
  );

  const endPan = useCallback(() => {
    if (!dragStartRef.current) return;
    dragStartRef.current = null;
    setIsDragging(false);
    if (justDraggedRef.current) {
      // Clear on next tick so the upcoming click event (same tick) sees the
      // flag and gets suppressed in capture phase.
      setTimeout(() => {
        justDraggedRef.current = false;
      }, 0);
    }
  }, []);

  const onPanClickCapture = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (justDraggedRef.current) {
        e.stopPropagation();
        e.preventDefault();
      }
    },
    [],
  );

  const onImgLoad = useCallback(() => {
    const img = imgRef.current;
    if (img && img.naturalWidth && img.naturalHeight) {
      setNaturalAspect(img.naturalWidth / img.naturalHeight);
    }
    setLoaded(true);
  }, []);

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

  // Inner box keeps image + overlay locked to the same aspect ratio so the
  // SVG dots always land on the same physical pixels as the image. At
  // zoom=1 we keep the original fit-to-container constraints; past 1 we
  // explicitly size width to a multiple of the container so the box
  // overflows and the outer wrapper scrolls.
  const aspectStyle = naturalAspect
    ? zoom === 1
      ? { aspectRatio: `${naturalAspect}`, maxWidth: "100%", maxHeight: "100%" }
      : {
          aspectRatio: `${naturalAspect}`,
          width: `${100 * zoom}%`,
          maxWidth: "none",
          maxHeight: "none",
        }
    : { width: "100%", height: "100%" };

  // Two-layer structure:
  //   outer:   bounded box that hosts overlays (zoom widget, hints, errors).
  //            Doesn't scroll — overlays stay pinned regardless of pan.
  //   scroll:  fills the outer; at zoom=1 it just centers content, past 1
  //            it becomes overflow-auto and the user pans with drag/scroll.
  // Click-to-tag math is unaffected because the SVG's getBoundingClientRect
  // reflects rendered position regardless of scroll offset.
  const scrollClass =
    zoom === 1
      ? "absolute inset-0 flex items-center justify-center overflow-hidden"
      : `absolute inset-0 overflow-auto ${
          canPan ? (isDragging ? "cursor-grabbing select-none" : "cursor-grab") : ""
        }`;

  return (
    <div className="relative h-full w-full overflow-hidden bg-zinc-100 dark:bg-zinc-900">
      {/* Scroll layer — pan target; held inside the bounded outer so the
       *  zoom widget and other overlays positioned at the outer's edges
       *  never scroll out of view. */}
      <div
        ref={containerRef}
        className={scrollClass}
        onMouseDown={onPanMouseDown}
        onMouseMove={onPanMouseMove}
        onMouseUp={endPan}
        onMouseLeave={endPan}
        onClickCapture={onPanClickCapture}
      >
      {!loaded && !error && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-zinc-500">
          Loading PCB layout…
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center text-sm text-zinc-500">
          <div className="font-medium text-zinc-700 dark:text-zinc-300">
            No PCB layout available
          </div>
          {onUploadImage ? (
            <>
              <div className="max-w-xs text-xs leading-snug">
                Upload a PCB layout image (PNG / JPG / WebP) to use the
                click-to-tag workflow on this project.
              </div>
              <button
                type="button"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
                className="rounded-md border border-emerald-500 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800 hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 dark:hover:bg-emerald-900/50"
              >
                {uploading ? "Uploading…" : "Upload PCB image"}
              </button>
              <div className="text-[11px] text-zinc-400">
                Or attach a PedalPCB PDF on the Overview tab.
              </div>
            </>
          ) : (
            <div className="text-xs">
              Attach a PDF on the Overview tab and the PCB layout page will render here.
            </div>
          )}
        </div>
      )}
      {onUploadImage && (
        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (!f) return;
            setUploading(true);
            try {
              await onUploadImage(f);
              setError(false);
              setLoaded(false);
            } finally {
              setUploading(false);
            }
          }}
        />
      )}
      {loaded && hasCustomImage && onUploadImage && (
        <div className="absolute right-2 top-2 z-10 flex gap-1">
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
            className="rounded bg-zinc-900/70 px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-zinc-100 backdrop-blur hover:bg-zinc-900/90 disabled:opacity-50"
            title="Replace the custom PCB layout image"
          >
            {uploading ? "Uploading…" : "Replace image"}
          </button>
          {onClearImage && (
            <button
              type="button"
              onClick={async () => {
                await onClearImage();
                setLoaded(false);
              }}
              className="rounded bg-zinc-900/70 px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-zinc-100 backdrop-blur hover:bg-red-700/80"
              title="Remove the custom image (falls back to PDF page if attached)"
            >
              Remove
            </button>
          )}
        </div>
      )}
      <div className="relative" style={aspectStyle}>
      <img
        ref={imgRef}
        src={imageUrl}
        alt="PCB layout"
        className={`block h-full w-full object-contain ${loaded ? "" : "opacity-0"}`}
        onLoad={onImgLoad}
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
                    r={0.028}
                    fill="none"
                    stroke={color.fill}
                    strokeWidth={0.004}
                    strokeOpacity={0.7}
                  >
                    <animate
                      attributeName="r"
                      values="0.016;0.04;0.016"
                      dur="1.2s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
                <circle
                  cx={x}
                  cy={y}
                  r={isHighlighted ? 0.011 : 0.0065}
                  fill={color.fill}
                  stroke={color.stroke}
                  strokeWidth={0.0012}
                  fillOpacity={isHighlighted ? 0.75 : 0.55}
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
      </div>
      </div>
      {/* Zoom controls — siblings of the scroll layer (not inside it), so
       *  panning the image leaves them pinned to the outer's top-right.
       *  Disabled at min/max steps. */}
      {loaded && !error && (
        <div className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-zinc-200 bg-white/90 px-1 py-0.5 text-xs shadow-md backdrop-blur dark:border-zinc-700 dark:bg-zinc-900/90">
          <button
            onClick={zoomOut}
            disabled={zoomIndex === 0}
            title="Zoom out"
            className="flex h-6 w-6 items-center justify-center rounded text-zinc-700 hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            −
          </button>
          <button
            onClick={zoomReset}
            disabled={zoom === 1}
            title="Reset zoom"
            className="min-w-[2.5rem] rounded px-1 py-0.5 font-mono tabular-nums text-zinc-700 hover:bg-zinc-200 disabled:opacity-60 disabled:hover:bg-transparent dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            {zoom.toFixed(2).replace(/\.?0+$/, "")}×
          </button>
          <button
            onClick={zoomIn}
            disabled={zoomIndex === ZOOM_STEPS.length - 1}
            title="Zoom in"
            className="flex h-6 w-6 items-center justify-center rounded text-zinc-700 hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            +
          </button>
        </div>
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
