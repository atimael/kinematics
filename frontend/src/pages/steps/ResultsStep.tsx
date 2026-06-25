import { useResults } from "../../api/queries";
import { GaitReport } from "../../components/GaitReport";
import { Card, Spinner, Stat } from "../../components/ui";
import type { ProjectMeta } from "../../types";

export function ResultsStep({ project }: { project: ProjectMeta }) {
  const { data: summary, isLoading } = useResults(project.id, true);

  if (isLoading || !summary) {
    return (
      <Card>
        <div className="flex items-center gap-2 px-5 py-10 text-[13px] text-muted">
          <Spinner /> Loading results…
        </div>
      </Card>
    );
  }

  const calib = summary.calibration;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Frames" value={summary.n_frames ?? "—"} />
        <Stat label="Duration" value={summary.duration_s != null ? `${summary.duration_s}s` : "—"} />
        <Stat label="Frame rate" value={summary.frame_rate ? `${summary.frame_rate} fps` : "—"} />
        <Stat
          label="Max calib error"
          value={calib?.max_error_px != null ? `${calib.max_error_px.toFixed(3)} px` : "—"}
          tone={calib?.max_error_px != null && calib.max_error_px < 1 ? "good" : "warn"}
        />
      </div>

      <GaitReport projectId={project.id} />
    </div>
  );
}
