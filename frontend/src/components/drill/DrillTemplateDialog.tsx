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
 * Print-ready drill template for builders without a 3D printer. Renders
 * each hole as a circle (true diameter) with a crosshair through its
 * center for center-punching. 1:1 mm scale; user must print at 100% (no
 * "fit to page"). Includes a 10mm reference square so they can verify
 * scale with a ruler before drilling.
 */
export function DrillTemplateDialog({
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
    () =>
      face
        ? renderTemplateSVG({
            side,
            face,
            sideHoles,
            pedalName,
            enclosureKey: enclosure.key,
          })
        : "",
    [face, side, sideHoles, pedalName, enclosure.key],
  );

  const downloadSvg = () => {
    const blob = new Blob([svg], { type: "image/svg+xml" });
    triggerDownload(blob, `${slugName(pedalName)}-drill-${side}.svg`);
  };

  const downloadPng = async () => {
    const blob = await svgToPng(svg, 600);
    triggerDownload(blob, `${slugName(pedalName)}-drill-${side}.png`);
  };

  const openInNewTab = () => {
    const blob = new Blob([svg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    // Don't revoke — the new tab needs the URL to keep working.
  };

  if (!face) return null;

  return (
    <Dialog open={open} onClose={onClose} title="Print drill template" maxWidth="xl">
      <div className="space-y-4">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          1:1 scale template with crosshairs at every hole center for
          center-punching. Print at <strong>100% scale</strong> (turn off
          "fit to page" / "shrink to fit"). Verify the 10&nbsp;mm reference
          square with a ruler before drilling.
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
            {sideHoles.length} {sideHoles.length === 1 ? "hole" : "holes"} ·{" "}
            {face.width_mm.toFixed(0)} × {face.height_mm.toFixed(0)} mm
          </div>
        </div>

        <div className="overflow-auto rounded border border-zinc-200 bg-white p-4 dark:border-zinc-800">
          <div
            className="mx-auto"
            style={{ maxWidth: "100%" }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button variant="secondary" onClick={openInNewTab} disabled={!sideHoles.length}>
            Open in new tab
          </Button>
          <Button variant="secondary" onClick={downloadPng} disabled={!sideHoles.length}>
            Download PNG (600 DPI)
          </Button>
          <Button variant="primary" onClick={downloadSvg} disabled={!sideHoles.length}>
            Download SVG
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

interface RenderArgs {
  side: Side;
  face: { width_mm: number; height_mm: number; label: string };
  sideHoles: Hole[];
  pedalName: string;
  enclosureKey: string;
}

function renderTemplateSVG(args: RenderArgs): string {
  const { side, face, sideHoles, pedalName, enclosureKey } = args;

  const PAD_MM = 12;
  const TITLE_H = 12;
  const FOOTER_H = 6;
  const w = face.width_mm + 2 * PAD_MM;
  const h = face.height_mm + 2 * PAD_MM + TITLE_H + FOOTER_H;

  // Face origin = top-left of the drilled rectangle inside the canvas.
  const faceOriginX = PAD_MM;
  const faceOriginY = PAD_MM + TITLE_H;
  const centerX = faceOriginX + face.width_mm / 2;
  const centerY = faceOriginY + face.height_mm / 2;

  // Crosshair geometry — extends past the circle so it's findable on small holes.
  // Each arm is half-length; total visible length = 2 * ARM_MM.
  const ARM_MM = 2.5;

  const holeMarkup = sideHoles
    .map((hole) => {
      const x = centerX + hole.x_mm;
      const y = centerY - hole.y_mm; // PDF/Tayda are Y-up; SVG is Y-down.
      const r = hole.diameter_mm / 2;
      const labelY = y + r + 3.6;
      const label = escapeXml(hole.label ?? "");
      return `
        <circle cx="${fmt(x)}" cy="${fmt(y)}" r="${fmt(r)}" fill="none" stroke="#111" stroke-width="0.25"/>
        <line x1="${fmt(x - ARM_MM)}" y1="${fmt(y)}" x2="${fmt(x + ARM_MM)}" y2="${fmt(y)}" stroke="#111" stroke-width="0.2"/>
        <line x1="${fmt(x)}" y1="${fmt(y - ARM_MM)}" x2="${fmt(x)}" y2="${fmt(y + ARM_MM)}" stroke="#111" stroke-width="0.2"/>
        <circle cx="${fmt(x)}" cy="${fmt(y)}" r="0.25" fill="#111"/>
        ${
          label
            ? `<text x="${fmt(x)}" y="${fmt(labelY)}" text-anchor="middle" font-family="Segoe UI, Helvetica, sans-serif" font-size="2.6" fill="#666">${label}</text>`
            : ""
        }
      `;
    })
    .join("\n");

  // Corner alignment ticks — small triangles at each face corner pointing
  // outward, makes it easier to align cut-out template on the enclosure.
  const tick = (cx: number, cy: number, dx: number, dy: number) => {
    const len = 2.2;
    return `<polyline points="${fmt(cx + dx * len)},${fmt(cy)} ${fmt(cx)},${fmt(cy)} ${fmt(cx)},${fmt(cy + dy * len)}" fill="none" stroke="#666" stroke-width="0.25"/>`;
  };
  const corners =
    tick(faceOriginX, faceOriginY, -1, -1) +
    tick(faceOriginX + face.width_mm, faceOriginY, 1, -1) +
    tick(faceOriginX, faceOriginY + face.height_mm, -1, 1) +
    tick(faceOriginX + face.width_mm, faceOriginY + face.height_mm, 1, 1);

  // 10mm reference square in the top-right (inside the canvas, outside the face).
  const refX = w - PAD_MM - 10;
  const refY = PAD_MM + TITLE_H - 10 - 1;
  const refSquare = `
    <rect x="${fmt(refX)}" y="${fmt(refY)}" width="10" height="10" fill="none" stroke="#111" stroke-width="0.3"/>
    <text x="${fmt(refX + 5)}" y="${fmt(refY - 1)}" text-anchor="middle"
          font-family="Segoe UI, Helvetica, sans-serif"
          font-size="2.4" fill="#666">10 mm — verify with ruler</text>
  `;

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 ${fmt(w)} ${fmt(h)}"
     width="${fmt(w)}mm"
     height="${fmt(h)}mm">
  <rect x="0" y="0" width="${fmt(w)}" height="${fmt(h)}" fill="#ffffff"/>
  <text x="${fmt(w / 2)}" y="${fmt(PAD_MM / 2 + TITLE_H / 2)}"
        text-anchor="middle"
        font-family="Segoe UI, Helvetica, sans-serif"
        font-size="4.2" font-weight="700" fill="#111">
    ${escapeXml(pedalName)} · Face ${escapeXml(side)} · ${escapeXml(enclosureKey)}
  </text>
  <text x="${fmt(w / 2)}" y="${fmt(PAD_MM / 2 + TITLE_H / 2 + 4.5)}"
        text-anchor="middle"
        font-family="Segoe UI, Helvetica, sans-serif"
        font-size="2.6" font-weight="600" fill="#a00">
    PRINT AT 100% SCALE — turn off "fit to page"
  </text>
  ${refSquare}
  <rect x="${fmt(faceOriginX)}" y="${fmt(faceOriginY)}"
        width="${fmt(face.width_mm)}" height="${fmt(face.height_mm)}"
        fill="none" stroke="#bbb" stroke-width="0.15"
        stroke-dasharray="1 1"/>
  ${corners}
  ${holeMarkup}
  <text x="${fmt(w / 2)}" y="${fmt(h - FOOTER_H / 2)}"
        text-anchor="middle"
        font-family="Segoe UI, Helvetica, sans-serif"
        font-size="2.4" fill="#888">
    Tape to enclosure, center-punch through every crosshair, then drill.
  </text>
</svg>`;
}

function fmt(n: number): string {
  return Number(n.toFixed(3)).toString();
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function slugName(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "drill"
  );
}

async function svgToPng(svg: string, dpi: number): Promise<Blob> {
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
