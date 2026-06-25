import { Link, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Project from "./pages/Project";

export default function App() {
  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-line bg-surface/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Link to="/" className="flex items-center gap-2.5">
            <span className="grid size-7 place-items-center rounded-lg bg-brand text-[13px] font-bold text-white">K</span>
            <span className="text-[15px] font-semibold tracking-tight">Kinematics</span>
            <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[11px] font-medium text-brand">Pose2Sim</span>
          </Link>
          <a
            href="https://github.com/perfanalytics/pose2sim"
            target="_blank"
            rel="noreferrer"
            className="text-[13px] text-muted hover:text-ink"
          >
            About the pipeline
          </a>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/projects/:id" element={<Project />} />
        </Routes>
      </main>
    </div>
  );
}
