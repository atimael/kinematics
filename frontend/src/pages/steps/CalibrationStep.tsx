import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useCalibrationFiles } from "../../api/queries";
import { FileDrop } from "../../components/FileDrop";
import { JobProgress } from "../../components/JobProgress";
import { Badge, Button, Card, CardHeader } from "../../components/ui";
import type { CameraError, ProjectMeta } from "../../types";

function errorTone(px: number | null): "good" | "warn" | "bad" | "neutral" {
  if (px == null) return "neutral";
  if (px < 0.5) return "good";
  if (px < 1.0) return "warn";
  return "bad";
}

function CameraCard({
  camera,
  uploaded,
  busy,
  error,
  onFiles,
}: {
  camera: string;
  uploaded: number;
  busy: boolean;
  error?: CameraError;
  onFiles: (files: File[]) => void;
}) {
  return (
    <div className="rounded-xl border border-line bg-bg p-3.5">
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[13px] font-semibold">{camera}</span>
        {error ? (
          <Badge tone={errorTone(error.reproj_error_px)}>
            {error.reproj_error_px != null ? `${error.reproj_error_px.toFixed(3)} px` : "—"}
          </Badge>
        ) : (
          uploaded > 0 && <Badge tone="good">ready</Badge>
        )}
      </div>
      <FileDrop
        accept="video/*,image/*"
        multiple
        busy={busy}
        done={uploaded ? `${uploaded} file${uploaded > 1 ? "s" : ""} uploaded` : null}
        label="Checkerboard video"
        onFiles={onFiles}
      />
      {error?.intrinsics_views != null && (
        <div className="mt-1.5 text-[11px] text-muted">
          intrinsics: {error.intrinsics_views} views
          {error.intrinsics_error_px != null && ` · ${error.intrinsics_error_px.toFixed(3)} px`}
        </div>
      )}
    </div>
  );
}

export function CalibrationStep({ project, goNext }: { project: ProjectMeta; goNext: () => void }) {
  const qc = useQueryClient();
  const { data: files } = useCalibrationFiles(project.id);
  const [jobId, setJobId] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const persistedJobId =
    project.job?.kind === "calibration" && (project.job.status === "queued" || project.job.status === "running")
      ? project.job.id
      : null;
  const activeJobId = jobId ?? persistedJobId;
  const invalidateFiles = () => qc.invalidateQueries({ queryKey: ["calibFiles", project.id] });

  const upload = useMutation({
    mutationFn: ({ camera, files }: { camera: string; files: File[] }) =>
      api.uploadIntrinsics(project.id, camera, files),
    onSuccess: invalidateFiles,
  });
  const uploadAll = useMutation({
    mutationFn: async (dropped: File[]) => {
      const sorted = [...dropped].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
      await Promise.all(
        project.cameras.map((cam, i) =>
          sorted[i] ? api.uploadIntrinsics(project.id, cam, [sorted[i]]) : Promise.resolve(),
        ),
      );
    },
    onSuccess: invalidateFiles,
  });
  const run = useMutation({
    mutationFn: () => api.runCalibration(project.id),
    onMutate: () => setLastError(null),
    onSuccess: (r) => {
      setJobId(r.job_id);
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Failed to start calibration.";
      if (persistedJobId && message.includes("already running")) {
        setJobId(persistedJobId);
        setLastError(null);
      } else {
        setLastError(message);
      }
    },
  });
  const accept = useMutation({
    mutationFn: () => api.acceptCalibration(project.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", project.id] });
      goNext();
    },
  });

  const ready = !!files && project.cameras.every((c) => (files.intrinsics[c]?.length ?? 0) > 0);
  const calib = project.calibration;
  const errorByCam = new Map(calib.cameras.map((c) => [c.camera, c]));
  const isDone = calib.status === "done" || calib.status === "accepted";
  const running = !!activeJobId && !isDone;

  const onJobDone = (status: "done" | "failed", error?: string | null) => {
    setJobId(null);
    if (status === "failed") setLastError(error ?? "Calibration failed.");
    qc.invalidateQueries({ queryKey: ["project", project.id] });
  };

  return (
    <Card>
      <CardHeader
        title="Camera calibration"
        desc="Upload one checkerboard video per camera. Lens calibration and camera placement are computed automatically."
        right={
          isDone ? (
            <Badge tone="good">calibrated</Badge>
          ) : (
            <Button onClick={() => run.mutate()} disabled={!ready || run.isPending || !!running}>
              {run.isPending || running ? "Calibrating…" : "Run calibration"}
            </Button>
          )
        }
      />
      <div className="space-y-4 p-5">
        <div className="rounded-lg border border-warn/30 bg-warn/8 px-3.5 py-2.5 text-[12px] text-ink">
          <b>Board:</b> {project.params.board_corners_h}×{project.params.board_corners_w} inner corners,{" "}
          {project.params.square_size_mm} mm squares. Inner corners are the intersections where black squares
          meet — if detection fails for a camera, this count is the usual culprit.
        </div>

        {!isDone && (
          <FileDrop
            accept="video/*"
            multiple
            busy={uploadAll.isPending}
            label={`Drop all ${project.cameras.length} checkerboard videos at once (assigned in filename order → ${project.cameras[0]}…${project.cameras[project.cameras.length - 1]})`}
            onFiles={(f) => uploadAll.mutate(f)}
          />
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {project.cameras.map((c) => (
            <CameraCard
              key={c}
              camera={c}
              uploaded={files?.intrinsics[c]?.length ?? 0}
              busy={upload.isPending && upload.variables?.camera === c}
              error={errorByCam.get(c)}
              onFiles={(f) => upload.mutate({ camera: c, files: f })}
            />
          ))}
        </div>

        {(upload.isError || uploadAll.isError) && (
          <p className="text-[13px] text-bad">
            Upload failed: {((upload.error ?? uploadAll.error) as Error).message}. If it says the
            session wasn’t found, it no longer exists — go back to “All sessions” and create a new one.
          </p>
        )}
        {(upload.isPending || uploadAll.isPending) && (
          <p className="text-[12px] text-muted">Uploading… large videos can take a moment.</p>
        )}

        {running && (
          <div className="rounded-xl border border-line p-4">
            <JobProgress projectId={project.id} jobId={activeJobId} onDone={onJobDone} />
          </div>
        )}

        {(calib.status === "failed" || !!lastError) && !running && (
          <div className="rounded-xl border border-bad/30 bg-bad/5 p-4">
            <p className="text-[13px] font-semibold text-bad">Calibration failed</p>
            <p className="mt-1 whitespace-pre-wrap text-[12px] text-bad/90">
              {lastError ?? calib.message ?? "Unknown error — see the log above."}
            </p>
            <Button className="mt-2" onClick={() => run.mutate()} disabled={run.isPending}>
              Try again
            </Button>
          </div>
        )}

        {isDone && (
          <div className="flex items-center justify-between rounded-xl border border-good/30 bg-good/5 px-4 py-3">
            <div className="text-[13px]">
              <b>Reprojection error</b> peaks at{" "}
              <span className="tabular">{calib.max_error_px?.toFixed(3) ?? "—"} px</span>.{" "}
              {calib.max_error_px != null && calib.max_error_px < 1
                ? "Good — well within tolerance."
                : "Above 1 px on a camera — its board frame may have been mistimed; re-shoot that camera for best accuracy."}
            </div>
            <Button onClick={() => accept.mutate()} disabled={accept.isPending}>
              Accept &amp; continue →
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
}
