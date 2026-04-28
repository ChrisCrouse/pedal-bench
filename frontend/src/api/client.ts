/**
 * Thin typed API client for the pedal-bench FastAPI backend.
 *
 * Types mirror backend/pedal_bench/api/schemas.py — keep in sync. When the
 * backend stabilizes we'll auto-generate this from the OpenAPI schema.
 */
import { getApiKey } from "@/lib/apiKey";

export type Side = "A" | "B" | "C" | "D" | "E";
export type Status = "planned" | "ordered" | "building" | "finishing" | "done";
export type BuildPhase = "pcb" | "drill" | "finish" | "wiring" | "test";
export type IconKind =
  | "pot"
  | "chicken-head"
  | "footswitch"
  | "toggle"
  | "led"
  | "jack"
  | "dc-jack"
  | "expression";

export interface FaceDims {
  width_mm: number;
  height_mm: number;
  label: string;
}

export interface Enclosure {
  key: string;
  name: string;
  length_mm: number;
  width_mm: number;
  height_mm: number;
  wall_thickness_mm: number;
  faces: Record<string, FaceDims>;
  notes: string;
}

export interface Hole {
  side: Side;
  x_mm: number;
  y_mm: number;
  diameter_mm: number;
  label: string | null;
  powder_coat_margin: boolean;
  icon?: IconKind | null;
  /** Holes sharing a mirror_group move together when one is dragged. */
  mirror_group?: string | null;
  /** Flip flags describe this hole's position relative to the group seed. */
  mirror_x_flipped?: boolean;
  mirror_y_flipped?: boolean;
  mirror_ce_flipped?: boolean;
}

export interface SnapGuide {
  vertical_lines_mm: number[];
  horizontal_lines_mm: number[];
}

export interface LayoutPreset {
  id: string;
  enclosure: string;
  category: "jacks" | "controls" | "combined" | string;
  name: string;
  description: string;
  holes: Hole[];
}

export interface LayoutPresetsResponse {
  presets: LayoutPreset[];
  snap_guides: Record<string, Record<string, SnapGuide>>;
}

export interface BOMItem {
  location: string;
  value: string;
  type: string;
  notes: string;
  quantity: number;
  polarity_sensitive: boolean;
  orientation_hint: string | null;
}

export interface BuildProgress {
  soldered_locations: string[];
  current_phase: BuildPhase;
  phase_notes: Record<string, string>;
}

export interface Project {
  slug: string;
  name: string;
  status: Status;
  enclosure: string;
  source_pdf: string | null;
  bom: BOMItem[];
  holes: Hole[];
  progress: BuildProgress;
  notes: string;
  /** Per-refdes positions on the cached PCB layout image; manual tagging. */
  refdes_map: Record<string, [number, number]>;
  created_at: string;
  updated_at: string;
  /** Tayda Manufacturing Center drill-template deep link captured at import. */
  drill_tool_url?: string | null;
  /** Original source supplier and URL captured during import, when known. */
  source_supplier?: string | null;
  source_url?: string | null;
  /** When false, this project is excluded from the global shopping list. */
  active: boolean;
}

export interface ProjectSummary {
  slug: string;
  name: string;
  status: Status;
  enclosure: string;
  updated_at: string;
}

export interface STLExport {
  side: Side;
  path: string;
  size_bytes: number;
}

export type STLTemplateMode = "pilot" | "mark" | "full";

export interface STLExportOptions {
  template_mode?: STLTemplateMode;
  pilot_diameter_mm?: number;
  show_final_size_ring?: boolean;
}

export interface Photo {
  filename: string;
  url: string;
  uploaded_at: string;
  caption: string;
  size_bytes: number;
}


const BASE = "/api/v1";

