/**
 * Thin typed API client for the pedal-bench FastAPI backend.
 *
 * Types mirror backend/pedal_bench/api/schemas.py — keep in sync. When the
 * backend stabilizes we'll auto-generate this from the OpenAPI schema.
 */
import { getApiKey } from "@/lib/apiKey";
import { getTaydaToken } from "@/lib/taydaToken";

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

export interface Photo {
  filename: string;
  url: string;
  uploaded_at: string;
  caption: string;
  size_bytes: number;
}

export interface TaydaPushOut {
  design_id: string | null;
  design_url: string | null;
  status_code: number;
  tayda_response: unknown;
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

export const api = {
  health: () => request<{ status: string; service: string }>("/health"),
  aiStatus: {
    get: () => request<AIStatus>("/ai/status"),
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
      payload: Partial<Pick<Project, "name" | "status" | "enclosure" | "notes">>,
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
    exportSTLs: (slug: string) =>
      request<STLExport[]>(`/projects/${encodeURIComponent(slug)}/stl/export`, {
        method: "POST",
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
  },
  tayda: {
    parse: (text: string) =>
      request<Hole[]>("/tayda/parse", {
        method: "POST",
        body: JSON.stringify({ text }),
      }),
    push: (
      slug: string,
      body: { is_public?: boolean; name_override?: string } = {},
    ) => {
      // Tayda token rides as X-Tayda-Token on this one call only (not
      // on every request). Second BYOK axis, mirrors X-Anthropic-Key.
      const token = getTaydaToken();
      return request<TaydaPushOut>(
        `/projects/${encodeURIComponent(slug)}/tayda/push`,
        {
          method: "POST",
          body: JSON.stringify(body),
          headers: token ? { "X-Tayda-Token": token } : {},
        },
      );
    },
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
