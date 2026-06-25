import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useVideos } from "../../api/queries";
import { FileDrop } from "../../components/FileDrop";
import { Button, Card, CardHeader } from "../../components/ui";
import type { ProjectMeta } from "../../types";

function VideoSlot({ project, camera, current }: { project: ProjectMeta; camera: string; current: string | null }) {
  const qc = useQueryClient();
  const up = useMutation({
    mutationFn: (file: File) => api.uploadVideo(project.id, camera, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["videos", project.id] }),
  });
  return (
    <div className="rounded-xl border border-line bg-bg p-3.5">
      <div className="mb-2 text-[13px] font-semibold">{camera}</div>
      <FileDrop accept="video/*" busy={up.isPending} done={current} label="Trial video" onFiles={(f) => up.mutate(f[0])} />
    </div>
  );
}

export function TrialVideosStep({ project, goNext }: { project: ProjectMeta; goNext: () => void }) {
  const { data: videos } = useVideos(project.id);
  const start = useMutation({ mutationFn: () => api.runProcessing(project.id), onSuccess: goNext });

  const ready = videos && project.cameras.every((c) => videos[c]);

  return (
    <Card>
      <CardHeader
        title="Trial videos"
        desc="One synchronized clip per camera of the movement to analyze."
        right={
          <Button onClick={() => start.mutate()} disabled={!ready || start.isPending}>
            {start.isPending ? "Starting…" : "Start processing →"}
          </Button>
        }
      />
      <div className="space-y-4 p-5">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {project.cameras.map((c) => (
            <VideoSlot key={c} project={project} camera={c} current={videos?.[c] ?? null} />
          ))}
        </div>
        {start.isError && <p className="text-[13px] text-bad">{(start.error as Error).message}</p>}
        {!ready && <p className="text-[12px] text-muted">Upload a video for every camera to enable processing.</p>}
      </div>
    </Card>
  );
}
