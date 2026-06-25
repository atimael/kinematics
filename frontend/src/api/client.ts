import type {
  AngleRow,
  ChartData,
  GaitReport,
  JobState,
  ProjectMeta,
  ProjectParams,
  ResultsSummary,
} from "../types";

const BASE = "/api";

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listProjects: () => jsonFetch<ProjectMeta[]>(`${BASE}/projects`),

  getProject: (id: string) => jsonFetch<ProjectMeta>(`${BASE}/projects/${id}`),

  createProject: (params: Partial<ProjectParams>) =>
    jsonFetch<ProjectMeta>(`${BASE}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }),

  deleteProject: (id: string) =>
    jsonFetch<{ deleted: boolean }>(`${BASE}/projects/${id}`, { method: "DELETE" }),

  calibrationFiles: (id: string) =>
    jsonFetch<{ intrinsics: Record<string, string[]>; extrinsics: Record<string, string | null> }>(
      `${BASE}/projects/${id}/calibration/files`,
    ),

  uploadIntrinsics: (id: string, camera: string, files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return jsonFetch(`${BASE}/projects/${id}/calibration/intrinsics/${camera}`, {
      method: "POST",
      body: fd,
    });
  },

  uploadExtrinsics: (id: string, camera: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return jsonFetch(`${BASE}/projects/${id}/calibration/extrinsics/${camera}`, {
      method: "POST",
      body: fd,
    });
  },

  extractExtrinsics: (id: string) =>
    jsonFetch<{ frame_index: number; cameras: { camera: string; detected: boolean; file: string }[] }>(
      `${BASE}/projects/${id}/calibration/extract-extrinsics`,
      { method: "POST" },
    ),

  runCalibration: (id: string) =>
    jsonFetch<{ job_id: string }>(`${BASE}/projects/${id}/calibration/run`, { method: "POST" }),

  acceptCalibration: (id: string) =>
    jsonFetch<ProjectMeta>(`${BASE}/projects/${id}/calibration/accept`, { method: "POST" }),

  listVideos: (id: string) =>
    jsonFetch<Record<string, string | null>>(`${BASE}/projects/${id}/videos`),

  uploadVideo: (id: string, camera: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return jsonFetch(`${BASE}/projects/${id}/videos/${camera}`, { method: "POST", body: fd });
  },

  runProcessing: (id: string) =>
    jsonFetch<{ job_id: string; stages: string[] }>(`${BASE}/projects/${id}/process`, {
      method: "POST",
    }),

  currentJob: (id: string) => jsonFetch<{ job: JobState | null }>(`${BASE}/projects/${id}/job`),

  results: (id: string) => jsonFetch<ResultsSummary>(`${BASE}/projects/${id}/results`),

  anglesTable: (id: string) =>
    jsonFetch<{ rows: AngleRow[]; n_frames: number }>(`${BASE}/projects/${id}/results/angles/table`),

  gait: (id: string) => jsonFetch<GaitReport>(`${BASE}/projects/${id}/results/gait`),

  angles: (id: string, columns?: string[], kind: "angle" | "velocity" = "angle") => {
    const q = new URLSearchParams({ kind });
    if (columns?.length) q.set("columns", columns.join(","));
    return jsonFetch<ChartData>(`${BASE}/projects/${id}/results/angles.json?${q}`);
  },

  positions: (id: string, markers?: string[], kind: "position" | "speed" = "position") => {
    const q = new URLSearchParams({ kind });
    if (markers?.length) q.set("markers", markers.join(","));
    return jsonFetch<ChartData>(`${BASE}/projects/${id}/results/positions.json?${q}`);
  },

  gaitCsvUrl: (id: string) => `${BASE}/projects/${id}/results/gait.csv`,
  anglesCsvUrl: (id: string) => `${BASE}/projects/${id}/results/angles.csv`,
  positionsCsvUrl: (id: string) => `${BASE}/projects/${id}/results/positions.csv`,
  streamUrl: (id: string, jobId: string) => `${BASE}/projects/${id}/jobs/${jobId}/stream`,
};
