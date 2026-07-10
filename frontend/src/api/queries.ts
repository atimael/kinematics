import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "./client";
import type { JobEvent, ProjectParams } from "../types";

export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: api.listProjects });
}

export function useProject(id: string, opts?: { poll?: boolean }) {
  return useQuery({
    queryKey: ["project", id],
    queryFn: () => api.getProject(id),
    refetchInterval: opts?.poll ? 2000 : false,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: Partial<ProjectParams>) => api.createProject(params),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useCalibrationFiles(id: string) {
  return useQuery({ queryKey: ["calibFiles", id], queryFn: () => api.calibrationFiles(id) });
}

export function useVideos(id: string) {
  return useQuery({ queryKey: ["videos", id], queryFn: () => api.listVideos(id) });
}

export function useResults(id: string, enabled: boolean) {
  return useQuery({ queryKey: ["results", id], queryFn: () => api.results(id), enabled });
}

export function useAngles(id: string, columns: string[], enabled: boolean) {
  return useQuery({
    queryKey: ["angles", id, columns.join(",")],
    queryFn: () => api.angles(id, columns),
    enabled: enabled && columns.length > 0,
    staleTime: Infinity,
  });
}

export interface JobStream {
  status: "idle" | "running" | "done" | "failed";
  stage: string | null;
  pct: number;
  logs: string[];
  calib: { px: number[]; mm: number[] } | null;
  error: string | null;
}

/** Subscribe to a job's SSE stream. EventSource is an external resource -> useEffect is warranted. */
export function useJobStream(projectId: string, jobId: string | null, onDone?: () => void): JobStream {
  const [state, setState] = useState<JobStream>({
    status: "idle",
    stage: null,
    pct: 0,
    logs: [],
    calib: null,
    error: null,
  });
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (!jobId) return;
    setState({ status: "running", stage: null, pct: 0, logs: [], calib: null, error: null });
    const es = new EventSource(api.streamUrl(projectId, jobId));

    es.onmessage = (e) => {
      const ev: JobEvent = JSON.parse(e.data);
      setState((prev) => {
        const next = { ...prev };
        if (ev.type === "stage") {
          next.stage = ev.stage ?? prev.stage;
          if (typeof ev.pct === "number") next.pct = ev.pct;
          if (ev.status === "failed") {
            next.status = "failed";
            next.error = ev.error ?? "stage failed";
          }
        } else if (ev.type === "log" && ev.msg) {
          next.logs = [...prev.logs.slice(-400), ev.msg];
        } else if (ev.type === "calib") {
          next.calib = { px: ev.px ?? [], mm: ev.mm ?? [] };
        } else if (ev.type === "job") {
          next.status = ev.status === "done" ? "done" : ev.status === "failed" ? "failed" : prev.status;
          if (ev.error) next.error = ev.error;
        } else if (ev.type === "end") {
          es.close();
          onDoneRef.current?.();
        }
        return next;
      });
    };
    es.onerror = () => {
      /* server closes the stream at job end; rely on the 'end' event to finalize */
    };
    return () => es.close();
  }, [projectId, jobId]);

  return state;
}
