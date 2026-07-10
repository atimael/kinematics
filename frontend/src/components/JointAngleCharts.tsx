import { useState } from "react";
import { useAngles } from "../api/queries";
import type { ChartData } from "../types";
import { Card, CardHeader, Spinner } from "./ui";
import { Chips, TimeSeriesChart } from "./TimeSeriesChart";

const SIDE_RE = /^(.+)_([rl])$/;
const R_COLOR = "#2563eb";
const L_COLOR = "#f97316";
// Leg joints most relevant to gait / socket comparison, in display order.
const PREFERRED = ["knee_angle", "ankle_angle", "hip_flexion", "hip_adduction", "hip_rotation", "subtalar_angle", "mtp_angle"];

interface Pair {
  base: string;
  r: string;
  l: string;
}

function buildPairs(cols: string[]): Pair[] {
  const map = new Map<string, { r?: string; l?: string }>();
  for (const c of cols) {
    if (c.endsWith("_beta")) continue;
    const m = c.match(SIDE_RE);
    if (!m) continue;
    const entry = map.get(m[1]) ?? {};
    entry[m[2] as "r" | "l"] = c;
    map.set(m[1], entry);
  }
  const pairs: Pair[] = [];
  for (const [base, e] of map) {
    if (e.r && e.l) pairs.push({ base, r: e.r, l: e.l });
  }
  const rank = (b: string) => (PREFERRED.indexOf(b) < 0 ? 99 : PREFERRED.indexOf(b));
  pairs.sort((a, b) => rank(a.base) - rank(b.base));
  return pairs;
}

function jointTitle(pair: Pair, labels?: ChartData["labels"]): string {
  const raw = labels?.[pair.r]?.label ?? pair.base.replace(/_/g, " ");
  const stripped = raw.replace(/^(Right|Left)\s+/i, "");
  return stripped.charAt(0).toUpperCase() + stripped.slice(1);
}

export function JointAngleCharts({
  projectId,
  angleColumns,
  enabled,
}: {
  projectId: string;
  angleColumns: string[];
  enabled: boolean;
}) {
  const pairs = buildPairs(angleColumns);
  const cols = pairs.flatMap((p) => [p.r, p.l]);
  const { data, isLoading } = useAngles(projectId, cols, enabled && pairs.length > 0);

  const [sel, setSel] = useState<Set<string>>(() => new Set(pairs.slice(0, 2).map((p) => p.base)));

  if (!enabled || pairs.length === 0) return null;

  const toggle = (base: string) =>
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(base)) next.delete(base);
      else next.add(base);
      return next;
    });

  const shown = pairs.filter((p) => sel.has(p.base));

  return (
    <Card>
      <CardHeader
        title="Joint angles — left vs right"
        desc="From OpenSim inverse kinematics. Compare the prosthetic and sound sides across the trial."
        right={
          <div className="flex items-center gap-3 text-[12px] text-muted">
            <Legend color={R_COLOR} label="Right" />
            <Legend color={L_COLOR} label="Left" />
          </div>
        }
      />
      <div className="space-y-4 p-5">
        <Chips
          options={pairs.map((p) => p.base)}
          selected={sel}
          onToggle={toggle}
          labelMap={Object.fromEntries(pairs.map((p) => [p.base, jointTitle(p, data?.labels)]))}
        />

        {isLoading ? (
          <div className="flex items-center gap-2 py-16 text-[13px] text-muted">
            <Spinner /> Loading joint angles…
          </div>
        ) : !data ? (
          <p className="py-10 text-[13px] text-muted">No joint-angle output for this trial.</p>
        ) : shown.length === 0 ? (
          <p className="py-10 text-[13px] text-muted">Pick a joint above to plot it.</p>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            {shown
              .filter((p) => data.series[p.r] && data.series[p.l])
              .map((p) => (
                <div key={p.base}>
                  <div className="mb-1 text-[13px] font-semibold">{jointTitle(p, data.labels)} (°)</div>
                  <TimeSeriesChart
                    data={{ ...data, series: { [p.r]: data.series[p.r], [p.l]: data.series[p.l] } }}
                    yLabel="degrees"
                    labelMap={{ [p.r]: "Right", [p.l]: "Left" }}
                    colorMap={{ [p.r]: R_COLOR, [p.l]: L_COLOR }}
                    showLegend={false}
                  />
                </div>
              ))}
          </div>
        )}
      </div>
    </Card>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="size-2.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}