function withApiKey(headers: HeadersInit | undefined): HeadersInit {
  const key = getApiKey();
  if (!key) return headers ?? {};
  // Merge user-supplied headers + the BYOK header (BYOK wins on conflict).
  return { ...(headers ?? {}), "X-Anthropic-Key": key };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const baseHeaders: HeadersInit = { "Content-Type": "application/json" };
  const merged: RequestInit = {
    ...init,
    headers: withApiKey({ ...baseHeaders, ...(init?.headers ?? {}) }),
  };
  const res = await fetch(BASE + path, merged);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export interface DebugPin {
  pin: number;
  name: string;
  expected_v: number | null;
  tolerance_v: number | null;
}

export interface DebugIC {
  key: string;
  description: string;
  family: string;
  package: string;
  common_in: string[];
  pins: DebugPin[];
}

export interface CommonFailure {
  symptom: string;
  likely_causes: string[];
}

export interface DebugDataset {
  supply: { vcc_v: number; vref_v: number; vref_tolerance_v: number };
  ics: DebugIC[];
  audio_probe_procedure: string[];
  common_failures: CommonFailure[];
}

export interface PDFExtractOut {
  suggested_name: string | null;
  suggested_enclosure: string | null;
  enclosure_in_catalog: boolean;
  bom: BOMItem[];
  holes: Hole[];
  wiring_page_index: number | null;
  drill_template_page_index: number | null;
  warnings: string[];
  /** Workflow hand-offs to surface after a successful import (e.g., drill-tool
   *  walkthrough for Taydakits). Distinct from warnings, which mean a problem. */
  next_steps?: string[];
  source_supplier?: string | null;
  source_url?: string | null;
}

async function uploadPdf<T>(path: string, file: File, fields: Record<string, string> = {}): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  for (const [k, v] of Object.entries(fields)) fd.append(k, v);
  const res = await fetch(BASE + path, {
    method: "POST",
    body: fd,
    headers: withApiKey(undefined),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export interface AIStatus {
  available: boolean;
  source: "header" | "env" | null;
}

export interface InventoryStats {
  project_count: number;
  unique_parts: number;
  total_parts: number;
  by_kind: { kind: string; quantity: number }[];
}

export interface InventoryPart {
  kind: string;
  value_norm: string;
  value_magnitude: number | null;
  display_value: string;
  total_qty: number;
  project_count: number;
  project_slugs: string[];
}

export interface InventoryProjectHit {
  slug: string;
  name: string;
  status: Status;
  quantity: number;
}

export interface InventoryItem {
  key: string;
  kind: string;
  value_norm: string;
  /** Numeric magnitude of value_norm (e.g. "10k" → 10000). Null for ICs and
   *  anything that doesn't start with a number. Used for sort ordering. */
  value_magnitude: number | null;
  display_value: string;
  on_hand: number;
  reservations: Record<string, number>;
  reserved_total: number;
  available: number;
  supplier: string | null;
  unit_cost_usd: number | null;
  notes: string;
}

export interface InventoryItemInput {
  kind: string;
  value: string;
  on_hand: number;
  display_value?: string;
  supplier?: string | null;
  unit_cost_usd?: number | null;
  notes?: string;
}

export interface InventoryItemPatch {
  on_hand?: number;
  display_value?: string;
  supplier?: string | null;
  unit_cost_usd?: number | null;
  notes?: string;
}

export interface ShortageRow {
  kind: string;
  value_norm: string;
  value_magnitude: number | null;
  display_value: string;
  type_hint: string;
  needed: number;
  on_hand: number;
  reserved_for_others: number;
  reserved_for_self: number;
  available: number;
  shortfall: number;
  unit_cost_usd: number | null;
  supplier: string | null;
  needed_by: string[];
}

export interface Shortage {
  rows: ShortageRow[];
  estimated_total_cost_usd: number | null;
}

export const api = {
  health: () => request<{ status: string; service: string }>("/health"),
  aiStatus: {
    get: () => request<AIStatus>("/ai/status"),
  },
  inventory: {
    stats: () => request<InventoryStats>("/inventory/stats"),
    parts: (kind?: string, search?: string) => {
      const qs = new URLSearchParams();
      if (kind) qs.set("kind", kind);
      if (search) qs.set("search", search);
      const q = qs.toString();
      return request<{ parts: InventoryPart[] }>(
        `/inventory/parts${q ? `?${q}` : ""}`,
      );
    },
    projectsUsing: (kind: string, valueNorm: string) =>
      request<{ projects: InventoryProjectHit[] }>(
        `/inventory/parts/${encodeURIComponent(kind)}/${encodeURIComponent(valueNorm)}/projects`,
      ),
    items: {
      list: (kind?: string, search?: string) => {
        const qs = new URLSearchParams();
        if (kind) qs.set("kind", kind);
        if (search) qs.set("search", search);
        const q = qs.toString();
        return request<InventoryItem[]>(
          `/inventory/items${q ? `?${q}` : ""}`,
        );
      },
      upsert: (payload: InventoryItemInput) =>
        request<InventoryItem>("/inventory/items", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      patch: (key: string, payload: InventoryItemPatch) =>
        request<InventoryItem>(
          `/inventory/items/${encodeURIComponent(key)}`,
          { method: "PATCH", body: JSON.stringify(payload) },
        ),
      delete: (key: string) =>
        request<void>(
          `/inventory/items/${encodeURIComponent(key)}`,
          { method: "DELETE" },
        ),
      reserve: (key: string, slug: string, qty: number) =>
        request<InventoryItem>(
          `/inventory/items/${encodeURIComponent(key)}/reserve`,
          { method: "POST", body: JSON.stringify({ slug, qty }) },
        ),
    },
    shortage: () => request<Shortage>("/inventory/shortage"),
  },
  pdf: {
    extract: (file: File) => uploadPdf<PDFExtractOut>("/pdf/extract", file),
    extractFromUrl: (url: string) =>
      request<PDFExtractOut>("/pdf/from-url", {
        method: "POST",
        body: JSON.stringify({ url }),
      }),
  },
  debug: {
    dataset: () => request<DebugDataset>("/debug/dataset"),
  },
  layoutPresets: {
    all: () => request<LayoutPresetsResponse>("/layout-presets"),
  },
  enclosures: {
    list: () => request<Enclosure[]>("/enclosures"),
    get: (key: string) => request<Enclosure>(`/enclosures/${encodeURIComponent(key)}`),
  },
  projects: {
    list: () => request<ProjectSummary[]>("/projects"),
    get: (slug: string) => request<Project>(`/projects/${encodeURIComponent(slug)}`),
    create: (payload: { name: string; enclosure?: string }) =>
      request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    createFromPdf: (file: File, name?: string, enclosure?: string) =>
      uploadPdf<Project>("/projects/from-pdf", file, {
        ...(name ? { name } : {}),
        ...(enclosure ? { enclosure } : {}),
      }),
    createFromUrl: (url: string, name?: string, enclosure?: string) =>
      request<Project>("/projects/from-url", {
        method: "POST",
        body: JSON.stringify({
          url,
          ...(name ? { name } : {}),
          ...(enclosure ? { enclosure } : {}),
        }),
      }),
    update: (
      slug: string,
      payload: Partial<Pick<Project, "name" | "status" | "enclosure" | "notes" | "active">>,
    ) =>
      request<Project>(`/projects/${encodeURIComponent(slug)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    delete: (slug: string) =>
      request<void>(`/projects/${encodeURIComponent(slug)}`, { method: "DELETE" }),
    replaceHoles: (slug: string, holes: Hole[]) =>
      request<Hole[]>(`/projects/${encodeURIComponent(slug)}/holes`, {
        method: "PUT",
        body: JSON.stringify({ holes }),
      }),
    exportSTLs: (slug: string, options?: STLExportOptions) =>
      request<STLExport[]>(`/projects/${encodeURIComponent(slug)}/stl/export`, {
        method: "POST",
        body: JSON.stringify(options ?? {}),
      }),
    extractHoles: (slug: string) =>
      request<Hole[]>(`/projects/${encodeURIComponent(slug)}/extract-holes`, {
        method: "POST",
      }),
    attachPdf: (slug: string, file: File) =>
      uploadPdf<Project>(`/projects/${encodeURIComponent(slug)}/attach-pdf`, file),
    setRefdesMap: (slug: string, map: Record<string, [number, number]>) =>
      request<{ refdes_map: Record<string, [number, number]> }>(
        `/projects/${encodeURIComponent(slug)}/refdes-map`,
        { method: "PUT", body: JSON.stringify({ refdes_map: map }) },
      ),
    pcbLayoutImageUrl: (slug: string) =>
      `/api/v1/projects/${encodeURIComponent(slug)}/pcb-layout.png`,
    shortage: (slug: string) =>
      request<Shortage>(`/projects/${encodeURIComponent(slug)}/shortage`),
    consumeReservations: (slug: string) =>
      request<{ consumed: [string, number][] }>(
        `/projects/${encodeURIComponent(slug)}/consume-reservations`,
        { method: "POST" },
      ),
  },
  tayda: {
    parse: (text: string) =>
      request<Hole[]>("/tayda/parse", {
        method: "POST",
        body: JSON.stringify({ text }),
      }),
  },
  diagnose: {
    run: (
      slug: string,
      payload: {
        symptom: string;
        selected_ic?: string | null;
        readings: { pin: number; measured_v: number | null }[];
        include_wiring_image: boolean;
      },
    ) =>
      request<{
        primary_suspect: string;
        reasoning: string;
        next_probe: string;
        confidence: "high" | "medium" | "low" | "error";
        alternative_suspects: string[];
        caveats: string[];
        used_wiring_image: boolean;
      }>(`/projects/${encodeURIComponent(slug)}/debug/diagnose`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },
  verify: {
    component: (slug: string, location: string, file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("location", location);
      return fetch(
        `/api/v1${`/projects/${encodeURIComponent(slug)}/bom/verify-component`}`,
        { method: "POST", body: fd },
      ).then(async (res) => {
        if (!res.ok) {
          const body = await res.text();
          throw new Error(`${res.status} ${res.statusText}: ${body}`);
        }
        return res.json() as Promise<{
          verdict: "match" | "mismatch" | "unsure" | "error";
          explanation: string;
          guess_value: string | null;
          guess_type: string | null;
          expected_value: string;
          expected_type: string;
          location: string;
        }>;
      });
    },
  },
  photos: {
    list: (slug: string) =>
      request<Photo[]>(`/projects/${encodeURIComponent(slug)}/photos`),
    upload: (slug: string, file: File, caption?: string) =>
      uploadPdf<Photo>(
        `/projects/${encodeURIComponent(slug)}/photos`,
        file,
        caption ? { caption } : {},
      ),
    updateCaption: (slug: string, filename: string, caption: string) =>
      request<Photo>(
        `/projects/${encodeURIComponent(slug)}/photos/${encodeURIComponent(filename)}`,
        { method: "PATCH", body: JSON.stringify({ caption }) },
      ),
    delete: (slug: string, filename: string) =>
      request<{ ok: boolean }>(
        `/projects/${encodeURIComponent(slug)}/photos/${encodeURIComponent(filename)}`,
        { method: "DELETE" },
      ),
  },
};
