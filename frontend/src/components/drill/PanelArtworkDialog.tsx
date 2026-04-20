import { useMemo, useState } from "react";
import type { Enclosure, Hole, Side } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Select } from "@/components/ui/Select";

interface Props {
  open: boolean;
  onClose: () => void;
  enclosure: Enclosure;
  holes: Hole[];
  pedalName: string;
}

/**
 * Generates a print-ready panel-artwork SVG for a chosen face. Places
 * labels at each hole position (Tayda x/y → SVG pixel), with the pedal
 * name as a header. Users download as SVG (vector — best for UV prints
 * and water-slide decals) or PNG (canvas rasterization, 600 DPI).
 */
export function PanelArtworkDialog({
  open,
  onClose,
  enclosure,
  holes,
  pedalName,
}: Props) {
  const facesWithHoles = useMemo(() => {
    const set = new Set<Side>();
    for (const h of holes) set.add(h.side);
    return Array.from(set).sort() as Side[];
  }, [holes]);

  const [side, setSide] = useState<Side>(
    facesWithHoles[0] ?? ("A" as Side),
  );
  const face = enclosure.faces[side];
  const sideHoles = holes.filter((h) => h.side === side);

  const svg = useMemo(
    () => renderPanelSVG({ enclosure, side, face, sideHoles, pedalName }),
    [enclosure, side, face, sideHoles, pedalName],
  );

  const downloadSvg = () => {
    const blob = new Blob([svg], { type: "image/svg+xml" });
    triggerDownload(blob, `${slugName(pedalName)}-panel-${side}.svg`);
  };

  const downloadPng = async () => {
    const blob = await svgToPng(svg, 600);
    triggerDownload(blob, `${slugName(pedalName)}-panel-${side}.png`);
  };

  if (!face) return null;

  return (
    <Dialog open={open} onClose={onClose} title="Panel artwork" maxWidth="xl">
      <div className="space-y-4">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Print-ready artwork for the drilled face. Use the SVG for vector
          workflows (UV print, Illustrator) or the PNG for water-slide decals.
          Scale is 1:1 — printed at 100% the knob positions match the
          enclosure.
        </p>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Face
            </span>
            <Select value={side} onChange={(e) => setSide(e.target.value as Side)}>
              {facesWithHoles.length === 0 && (
                <option value="A" disabled>
                  No holes on any face yet
                </option>
              )}
              {facesWithHoles.map((s) => (
                <option key={s} value={s}>
                  {s} — {enclosure.faces[s]?.label ?? s}
                </option>
              ))}
            </Select>
          </label>
          <div className="text-xs text-zinc-500">
            {sideHoles.length} holes · {face.width_mm.toFixed(1)} × {face.height_mm.toFixed(1)} mm
          </div>
        </div>

        <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
          <div
            className="mx-auto max-h-[60vh] max-w-full"
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button variant="secondary" onClick={downloadPng}>
            Download PNG (600 DPI)
          </Button>
          <Button variant="primary" onClick={downloadSvg}>
            Download SVG
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function renderPanelSVG(args: {
  enclosure: Enclosure;
  side: Side;
  face: { width_mm: number; height_mm: number; label: string };
  sideHoles: Hole[];
  pedalName: string;
}): string {
  const { face, sideHoles, pedalName } = args;
  const PAD_MM = 10;
  const TITLE_H = 10;
  const w = face.width_mm + 2 * PAD_MM;
  const h = face.height_mm + 2 * PAD_MM + TITLE_H;

  // SVG has Y+ down; holes are Tayda (Y+ up). Face origin is at center of the face.
  // Layout origin = top-left of the outer canvas.
  const faceOriginX = PAD_MM;
  const faceOriginY = PAD_MM + TITLE_H;
  const centerX = faceOriginX + face.width_mm / 2;
  const centerY = faceOriginY + face.height_mm / 2;

  const holeMarkup = sideHoles
    .map((hole) => {
      const x = centerX + hole.x_mm;
      const y = centerY - hole.y_mm; // flip Y
      const r = hole.diameter_mm / 2;
      const labelY = y + r + 4;
      const label = escapeXml(hole.label ?? "");
      return `
        <circle cx="${x}" cy="${y}" r="${r}" fill="none" stroke="#111" stroke-width="0.25"/>
        ${label
          ? `<text x="${x}" y="${labelY}" text-anchor="middle" font-family="Segoe UI, Helvetica, sans-serif" font-size="3.2" fill="#111">${label}</text>`
          : ""}
      `;
    })
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 ${w} ${h}"
     width="${w}mm"
     height="${h}mm">
  <rect x="0" y="0" width="${w}" height="${h}" fill="#ffffff"/>
  <text x="${w / 2}" y="${PAD_MM / 2 + TITLE_H / 2 + 1}"
        text-anchor="middle"
        font-family="Segoe UI, Helvetica, sans-serif"
        font-size="6" font-weight="600" fill="#111">
    ${escapeXml(pedalName)}
  </text>
  <rect x="${faceOriginX}" y="${faceOriginY}"
        width="${face.width_mm}" height="${face.height_mm}"
        fill="none" stroke="#bbb" stroke-width="0.15"
        stroke-dasharray="1 1"/>
  ${holeMarkup}
</svg>`;
}

async function svgToPng(svg: string, dpi: number): Promise<Blob> {
  // Parse viewBox to get intrinsic mm size, then rasterize at DPI.
  const match = svg.match(/viewBox="\s*0\s+0\s+([\d.]+)\s+([\d.]+)"/);
  const widthMm = match ? parseFloat(match[1]) : 100;
  const heightMm = match ? parseFloat(match[2]) : 100;
  const pxPerMm = dpi / 25.4;
  const pxW = Math.round(widthMm * pxPerMm);
  const pxH = Math.round(heightMm * pxPerMm);

  const canvas = document.createElement("canvas");
  canvas.width = pxW;
  canvas.height = pxH;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, pxW, pxH);

  const img = new Image();
  const svgBlob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = reject;
    img.src = url;
  });
  ctx.drawImage(img, 0, 0, pxW, pxH);
  URL.revokeObjectURL(url);
  return new Promise<Blob>((resolve) =>
    canvas.toBlob((b) => resolve(b!), "image/png"),
  );
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function slugName(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "panel";
}

function escapeXml(s: string): string {
  return s.replace(/[<>&'"]/g, (c) => {
    switch (c) {
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case "&":
        return "&amp;";
      case "'":
        return "&apos;";
      case '"':
        return "&quot;";
    }
    return c;
  });
}
