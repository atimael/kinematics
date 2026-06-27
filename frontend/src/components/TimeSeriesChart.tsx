import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartData } from "../types";

const PALETTE = [
  "#4f46e5",
  "#0891b2",
  "#16a34a",
  "#ea580c",
  "#db2777",
  "#7c3aed",
  "#ca8a04",
  "#0d9488",
];

export function TimeSeriesChart({
  data,
  yLabel,
  labelMap,
}: {
  data: ChartData;
  yLabel: string;
  labelMap?: Record<string, string>;
}) {
  const keys = Object.keys(data.series);
  const name = (k: string) => labelMap?.[k] ?? k;
  const rows = data.time.map((t, i) => {
    const row: Record<string, number | null> = { time: Number(t.toFixed(3)) };
    keys.forEach((k) => (row[k] = data.series[k][i]));
    return row;
  });

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 18, left: 4 }}>
        <CartesianGrid stroke="#eef0f4" vertical={false} />
        <XAxis
          dataKey="time"
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickLine={false}
          axisLine={{ stroke: "#e2e8f0" }}
          label={{ value: "time (s)", position: "insideBottom", offset: -8, fontSize: 11, fill: "#94a3b8" }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickLine={false}
          axisLine={{ stroke: "#e2e8f0" }}
          width={52}
          label={{ value: yLabel, angle: -90, position: "insideLeft", fontSize: 11, fill: "#94a3b8" }}
        />
        <Tooltip
          contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 12 }}
          labelFormatter={(v) => `t = ${v}s`}
        />
        {keys.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {keys.map((k, i) => (
          <Line
            key={k}
            type="monotone"
            dataKey={k}
            name={name(k)}
            stroke={PALETTE[i % PALETTE.length]}
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function Chips({
  options,
  selected,
  onToggle,
  labelMap,
}: {
  options: string[];
  selected: Set<string>;
  onToggle: (v: string) => void;
  labelMap?: Record<string, string>;
}) {
  return (
    <div className="flex max-h-28 flex-wrap gap-1.5 overflow-auto">
      {options.map((o) => {
        const on = selected.has(o);
        return (
          <button
            key={o}
            aria-pressed={on}
            onClick={() => onToggle(o)}
            className={`rounded-full px-2.5 py-1 text-[12px] font-medium transition duration-150 ease-out active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg ${
              on ? "bg-brand text-white" : "bg-line/60 text-muted hover:text-ink"
            }`}
          >
            {labelMap?.[o] ?? o}
          </button>
        );
      })}
    </div>
  );
}
