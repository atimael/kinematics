import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { GaitRow } from "../types";
import { Button, Card, CardHeader, Spinner, Stat } from "./ui";

function fmt(v: number | null): string {
  return v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function MetricTable({ rows, indicative }: { rows: GaitRow[]; indicative?: boolean }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line">
      <table className="w-full border-collapse text-[13px]">
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={`${r.label}-${r.unit}-${i}`}
              className={`border-t border-line ${i === 0 ? "border-t-0" : ""} ${
                r.derived ? "bg-bg" : i % 2 ? "bg-bg/40" : ""
              }`}
            >
              <td className={`px-3 py-1.5 ${r.derived ? "text-muted" : ""}`}>
                {r.label}
                {r.unit && <span className="text-muted"> ({r.unit})</span>}
                {r.robust && !r.derived && (
                  <span className="ml-1.5 rounded bg-good/12 px-1.5 py-0.5 text-[10px] font-medium text-good">robust</span>
                )}
              </td>
              <td className={`px-3 py-1.5 text-right tabular ${r.derived ? "text-muted" : "font-medium"}`}>
                {fmt(r.value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {indicative && (
        <p className="border-t border-line bg-bg px-3 py-2 text-[11px] text-muted">
          Indicative only — markerless kinematics from 4 cameras. Compare R vs L (and between sockets within the same
          subject), not against absolute clinical norms.
        </p>
      )}
    </div>
  );
}

export function GaitReport({ projectId }: { projectId: string }) {
  const gait = useQuery({ queryKey: ["gait", projectId], queryFn: () => api.gait(projectId), retry: false });
  const r = gait.data;

  return (
    <Card>
      <CardHeader
        title="Gait analysis — socket comparison"
        desc="Spatiotemporal symmetry is the defensible core; joint kinematics are indicative. Set your prosthetic side as R or L when interpreting."
        right={
          r ? (
            <a href={api.gaitCsvUrl(projectId)} download>
              <Button variant="subtle">Download CSV</Button>
            </a>
          ) : undefined
        }
      />
      <div className="space-y-5 p-5">
        {gait.isLoading ? (
          <div className="flex items-center gap-2 text-[13px] text-muted">
            <Spinner /> Detecting gait events…
          </div>
        ) : gait.isError ? (
          <p className="text-[13px] text-bad">{(gait.error as Error).message}</p>
        ) : r ? (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Cadence" value={r.cadence_steps_min != null ? `${r.cadence_steps_min}/min` : "—"} />
              <div className="rounded-xl border border-line bg-bg px-4 py-3">
                <div className="text-[12px] uppercase tracking-wide text-muted">Walking speed</div>
                <div className="mt-1 text-[20px] font-semibold tabular">
                  {r.walking_speed_ms ?? "—"} <span className="text-[13px] font-normal text-muted">m/s</span>
                </div>
                <div className="text-[12px] text-muted tabular">
                  {r.walking_speed_ms != null ? `${(r.walking_speed_ms * 3.6).toFixed(2)} km/h` : "—"}
                </div>
              </div>
              <Stat label="Steps detected" value={r.n_steps} tone={r.enough_steps ? "good" : "warn"} />
              <Stat label="Gait cycles (R/L)" value={`${r.n_strides.r} / ${r.n_strides.l}`} />
            </div>

            {!r.enough_steps && (
              <p className="rounded-lg border border-warn/30 bg-warn/8 px-3.5 py-2.5 text-[12px] text-ink">
                Only {r.n_steps} steps detected — too few for reliable symmetry. Use a longer straight walking trial
                (aim for 6+ steps per limb).
              </p>
            )}

            <div>
              <h3 className="mb-2 text-[13px] font-semibold">Spatiotemporal</h3>
              <MetricTable rows={r.spatiotemporal} />
              <p className="mt-1.5 text-[11px] text-muted">
                Step time &amp; step length are most reliable (foot-contact timing); stance/swing depend on toe-off,
                noisier on the prosthetic foot.
              </p>
            </div>

            <div>
              <h3 className="mb-2 text-[13px] font-semibold">Joint kinematics (indicative)</h3>
              <MetricTable rows={r.kinematics} indicative />
            </div>
          </>
        ) : null}
      </div>
    </Card>
  );
}
