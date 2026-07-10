import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import { useCreateProject } from "../api/queries";
import type { ProjectParams } from "../types";
import { Button, Card, CardHeader, Field, Input, Select, Toggle } from "./ui";

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

  const set = <K extends keyof ProjectParams>(k: K, v: ProjectParams[K] | null | undefined) =>
    setP((prev) => ({ ...prev, [k]: v }));
  const num = (v: string): number | null => (v === "" ? null : Number(v));
  const numU = (v: string): number | undefined => (v === "" ? undefined : Number(v));

  const clampInt = (v: number | undefined, min: number, max: number, def: number) => {
    const n = typeof v === "number" && Number.isFinite(v) ? Math.round(v) : def;
    return Math.min(max, Math.max(min, n));
  };
  const positive = (v: number | undefined, def: number) =>
    typeof v === "number" && Number.isFinite(v) && v > 0 ? v : def;

  const submit = () => {
    if (!p.name?.trim()) return;
    // Guarantee a schema-valid payload: cleared numeric fields would otherwise
    // send 0/NaN and the API rejects them with a 422.
    const payload: Partial<ProjectParams> = {
      ...p,
      name: p.name.trim(),
      n_cameras: clampInt(p.n_cameras, 2, 12, 4),
      board_corners_h: clampInt(p.board_corners_h, 3, 30, 6),
      board_corners_w: clampInt(p.board_corners_w, 3, 30, 7),
      square_size_mm: positive(p.square_size_mm, 105),
      filter_cutoff_hz: positive(p.filter_cutoff_hz, 6),
    };
    create.mutate(payload, { onSuccess: (proj) => nav(`/projects/${proj.id}`) });
  };

  return (
    <Card className="capture-form">
      <CardHeader title="New capture session" desc="Multi-camera markerless 3D kinematics" />
      <div className="space-y-5 p-5">
        <div className="capture-form-primary grid gap-4">
          <Field label="Session name">
            <Input value={p.name ?? ""} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Subject A — gait" />
          </Field>
          <Field label="Number of cameras" hint="2 minimum; 3–4+ gives accurate triangulation">
            <Input className="text-center" type="number" min={2} max={12} value={p.n_cameras ?? ""} onChange={(e) => set("n_cameras", numU(e.target.value))} />
          </Field>
        </div>

        <fieldset className="border-y border-line py-4">
          <legend className="px-1 text-[13px] font-semibold">Checkerboard</legend>
          <div className="checkerboard-fields grid gap-4">
            <Field className="checkerboard-corners" label="Inner corners (H × W)" hint="Intersections where squares meet, not the square count">
              <div className="grid w-full grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2">
                <Input
                  type="number"
                  inputMode="numeric"
                  min={3}
                  aria-label="Checkerboard inner corners horizontally"
                  className="min-w-0 text-center font-semibold text-ink caret-brand"
                  value={p.board_corners_h ?? ""}
                  onChange={(e) => set("board_corners_h", numU(e.target.value))}
                />
                <span className="text-[17px] font-medium text-muted" aria-hidden>×</span>
                <Input
                  type="number"
                  inputMode="numeric"
                  min={3}
                  aria-label="Checkerboard inner corners vertically"
                  className="min-w-0 text-center font-semibold text-ink caret-brand"
                  value={p.board_corners_w ?? ""}
                  onChange={(e) => set("board_corners_w", numU(e.target.value))}
                />
              </div>
            </Field>
            <Field label="Square size (mm)">
              <Input className="text-center" type="number" step="0.1" value={p.square_size_mm ?? ""} onChange={(e) => set("square_size_mm", numU(e.target.value))} />
            </Field>
            <Field label="Board placement">
              <Select
                value={p.board_position}
                onChange={(e) => set("board_position", e.target.value as ProjectParams["board_position"])}
              >
                <option value="horizontal">Horizontal (on floor)</option>
                <option value="vertical">Vertical</option>
              </Select>
            </Field>
          </div>
        </fieldset>

        <div className="participant-fields grid gap-4">
          <Field label="Participant height (m)" hint="Measured value improves scaling">
            <Input className="text-center" type="number" step="0.01" placeholder="auto" value={p.participant_height_m ?? ""} onChange={(e) => set("participant_height_m", num(e.target.value))} />
          </Field>
          <Field label="Participant mass (kg)">
            <Input className="text-center" type="number" step="0.1" placeholder="70" value={p.participant_mass_kg ?? ""} onChange={(e) => set("participant_mass_kg", num(e.target.value))} />
          </Field>
          <Field label="Frame rate (fps)" hint="Leave blank to auto-detect">
            <Input className="text-center" type="number" step="1" placeholder="auto" value={p.frame_rate ?? ""} onChange={(e) => set("frame_rate", num(e.target.value))} />
          </Field>
        </div>

        <Toggle
          checked={p.do_synchronization ?? true}
          onChange={(v) => set("do_synchronization", v)}
          label="Run automatic camera synchronization"
          hint="Keep on unless cameras are hardware-genlocked. Needs a sharp common motion near each clip's start."
        />

        <button
          type="button"
          onClick={() => setAdvanced((a) => !a)}
          aria-expanded={advanced}
          className="inline-flex items-center gap-1.5 rounded-md text-[13px] font-medium text-brand transition-opacity duration-150 ease-out hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
        >
          <ChevronDown aria-hidden className={`size-3.5 transition-transform duration-200 ease-out ${advanced ? "rotate-180" : ""}`} />
          Advanced options
        </button>
        {advanced && (
          <div className="reveal grid gap-4 sm:grid-cols-2">
            <Field label="Pose estimation mode" hint="Higher = more accurate, slower (CPU)">
              <Select
                value={p.pose_mode}
                onChange={(e) => set("pose_mode", e.target.value as ProjectParams["pose_mode"])}
              >
                <option value="lightweight">Lightweight</option>
                <option value="balanced">Balanced</option>
                <option value="performance">Performance</option>
              </Select>
            </Field>
            <Field label="Filter cut-off (Hz)" hint="Butterworth low-pass; 6 Hz is the biomech default">
              <Input className="text-center" type="number" step="0.5" value={p.filter_cutoff_hz ?? ""} onChange={(e) => set("filter_cutoff_hz", numU(e.target.value))} />
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
