/**
 * Thin typed API client for the pedal-bench FastAPI backend.
 *
 * Types mirror backend/pedal_bench/api/schemas.py — keep in sync. When the
 * backend stabilizes we'll auto-generate this from the OpenAPI schema.
 */

export type Side = "A" | "B" | "C" | "D" | "E";
export type Status = "planned" | "ordered" | "building" | "finishing" | "done";
export type BuildPhase = "pcb" | "drill" | "finish" | "wiring" | "test";

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

const BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; service: string }>("/health"),
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
  },
  tayda: {
    parse: (text: string) =>
      request<Hole[]>("/tayda/parse", {
        method: "POST",
        body: JSON.stringify({ text }),
      }),
  },
};
