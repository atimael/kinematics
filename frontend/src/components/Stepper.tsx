export type StepKey = "calibration" | "videos" | "processing" | "results";

const STEPS: { key: StepKey; label: string }[] = [
  { key: "calibration", label: "Calibration" },
  { key: "videos", label: "Trial videos" },
  { key: "processing", label: "Processing" },
  { key: "results", label: "Results" },
];

export function Stepper({
  active,
  reached,
  onJump,
}: {
  active: StepKey;
  reached: Set<StepKey>;
  onJump: (s: StepKey) => void;
}) {
  return (
    <ol className="flex flex-wrap items-center gap-y-2">
      {STEPS.map((s, i) => {
        const isActive = s.key === active;
        const isReached = reached.has(s.key);
        const clickable = isReached || isActive;
        return (
          <li key={s.key} className="flex items-center gap-2">
            <button
              disabled={!clickable}
              onClick={() => clickable && onJump(s.key)}
              className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-[13px] font-medium transition duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg ${
                clickable ? "active:scale-[0.97]" : "cursor-default"
              } ${
                isActive
                  ? "bg-brand text-white"
                  : isReached
                    ? "bg-brand-soft text-brand hover:opacity-80"
                    : "text-muted"
              }`}
            >
              <span
                className={`grid size-5 place-items-center rounded-full text-[11px] ${
                  isActive ? "bg-white/25" : isReached ? "bg-brand/15" : "bg-line"
                }`}
              >
                {i + 1}
              </span>
              {s.label}
            </button>
            {i < STEPS.length - 1 && <span className="h-px w-5 bg-line" />}
          </li>
        );
      })}
    </ol>
  );
}
