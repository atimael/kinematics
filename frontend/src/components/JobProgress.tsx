import { useRef } from "react";
import { useJobStream } from "../api/queries";
import { ProgressBar, Spinner } from "./ui";

const STAGE_LABELS: Record<string, string> = {
  calibration: "Calibrating cameras",
  poseEstimation: "Estimating 2D pose",
  synchronization: "Synchronizing cameras",
  personAssociation: "Associating person across views",
  triangulation: "Triangulating to 3D",
  filtering: "Filtering trajectories",
  markerAugmentation: "Augmenting markers (LSTM)",
  kinematics: "OpenSim scaling + inverse kinematics",
};

export function JobProgress({
  projectId,
  jobId,
  onDone,
}: {
  projectId: string;
  jobId: string;
  onDone: (status: "done" | "failed", error?: string | null) => void;
}) {
  const job = useJobStream(projectId, jobId, () => undefined);
  const firedRef = useRef(false);

  // Finalize exactly once when the stream reports a terminal status.
  if ((job.status === "done" || job.status === "failed") && !firedRef.current) {
    firedRef.current = true;
    queueMicrotask(() => onDone(job.status as "done" | "failed", job.error));
  }

  const label = job.stage ? (STAGE_LABELS[job.stage] ?? job.stage) : "Starting…";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-[13px]">
        <span className="flex items-center gap-2 font-medium">
          {job.status === "running" && <Spinner className="text-brand" />}
          {label}
        </span>
        <span className="tabular text-muted">{Math.round(job.pct)}%</span>
      </div>
      <ProgressBar pct={job.pct} />
      {job.logs.length > 0 && (
        <pre className="max-h-40 overflow-auto rounded-lg border border-line bg-bg p-3 text-[11px] leading-relaxed text-muted">
          {job.logs.slice(-10).join("\n")}
        </pre>
      )}
      {job.error && (
        <pre className="overflow-auto rounded-lg border border-bad/30 bg-bad/5 p-3 text-[12px] text-bad">{job.error}</pre>
      )}
    </div>
  );
}
