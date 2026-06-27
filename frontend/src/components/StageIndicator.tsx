export type StepKey = "calibration" | "videos" | "processing" | "results";

const STEPS: { key: StepKey; label: string }[] = [
  { key: "calibration", label: "Calibration" },
  { key: "videos", label: "Trial videos" },
  { key: "processing", label: "Processing" },
  { key: "results", label: "Results" },
];

export const STEP_ORDER = STEPS.map((s) => s.key);

export function StageIndicator({ active }: { active: StepKey }) {
  const idx = STEPS.findIndex((s) => s.key === active);
  const step = STEPS[idx];
  if (!step) return null;

  return (
    <div className="flex items-center gap-2 rounded-full bg-brand px-3 py-1.5 text-[13px] font-medium text-white">
      <span className="grid size-5 place-items-center rounded-full bg-white/25 text-[11px]">{idx + 1}</span>
      {step.label}
      <span className="text-[11px] font-normal text-white/70">
        Step {idx + 1} of {STEPS.length}
      </span>
    </div>
  );
}
