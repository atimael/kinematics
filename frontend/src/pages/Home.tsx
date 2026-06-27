import { Link } from "react-router-dom";
import { useDeleteProject, useProjects } from "../api/queries";
import { NewProjectForm } from "../components/NewProjectForm";
import { Badge, Card, Spinner } from "../components/ui";
import type { ProjectMeta, ProjectStatus } from "../types";

const STATUS_TONE: Record<ProjectStatus, "neutral" | "brand" | "good" | "bad"> = {
  created: "neutral",
  calibrated: "brand",
  processing: "brand",
  processed: "good",
  failed: "bad",
};

function ProjectRow({ p, onDelete }: { p: ProjectMeta; onDelete: (id: string) => void }) {
  return (
    <div className="group flex items-center justify-between gap-4 px-5 py-3.5 transition-colors duration-150 ease-out hover:bg-bg">
      <Link
        to={`/projects/${p.id}`}
        className="min-w-0 flex-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
      >
        <div className="flex items-center gap-2.5">
          <span className="truncate text-[14px] font-medium">{p.params.name}</span>
          <Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge>
        </div>
        <div className="mt-0.5 text-[12px] text-muted">
          {p.cameras.length} cameras · {p.params.board_corners_h}×{p.params.board_corners_w} board ·{" "}
          {p.params.square_size_mm} mm
        </div>
      </Link>
      <button
        onClick={() => onDelete(p.id)}
        className="rounded-md px-1.5 py-1 text-[12px] text-muted transition-colors duration-150 ease-out hover:text-bad focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bad/40"
      >
        Delete
      </button>
    </div>
  );
}

export default function Home() {
  const { data: projects, isLoading } = useProjects();
  const del = useDeleteProject();

  const onDelete = (id: string) => {
    if (confirm("Delete this session and all its data?")) del.mutate(id);
  };

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_minmax(380px,440px)]">
      <section>
        <h1 className="mb-1 text-[22px] font-semibold tracking-tight">Capture sessions</h1>
        <p className="mb-4 text-[14px] text-muted">
          Calibrate your cameras, process trial videos, and export 3D kinematics.
        </p>
        <Card>
          {isLoading ? (
            <div className="flex items-center gap-2 px-5 py-8 text-[13px] text-muted">
              <Spinner /> Loading…
            </div>
          ) : projects && projects.length ? (
            <div className="divide-y divide-line">
              {projects.map((p) => (
                <ProjectRow key={p.id} p={p} onDelete={onDelete} />
              ))}
            </div>
          ) : (
            <div className="px-5 py-10 text-center text-[14px] text-muted">
              No sessions yet — create one to get started.
            </div>
          )}
        </Card>
      </section>
      <section>
        <NewProjectForm />
      </section>
    </div>
  );
}
