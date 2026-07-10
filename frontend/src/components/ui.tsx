import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg";

type Tone = "neutral" | "good" | "warn" | "bad" | "brand";

const toneText: Record<Tone, string> = {
  neutral: "text-muted",
  good: "text-good",
  warn: "text-warn",
  bad: "text-bad",
  brand: "text-brand",
};
const toneBg: Record<Tone, string> = {
  neutral: "bg-line/60 text-ink",
  good: "bg-good/12 text-good",
  warn: "bg-warn/15 text-warn",
  bad: "bg-bad/12 text-bad",
  brand: "bg-brand-soft text-brand",
};

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-line bg-surface shadow-[0_1px_2px_rgba(16,24,40,0.04)] ${className}`}>
      {children}
    </div>
  );
}

export function CardHeader({ title, desc, right }: { title: string; desc?: string; right?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
      <div>
        <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
        {desc && <p className="mt-0.5 text-[13px] text-muted">{desc}</p>}
      </div>
      {right}
    </div>
  );
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "subtle" | "danger" }) {
  const styles = {
    primary: "bg-brand text-white hover:opacity-90 disabled:opacity-40",
    subtle: "bg-brand-soft text-brand hover:bg-brand-soft/70 disabled:opacity-40",
    ghost: "text-ink hover:bg-line/50 disabled:opacity-40",
    danger: "text-bad hover:bg-bad/10 disabled:opacity-40",
  }[variant];
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-[13px] font-medium transition duration-150 ease-out active:scale-[0.97] disabled:cursor-not-allowed disabled:active:scale-100 ${focusRing} ${styles} ${className}`}
      {...props}
    />
  );
}

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[12px] font-medium ${toneBg[tone]}`}>
      {children}
    </span>
  );
}

export function Field({
  label,
  hint,
  children,
  className = "",
  labelClassName = "",
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
  labelClassName?: string;
}) {
  return (
    <label className={`flex min-w-0 flex-col ${className}`}>
      <div className={`mb-1.5 text-[13px] font-medium leading-5 text-ink ${labelClassName}`}>{label}</div>
      {children}
      {hint && <div className="mt-1 text-[12px] leading-snug text-muted">{hint}</div>}
    </label>
  );
}

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`h-10 w-full rounded-lg border border-line bg-surface px-3 text-[14px] leading-none tabular outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/15 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      {...props}
    />
  );
}

export function Select({ className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        className={`h-10 w-full appearance-none rounded-lg border border-line bg-surface px-3 pr-9 text-[14px] text-ink outline-none transition-[border-color,box-shadow] duration-150 ease-out focus:border-brand focus:ring-2 focus:ring-brand/15 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
        {...props}
      >
        {children}
      </select>
      <svg
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted"
      >
        <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`spin inline-block size-4 rounded-full border-2 border-current border-t-transparent ${className}`}
      aria-hidden
    />
  );
}

export function Stat({ label, value, tone = "neutral" }: { label: string; value: ReactNode; tone?: Tone }) {
  return (
    <div className="rounded-xl border border-line bg-bg px-4 py-3">
      <div className="text-[12px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 text-[20px] font-semibold tabular ${toneText[tone]}`}>{value}</div>
    </div>
  );
}

export function ProgressBar({ pct }: { pct: number }) {
  const clamped = Math.max(2, Math.min(100, pct));
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-line"
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full w-full origin-left rounded-full bg-brand transition-transform duration-300 ease-out"
        style={{ transform: `scaleX(${clamped / 100})` }}
      />
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`flex w-full items-center justify-between gap-4 rounded-lg border border-line bg-surface px-3.5 py-2.5 text-left transition-colors duration-150 ease-out hover:border-brand/40 ${focusRing}`}
    >
      <span>
        <span className="block text-[13px] font-medium">{label}</span>
        {hint && <span className="block text-[12px] text-muted">{hint}</span>}
      </span>
      <span className={`relative h-5 w-9 shrink-0 rounded-full transition-colors duration-200 ease-out ${checked ? "bg-brand" : "bg-line"}`}>
        <span
          className={`absolute left-0.5 top-0.5 size-4 rounded-full bg-white shadow transition-transform duration-200 ease-out ${checked ? "translate-x-4" : "translate-x-0"}`}
        />
      </span>
    </button>
  );
}
