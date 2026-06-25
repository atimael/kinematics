import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

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
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-[13px] font-medium transition disabled:cursor-not-allowed ${styles} ${className}`}
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
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <div className="mb-1 text-[13px] font-medium text-ink">{label}</div>
      {children}
      {hint && <div className="mt-1 text-[12px] leading-snug text-muted">{hint}</div>}
    </label>
  );
}

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`w-full rounded-lg border border-line bg-surface px-3 py-2 text-[14px] tabular outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/15 ${className}`}
      {...props}
    />
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
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-line">
      <div
        className="h-full rounded-full bg-brand transition-[width] duration-300"
        style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
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
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-4 rounded-lg border border-line bg-surface px-3.5 py-2.5 text-left"
    >
      <span>
        <span className="block text-[13px] font-medium">{label}</span>
        {hint && <span className="block text-[12px] text-muted">{hint}</span>}
      </span>
      <span className={`relative h-5 w-9 shrink-0 rounded-full transition ${checked ? "bg-brand" : "bg-line"}`}>
        <span
          className={`absolute top-0.5 size-4 rounded-full bg-white shadow transition-[left] ${checked ? "left-[18px]" : "left-0.5"}`}
        />
      </span>
    </button>
  );
}
