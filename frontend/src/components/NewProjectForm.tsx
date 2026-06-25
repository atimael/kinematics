import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateProject } from "../api/queries";
import type { ProjectParams } from "../types";
import { Button, Card, CardHeader, Field, Input, Toggle } from "./ui";

const DEFAULTS: Partial<ProjectParams> = {
  name: "",
  n_cameras: 4,
  board_corners_h: 6,
  board_corners_w: 7,
  square_size_mm: 105,
  board_position: "horizontal",
  participant_height_m: null,
  participant_mass_kg: null,
  frame_rate: null,
  do_synchronization: true,
  do_marker_augmentation: true,
  use_simple_model: false,
  filter_cutoff_hz: 6,
  pose_mode: "balanced",
};

export function NewProjectForm() {
  const [p, setP] = useState<Partial<ProjectParams>>(DEFAULTS);
  const [advanced, setAdvanced] = useState(false);
  const create = useCreateProject();
  const nav = useNavigate();

  const set = <K extends keyof ProjectParams>(k: K, v: ProjectParams[K] | null) =>
    setP((prev) => ({ ...prev, [k]: v }));
  const num = (v: string): number | null => (v === "" ? null : Number(v));

  const submit = () => {
    if (!p.name?.trim()) return;
    create.mutate(p, { onSuccess: (proj) => nav(`/projects/${proj.id}`) });
  };

  return (
    <Card>
      <CardHeader title="New capture session" desc="Multi-camera markerless 3D kinematics" />
      <div className="space-y-5 p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Session name">
            <Input value={p.name ?? ""} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Subject A — gait" />
          </Field>
          <Field label="Number of cameras" hint="2 minimum; 3–4+ gives accurate triangulation">
            <Input type="number" min={2} max={12} value={p.n_cameras ?? 4} onChange={(e) => set("n_cameras", Number(e.target.value))} />
          </Field>
        </div>

        <div className="rounded-xl border border-line bg-bg p-4">
          <div className="mb-3 text-[13px] font-semibold">Checkerboard</div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Inner corners (H × W)" hint="Intersections where squares meet — not the square count">
              <div className="flex items-center gap-2">
                <Input type="number" min={3} value={p.board_corners_h ?? 6} onChange={(e) => set("board_corners_h", Number(e.target.value))} />
                <span className="text-muted">×</span>
                <Input type="number" min={3} value={p.board_corners_w ?? 7} onChange={(e) => set("board_corners_w", Number(e.target.value))} />
              </div>
            </Field>
            <Field label="Square size (mm)">
              <Input type="number" step="0.1" value={p.square_size_mm ?? 105} onChange={(e) => set("square_size_mm", Number(e.target.value))} />
            </Field>
            <Field label="Board placement">
              <select
                value={p.board_position}
                onChange={(e) => set("board_position", e.target.value as ProjectParams["board_position"])}
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[14px] outline-none focus:border-brand"
              >
                <option value="horizontal">Horizontal (on floor)</option>
                <option value="vertical">Vertical</option>
              </select>
            </Field>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Participant height (m)" hint="Measured → accurate scaling">
            <Input type="number" step="0.01" placeholder="auto" value={p.participant_height_m ?? ""} onChange={(e) => set("participant_height_m", num(e.target.value))} />
          </Field>
          <Field label="Participant mass (kg)">
            <Input type="number" step="0.1" placeholder="70" value={p.participant_mass_kg ?? ""} onChange={(e) => set("participant_mass_kg", num(e.target.value))} />
          </Field>
          <Field label="Frame rate (fps)" hint="Blank → auto-detect">
            <Input type="number" step="1" placeholder="auto" value={p.frame_rate ?? ""} onChange={(e) => set("frame_rate", num(e.target.value))} />
          </Field>
        </div>

        <Toggle
          checked={p.do_synchronization ?? true}
          onChange={(v) => set("do_synchronization", v)}
          label="Run automatic camera synchronization"
          hint="Keep on unless cameras are hardware-genlocked. Needs a sharp common motion near each clip's start."
        />

        <button onClick={() => setAdvanced((a) => !a)} className="text-[13px] font-medium text-brand">
          {advanced ? "− Hide" : "+ Show"} advanced options
        </button>
        {advanced && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Pose estimation mode" hint="Higher = more accurate, slower (CPU)">
              <select
                value={p.pose_mode}
                onChange={(e) => set("pose_mode", e.target.value as ProjectParams["pose_mode"])}
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[14px] outline-none focus:border-brand"
              >
                <option value="lightweight">Lightweight</option>
                <option value="balanced">Balanced</option>
                <option value="performance">Performance</option>
              </select>
            </Field>
            <Field label="Filter cut-off (Hz)" hint="Butterworth low-pass; 6 Hz is the biomech default">
              <Input type="number" step="0.5" value={p.filter_cutoff_hz ?? 6} onChange={(e) => set("filter_cutoff_hz", Number(e.target.value))} />
            </Field>
            <Toggle checked={p.do_marker_augmentation ?? true} onChange={(v) => set("do_marker_augmentation", v)} label="LSTM marker augmentation" hint="Improves anatomical markers (esp. <4 cameras)" />
            <Toggle checked={p.use_simple_model ?? false} onChange={(v) => set("use_simple_model", v)} label="Fast (simplified) IK model" hint="10× faster, less accurate. Off = full OpenSim model." />
          </div>
        )}

        {create.isError && <p className="text-[13px] text-bad">{(create.error as Error).message}</p>}
        <div className="flex justify-end">
          <Button onClick={submit} disabled={!p.name?.trim() || create.isPending}>
            {create.isPending ? "Creating…" : "Create session →"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
