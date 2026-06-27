import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useProject } from "../api/queries";
import { Stepper, type StepKey } from "../components/Stepper";
import { Badge, Card, Spinner } from "../components/ui";
import { CalibrationStep } from "./steps/CalibrationStep";
import { TrialVideosStep } from "./steps/TrialVideosStep";
import { ProcessingStep } from "./steps/ProcessingStep";
import { ResultsStep } from "./steps/ResultsStep";
import type { ProjectStatus } from "../types";

function deriveStep(status: ProjectStatus): StepKey {
  if (status === "processed") return "results";
  if (status === "processing") return "processing";
  if (status === "calibrated") return "videos";
  return "calibration";
}

function reachedSteps(status: ProjectStatus): Set<StepKey> {
  const r = new Set<StepKey>(["calibration"]);
  if (["calibrated", "processing", "processed"].includes(status)) r.add("videos");
  if (["processing", "processed"].includes(status)) r.add("processing");
  if (status === "processed") r.add("results");
  return r;
}

export default function Project() {
  const { id = "" } = useParams();
  const { data: project, isLoading, error } = useProject(id, { poll: true });
  const [step, setStep] = useState<StepKey | null>(null);
  const [prevId, setPrevId] = useState(id);

  if (id !== prevId) {
    setPrevId(id);
    setStep(null);
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-[13px] text-muted">
        <Spinner /> Loading session…
      </div>
    );
  }
  if (error || !project) {
    return (
      <Card>
        <div className="px-5 py-8 text-[14px] text-muted">
          Session not found. <Link to="/" className="text-brand">Back to sessions</Link>
        </div>
      </Card>
    );
  }

  const active = step ?? deriveStep(project.status);
  const reached = reachedSteps(project.status);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Link to="/" className="text-[12px] text-muted hover:text-ink">
            ← All sessions
          </Link>
          <div className="mt-1 flex items-center gap-2.5">
            <h1 className="text-[20px] font-semibold tracking-tight">{project.params.name}</h1>
            <Badge tone={project.status === "processed" ? "good" : project.status === "failed" ? "bad" : "brand"}>
              {project.status}
            </Badge>
          </div>
        </div>
        <Stepper active={active} reached={reached} onJump={setStep} />
      </div>

      {active === "calibration" && <CalibrationStep project={project} goNext={() => setStep("videos")} />}
      {active === "videos" && <TrialVideosStep project={project} goNext={() => setStep("processing")} />}
      {active === "processing" && <ProcessingStep project={project} goResults={() => setStep("results")} />}
      {active === "results" && <ResultsStep project={project} />}
    </div>
  );
}
