"""Async job manager: spawn the headless worker, stream its NDJSON events.

One job at a time per project. Events are broadcast to any number of SSE
subscribers and mirrored into the project's ProjectMeta so a late subscriber
(or a page reload) can recover current state.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Optional

from app import projects
from app.models import CalibrationResult, CameraError, JobState

BACKEND_DIR = Path(__file__).resolve().parents[2]
PYBIN = sys.executable  # uvicorn runs under the venv -> this is the venv python


class Job:
    def __init__(self, job_id: str, project_id: str, kind: str, stages: list[str]):
        self.id = job_id
        self.project_id = project_id
        self.kind = kind
        self.stages = stages
        self.status = "queued"
        self.current_stage: Optional[str] = None
        self.pct = 0.0
        self.error: Optional[str] = None
        self.events: list[dict] = []  # ring buffer for replay
        self.calib_cameras: list[dict] = []
        self.calib_max: Optional[float] = None
        self.subscribers: set[asyncio.Queue] = set()
        self.done = asyncio.Event()

    def to_state(self) -> JobState:
        return JobState(
            id=self.id, kind=self.kind, status=self.status, stages=self.stages,
            current_stage=self.current_stage, pct=self.pct, error=self.error,
        )


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._active_by_project: dict[str, str] = {}

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def active_for(self, project_id: str) -> Optional[Job]:
        jid = self._active_by_project.get(project_id)
        return self._jobs.get(jid) if jid else None

    async def start(self, project_id: str, kind: str, stages: list[str]) -> Job:
        existing = self.active_for(project_id)
        if existing and existing.status in ("queued", "running"):
            raise RuntimeError("A job is already running for this project.")

        job = Job(uuid.uuid4().hex[:12], project_id, kind, stages)
        self._jobs[job.id] = job
        self._active_by_project[project_id] = job.id
        asyncio.create_task(self._run(job))
        return job

    def subscribe(self, job: Job) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        # Replay buffered events so a reconnecting client catches up.
        for ev in job.events:
            q.put_nowait(ev)
        if job.status in ("done", "failed"):
            q.put_nowait({"type": "job", "status": job.status, "error": job.error})
        job.subscribers.add(q)
        return q

    def unsubscribe(self, job: Job, q: asyncio.Queue) -> None:
        job.subscribers.discard(q)

    def _broadcast(self, job: Job, ev: dict) -> None:
        job.events.append(ev)
        if len(job.events) > 2000:
            job.events = job.events[-2000:]
        for q in list(job.subscribers):
            q.put_nowait(ev)

    async def _run(self, job: Job) -> None:
        project_dir = projects.project_dir(job.project_id)
        env = os.environ.copy()
        env.update(
            MPLBACKEND="Agg",
            QT_QPA_PLATFORM="offscreen",
            PYTHONUNBUFFERED="1",
            PYTHONPATH=str(BACKEND_DIR),
        )
        job.status = "running"
        self._persist(job)

        loop = asyncio.get_running_loop()
        cmd = [PYBIN, "-m", "app.pipeline.worker", str(project_dir), ",".join(job.stages)]

        # Plain synchronous Popen driven from threads. asyncio.create_subprocess_exec
        # only works on the Proactor loop on Windows (the Selector loop raises
        # NotImplementedError, surfaced as "Failed to launch worker"); Popen is
        # loop- and platform-agnostic.
        def _spawn() -> subprocess.Popen:
            return subprocess.Popen(
                cmd, cwd=str(BACKEND_DIR), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )

        try:
            proc = await loop.run_in_executor(None, _spawn)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("uvicorn.error").exception("Failed to launch worker: %s", cmd)
            job.status, job.error = "failed", f"Failed to launch worker: {exc!r}"
            self._broadcast(job, {"type": "job", "status": "failed", "error": job.error})
            self._finish(job)
            return

        sentinel = object()
        stdout_q: asyncio.Queue = asyncio.Queue()
        stderr_buf: list[str] = []

        def _read_stdout() -> None:
            try:
                for line in proc.stdout:
                    loop.call_soon_threadsafe(stdout_q.put_nowait, line)
            finally:
                loop.call_soon_threadsafe(stdout_q.put_nowait, sentinel)

        def _read_stderr() -> None:
            for line in proc.stderr:
                stderr_buf.append(line)

        t_err = threading.Thread(target=_read_stderr, name=f"worker-err-{job.id}", daemon=True)
        threading.Thread(target=_read_stdout, name=f"worker-out-{job.id}", daemon=True).start()
        t_err.start()

        while True:
            line = await stdout_q.get()
            if line is sentinel:
                break
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                ev = {"type": "log", "stage": job.current_stage, "msg": line}
            self._apply(job, ev)
            self._broadcast(job, ev)

        rc = await loop.run_in_executor(None, proc.wait)
        await loop.run_in_executor(None, t_err.join)
        if job.status not in ("done", "failed"):
            if rc == 0:
                job.status = "done"
                ev = {"type": "job", "status": "done"}
            else:
                stderr = "".join(stderr_buf)[-1500:]
                job.status, job.error = "failed", stderr or f"worker exited with code {rc}"
                ev = {"type": "job", "status": "failed", "error": job.error}
            self._broadcast(job, ev)
        self._finish(job)

    def _apply(self, job: Job, ev: dict) -> None:
        t = ev.get("type")
        if t == "stage":
            job.current_stage = ev.get("stage")
            if "pct" in ev:
                job.pct = float(ev["pct"])
            if ev.get("status") == "failed":
                job.status, job.error = "failed", ev.get("error")
        elif t == "calib":
            job.calib_cameras = ev.get("cameras", [])
            job.calib_max = ev.get("max_error_px")
        elif t == "job":
            job.status = ev.get("status", job.status)
            if ev.get("error"):
                job.error = ev["error"]

    def _finish(self, job: Job) -> None:
        if job.status == "done":
            job.pct = 100.0
        self._persist(job)
        self._broadcast(job, {"type": "end"})
        job.done.set()
        for q in list(job.subscribers):
            q.put_nowait({"type": "end"})

    def _persist(self, job: Job) -> None:
        meta = projects.load_meta(job.project_id)
        if not meta:
            return
        meta.job = job.to_state()
        if job.kind == "calibration":
            self._persist_calibration(job, meta)
        elif job.kind == "processing":
            if job.status == "done":
                meta.status = "processed"
            elif job.status == "failed":
                meta.status = "failed"
            elif job.status == "running":
                meta.status = "processing"
        projects.save_meta(meta)

    def _persist_calibration(self, job: Job, meta) -> None:
        cams = [CameraError(**c) for c in job.calib_cameras]
        cal_dir = projects.calibration_dir(job.project_id)
        tomls = sorted(cal_dir.glob("*.toml"), key=lambda p: p.stat().st_ctime, reverse=True) if cal_dir.exists() else []
        status = {"done": "done", "failed": "failed", "running": "running"}.get(job.status, "pending")
        meta.calibration = CalibrationResult(
            status=status,
            calib_file=tomls[0].name if tomls else None,
            cameras=cams,
            max_error_px=job.calib_max,
            message=job.error,
        )
        # Leave project.status as-is on success; the user reviews the per-camera
        # errors and clicks Accept (which sets 'calibrated') before continuing.


manager = JobManager()
