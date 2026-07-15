export interface ProjectParams {
  name: string;
  n_cameras: number;
  board_corners_h: number;
  board_corners_w: number;
  square_size_mm: number;
  board_position: "horizontal" | "vertical";
  participant_height_m: number | null;
  participant_mass_kg: number | null;
  frame_rate: number | null;
  multi_person: boolean;
  do_synchronization: boolean;
  do_marker_augmentation: boolean;
  use_simple_model: boolean;
  filter_cutoff_hz: number;
  pose_model: string;
  pose_mode: "lightweight" | "balanced" | "performance";
  intrinsics_extension: string;
  extrinsics_extension: string;
  video_extension: string;
}

export interface CameraError {
  camera: string;
  reproj_error_px: number | null;
  intrinsics_error_px: number | null;
  intrinsics_views: number | null;
  board_detected: boolean | null;
}

export interface SubjectSelection {
  x: number;
  y: number;
  time_s: number;
}

export type CalibStatus = "pending" | "running" | "done" | "failed" | "accepted";

export interface CalibrationResult {
  status: CalibStatus;
  calib_file: string | null;
  cameras: CameraError[];
  max_error_px: number | null;
  message: string | null;
}

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface JobState {
  id: string;
  kind: "calibration" | "processing";
  status: JobStatus;
  stages: string[];
  current_stage: string | null;
  pct: number;
  error: string | null;
}

export type ProjectStatus = "created" | "calibrated" | "processing" | "processed" | "failed";

export interface ProjectMeta {
  id: string;
  params: ProjectParams;
  cameras: string[];
  status: ProjectStatus;
  calibration: CalibrationResult;
  subject_selections: Record<string, SubjectSelection>;
  job: JobState | null;
}

export interface ResultsSummary {
  has_angles: boolean;
  has_positions: boolean;
  n_frames: number | null;
  duration_s: number | null;
  frame_rate: number | null;
  angle_columns: string[];
  marker_names: string[];
  calibration: CalibrationResult | null;
}

export interface ChartData {
  unit: string;
  time: number[];
  series: Record<string, (number | null)[]>;
  columns?: string[];
  markers?: string[];
  labels?: Record<string, { label: string; unit: string }>;
  marker_labels?: Record<string, string>;
}

export interface AngleRow {
  key: string;
  label: string;
  unit: string;
  min: number;
  max: number;
  mean: number;
  range: number;
  peak_vel: number;
}

export interface GaitRow {
  label: string;
  unit: string;
  value: number | null;
  robust?: boolean;
  derived?: boolean;
}

export interface GaitReport {
  n_steps: number;
  n_strides: { r: number; l: number };
  duration_s: number;
  cadence_steps_min: number | null;
  walking_speed_ms: number | null;
  spatiotemporal: GaitRow[];
  kinematics: GaitRow[];
  enough_steps: boolean;
  analyzed_frames?: number;
  source_frames?: number | null;
  coverage?: number;
  truncated?: boolean;
}

export interface JobEvent {
  type: "stage" | "log" | "calib" | "job" | "end";
  stage?: string;
  status?: string;
  pct?: number;
  msg?: string;
  error?: string;
  px?: number[];
  mm?: number[];
}
