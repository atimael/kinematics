"""Headless Pose2Sim stage runner (spawned as a subprocess).

Usage:  python -m app.pipeline.worker <project_dir> <stage1,stage2,...>

Runs each requested Pose2Sim stage in-process from inside <project_dir>,
emitting newline-delimited JSON events on stdout:

    {"type": "stage", "stage": "...", "status": "start|done|failed", "pct": 42.0}
    {"type": "log",   "stage": "...", "msg": "..."}
    {"type": "calib", "px": [...], "mm": [...]}
    {"type": "job",   "status": "done|failed", "error": "..."}

We attach our own root-logger handler BEFORE importing/calling Pose2Sim, so
Pose2Sim's `logging.basicConfig` becomes a no-op and every `logging.info`
record flows through us. All interactive flags are off via the generated
Config.toml; MPLBACKEND/QT envs (set by the parent) keep plotting headless.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import traceback
from pathlib import Path

_emit_lock = threading.Lock()

_CALIB_RE = re.compile(
    r"errors for each camera are respectively\s*\[(.*?)\]\s*px.*?\[(.*?)\]\s*mm",
    re.DOTALL,
)


def emit(obj: dict) -> None:
    with _emit_lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def _monitor_pose(stop: threading.Event, stage_index: int, total_stages: int) -> None:
    """Emit live progress during the long pose-estimation stage by counting the
    per-frame JSON files it writes (Pose2Sim itself gives no event we can hook)."""
    import cv2

    vids = sorted(p for p in Path("videos").glob("*") if p.is_file())
    total_frames = 0
    if vids:
        cap = cv2.VideoCapture(str(vids[0]))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
    pose_dir = Path("pose")
    while not stop.wait(5):
        dirs = list(pose_dir.glob("*_json")) if pose_dir.exists() else []
        counts = [len(list(d.glob("*.json"))) for d in dirs]
        if not counts:
            continue
        done = min(counts)
        frac = min(done / total_frames, 0.99) if total_frames else 0.0
        pct = round((stage_index + frac) / total_stages * 100, 1)
        emit({"type": "stage", "stage": "poseEstimation", "status": "progress", "pct": pct})
        emit({"type": "log", "stage": "poseEstimation",
              "msg": f"Pose estimation: ~{done}{('/' + str(total_frames)) if total_frames else ''} frames per camera"})


def _parse_floats(blob: str) -> list[float]:
    out = []
    for tok in blob.replace("\n", " ").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(float(tok))
        except ValueError:
            pass
    return out


class EventLogHandler(logging.Handler):
    def __init__(self, state: dict):
        super().__init__(level=logging.INFO)
        self._state = state

    def emit(self, record: logging.LogRecord) -> None:  # noqa: A003
        try:
            msg = record.getMessage()
        except Exception:
            return
        for line in msg.splitlines():
            if line.strip():
                emit({"type": "log", "stage": self._state.get("stage"), "msg": line.rstrip()})
        m = _CALIB_RE.search(msg)
        if m:
            emit({"type": "calib", "px": _parse_floats(m.group(1)), "mm": _parse_floats(m.group(2))})


def _neutralize_gui() -> None:
    """Defense-in-depth: ensure no Pose2Sim plotting/clicker path can block or
    crash this headless worker, even if a display flag slips through."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.backend_bases import FigureManagerBase

    plt.show = lambda *a, **k: None  # never block

    class _DummyWindow:
        def __getattr__(self, _name):
            return lambda *a, **k: None

    if not hasattr(FigureManagerBase, "window"):
        FigureManagerBase.window = property(lambda self: _DummyWindow())

    # Pose2Sim creates named figures (e.g. 'Synchronizing cameras') but only
    # closes them when saving plots is enabled. With plots off they leak and the
    # next reuse of the same `num=` raises. Close any same-named figure first.
    _orig_subplots, _orig_figure = plt.subplots, plt.figure

    def _safe_subplots(*a, **k):
        if k.get("num") is not None:
            plt.close(k["num"])
        return _orig_subplots(*a, **k)

    def _safe_figure(*a, **k):
        if k.get("num") is not None:
            plt.close(k["num"])
        return _orig_figure(*a, **k)

    plt.subplots, plt.figure = _safe_subplots, _safe_figure


def _run_calibration() -> None:
    """Headless multi-camera calibration from the checkerboard videos:
    per-camera intrinsics + pairwise extrinsics chained into one world frame."""
    import json

    import rtoml

    from app.pipeline.calibration import calibrate_project

    cfg = rtoml.load(Path("Config.toml"))
    meta = json.loads(Path("project.json").read_text())
    intr = cfg["calibration"]["calculate"]["intrinsics"]
    cams = meta["cameras"]
    corners = tuple(intr["intrinsics_corners_nb"])

    result = calibrate_project(
        Path("."),
        cameras=cams,
        corners=corners,
        square_mm=float(intr["intrinsics_square_size"]),
        log=lambda m: emit({"type": "log", "stage": "calibration", "msg": m}),
    )
    emit({
        "type": "calib",
        "cameras": result["cameras"],
        "px": [c["reproj_error_px"] for c in result["cameras"]],
        "max_error_px": result["max_error_px"],
    })


def run(project_dir: str, stages: list[str]) -> int:
    os.chdir(project_dir)
    _neutralize_gui()

    meta = json.loads(Path("project.json").read_text())
    cameras = meta.get("cameras", [])
    selections = meta.get("subject_selections", {})

    state: dict = {"stage": None}
    handler = EventLogHandler(state)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    pose2sim = None  # heavy (opensim/rtmlib) — import only when a real stage needs it
    total = len(stages)
    for i, stage in enumerate(stages):
        state["stage"] = stage
        emit({"type": "stage", "stage": stage, "status": "start",
              "index": i, "total": total, "pct": round(i / total * 100, 1)})
        try:
            if stage == "calibration":
                _run_calibration()
            else:
                if pose2sim is None:
                    from Pose2Sim import Pose2Sim as pose2sim  # noqa: N813
                if stage == "poseEstimation":
                    stop = threading.Event()
                    threading.Thread(target=_monitor_pose, args=(stop, i, total), daemon=True).start()
                    try:
                        pose2sim.poseEstimation()
                    finally:
                        stop.set()
                    if selections:
                        from app.pipeline.subject_selection import filter_pose_to_subject

                        filter_pose_to_subject(
                            Path("."), cameras, selections,
                            log=lambda message: emit({"type": "log", "stage": stage, "msg": message}),
                        )
                else:
                    getattr(pose2sim, stage)()
        except Exception as exc:  # noqa: BLE001 — report any stage failure verbatim
            emit({"type": "stage", "stage": stage, "status": "failed", "error": str(exc),
                  "trace": traceback.format_exc()[-2500:]})
            emit({"type": "job", "status": "failed", "error": f"{stage}: {exc}"})
            return 1
        emit({"type": "stage", "stage": stage, "status": "done",
              "index": i, "total": total, "pct": round((i + 1) / total * 100, 1)})

    emit({"type": "job", "status": "done"})
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -m app.pipeline.worker <project_dir> <stages csv>", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(sys.argv[1], [s for s in sys.argv[2].split(",") if s]))
