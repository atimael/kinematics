import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { JobProgress } from "../../components/JobProgress";
import { Button, Card, CardHeader, Spinner } from "../../components/ui";
import type { ProjectMeta } from "../../types";

const STAGE_ORDER = [
  "poseEstimation",
  "synchronization",
  "personAssociation",
  "triangulation",
  "filtering",
  "markerAugmentation",
  "kinematics",
];

export function ProcessingStep({ project, goResults }: { project: ProjectMeta; goResults: () => void }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["currentJob", project.id],
    queryFn: () => api.currentJob(project.id),
    refetchInterval: (q) => (q.state.data?.job?.id ? false : 1500),
  });

  const job = data?.job;
  const failed = project.status === "failed" || job?.status === "failed";
  const done = project.status === "processed";

  const onDone = (status: "done" | "failed") => {
    qc.invalidateQueries({ queryKey: ["project", project.id] });
    qc.invalidateQueries({ queryKey: ["results", project.id] });
    if (status === "done") goResults();
  };

  return (
    <Card>
      <CardHeader
        title="Processing"
        desc="Markerless pipeline: pose → triangulation → filtering → OpenSim inverse kinematics. CPU inference takes a few minutes per clip."
      />
      <div className="space-y-4 p-5">
        <ol className="flex flex-wrap gap-2 text-[12px]">
          {STAGE_ORDER.filter(
            (s) =>
              (s !== "synchronization" || project.params.do_synchronization) &&
              (s !== "markerAugmentation" || project.params.do_marker_augmentation),
          ).map((s) => (
            <li key={s} className="rounded-full border border-line bg-bg px-2.5 py-1 text-muted">
              {s}
            </li>
          ))}
        </ol>

        {!done && (isLoading || (!job && !failed)) ? (
          <div className="flex items-center gap-2 text-[13px] text-muted">
            <Spinner /> Starting worker…
          </div>
        ) : job && !done ? (
          <div className="rounded-xl border border-line p-4">
            <JobProgress projectId={project.id} jobId={job.id} onDone={onDone} />
          </div>
        ) : null}

        {failed && (
          <p className="text-[13px] text-bad">
            Processing failed{job?.error ? `: ${job.error}` : "."} Check that calibration is accurate and the clips
            overlap in time.
          </p>
        )}

        {project.status === "processed" && (
          <div className="flex justify-end">
            <Button onClick={goResults}>View results →</Button>
          </div>
        )}
      </div>
    </Card>
  );
}
