import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Crosshair, X } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useVideos } from "../../api/queries";
import { FileDrop } from "../../components/FileDrop";
import { Badge, Button, Card, CardHeader } from "../../components/ui";
import type { ProjectMeta, SubjectSelection } from "../../types";

interface VideoContentRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

function videoContentRect(container: HTMLDivElement, video: HTMLVideoElement): VideoContentRect {
  const width = container.clientWidth;
  const height = container.clientHeight;
  if (!video.videoWidth || !video.videoHeight) return { left: 0, top: 0, width, height };
  const scale = Math.min(width / video.videoWidth, height / video.videoHeight);
  const contentWidth = video.videoWidth * scale;
  const contentHeight = video.videoHeight * scale;
  return {
    left: (width - contentWidth) / 2,
    top: (height - contentHeight) / 2,
    width: contentWidth,
    height: contentHeight,
  };
}

function VideoSlot({
  project,
  camera,
  current,
  selection,
}: {
  project: ProjectMeta;
  camera: string;
  current: string | null;
  selection?: SubjectSelection;
}) {
  const qc = useQueryClient();
  const videoRef = useRef<HTMLVideoElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [picking, setPicking] = useState(false);
  const [videoVersion, setVideoVersion] = useState(0);
  const [layoutVersion, setLayoutVersion] = useState(0);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const observer = new ResizeObserver(() => setLayoutVersion((value) => value + 1));
    observer.observe(frame);
    return () => observer.disconnect();
  }, [current]);

  const updateProject = (meta: ProjectMeta) => {
    qc.setQueryData(["project", project.id], meta);
  };
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadVideo(project.id, camera, file),
    onSuccess: () => {
      setPicking(false);
      setVideoVersion(Date.now());
      qc.invalidateQueries({ queryKey: ["videos", project.id] });
      qc.invalidateQueries({ queryKey: ["project", project.id] });
    },
  });
  const choose = useMutation({
    mutationFn: (value: SubjectSelection) => api.selectSubject(project.id, camera, value),
    onSuccess: (meta) => {
      setPicking(false);
      updateProject(meta);
    },
  });
  const clear = useMutation({
    mutationFn: () => api.clearSubjectSelection(project.id, camera),
    onSuccess: updateProject,
  });

  const beginPicking = () => {
    videoRef.current?.pause();
    setPicking(true);
  };

  const saveClick = (event: MouseEvent<HTMLButtonElement>) => {
    const frame = frameRef.current;
    const video = videoRef.current;
    if (!frame || !video) return;
    const bounds = frame.getBoundingClientRect();
    const content = videoContentRect(frame, video);
    const x = (event.clientX - bounds.left - content.left) / content.width;
    const y = (event.clientY - bounds.top - content.top) / content.height;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    choose.mutate({ x, y, time_s: video.currentTime });
  };

  const marker = (() => {
    void layoutVersion;
    const frame = frameRef.current;
    const video = videoRef.current;
    if (!selection || !frame || !video) return null;
    const content = videoContentRect(frame, video);
    return {
      left: content.left + selection.x * content.width,
      top: content.top + selection.y * content.height,
    };
  })();

  const error = upload.error ?? choose.error ?? clear.error;

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-bg">
      <div className="flex items-center justify-between px-3.5 py-3">
        <span className="text-[13px] font-semibold">{camera}</span>
        {selection && <Badge tone="good">subject selected</Badge>}
      </div>

      {current && (
        <div ref={frameRef} className="relative aspect-video overflow-hidden bg-black">
          <video
            key={`${current}-${videoVersion}`}
            ref={videoRef}
            className="size-full object-contain"
            src={`${api.videoUrl(project.id, camera)}?v=${videoVersion}`}
            controls={!picking}
            playsInline
            preload="metadata"
            onLoadedMetadata={() => setLayoutVersion((value) => value + 1)}
          />
          {marker && (
            <span
              className="pointer-events-none absolute z-10 grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-white bg-brand text-white shadow-lg"
              style={marker}
              aria-hidden
            >
              <Crosshair size={17} strokeWidth={2.5} />
            </span>
          )}
          {picking && (
            <button
              type="button"
              className="absolute inset-0 z-20 cursor-crosshair bg-black/15 text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white"
              onClick={saveClick}
              aria-label={`Select subject in ${camera}`}
            >
              <span className="absolute left-3 top-3 rounded-md bg-black/70 px-2.5 py-1.5 text-[12px] font-medium">
                Click the subject
              </span>
            </button>
          )}
        </div>
      )}

      <div className="space-y-3 p-3.5">
        {current && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant={picking ? "subtle" : "ghost"}
              className="px-2.5 py-1.5"
              onClick={picking ? () => setPicking(false) : beginPicking}
              disabled={choose.isPending}
            >
              {picking ? <X size={15} /> : <Crosshair size={15} />}
              {picking ? "Cancel" : selection ? "Change subject" : "Select subject"}
            </Button>
            {selection && (
              <Button variant="ghost" className="px-2.5 py-1.5 text-muted" onClick={() => clear.mutate()} disabled={clear.isPending}>
                <X size={15} />
                Clear
              </Button>
            )}
            {selection && <span className="ml-auto text-[11px] tabular text-muted">{selection.time_s.toFixed(2)}s</span>}
          </div>
        )}
        <FileDrop
          accept="video/*"
          busy={upload.isPending}
          done={current}
          label={current ? "Replace trial video" : "Trial video"}
          onFiles={(files) => upload.mutate(files[0])}
        />
        {error && <p className="text-[12px] text-bad">{(error as Error).message}</p>}
      </div>
    </div>
  );
}

export function TrialVideosStep({ project, goNext }: { project: ProjectMeta; goNext: () => void }) {
  const { data: videos } = useVideos(project.id);
  const start = useMutation({ mutationFn: () => api.runProcessing(project.id), onSuccess: goNext });

  const ready = !!videos && project.cameras.every((camera) => videos[camera]);
  const selections = project.subject_selections ?? {};
  const selectedCount = project.cameras.filter((camera) => selections[camera]).length;
  const selectionIncomplete = selectedCount > 0 && selectedCount < project.cameras.length;

  return (
    <Card>
      <CardHeader
        title="Trial videos"
        desc="One synchronized clip per camera of the movement to analyze."
        right={
          <Button onClick={() => start.mutate()} disabled={!ready || selectionIncomplete || start.isPending}>
            {start.isPending ? "Starting…" : "Start processing →"}
          </Button>
        }
      />
      <div className="space-y-4 p-5">
        <div className="grid gap-3 md:grid-cols-2">
          {project.cameras.map((camera) => (
            <VideoSlot
              key={camera}
              project={project}
              camera={camera}
              current={videos?.[camera] ?? null}
              selection={selections[camera]}
            />
          ))}
        </div>
        {start.isError && <p className="text-[13px] text-bad">{(start.error as Error).message}</p>}
        {!ready && <p className="text-[12px] text-muted">Upload a video for every camera to enable processing.</p>}
        {selectionIncomplete && (
          <p className="text-[12px] text-warn">Select the subject in every camera, or clear the existing selections.</p>
        )}
      </div>
    </Card>
  );
}
