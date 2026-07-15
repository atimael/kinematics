"""Filter tracked 2D poses to the subject selected in each camera preview."""
from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from app.models import SubjectSelection


def _frame_number(path: Path) -> int:
    hits = re.findall(r"\d+", path.stem)
    return int(hits[-1]) if hits else 0


def _json_dir(root: Path, camera: str) -> Path:
    exact = root / f"{camera}_json"
    if exact.is_dir():
        return exact
    matches = sorted(p for p in root.glob(f"{camera}*_json") if p.is_dir())
    if not matches:
        raise ValueError(f"{camera}: pose-estimation output was not found.")
    return matches[0]


def _valid_points(person: dict) -> np.ndarray:
    raw = person.get("pose_keypoints_2d", [])
    if len(raw) < 3:
        return np.empty((0, 2))
    points = np.asarray(raw, dtype=float).reshape(-1, 3)
    valid = np.isfinite(points).all(axis=1) & (points[:, 2] > 0.1)
    return points[valid, :2]


def _centroid(person: dict) -> Optional[np.ndarray]:
    pts = _valid_points(person)
    return pts.mean(axis=0) if len(pts) >= 3 else None


def _click_distance(person: dict, click_x: float, click_y: float, width: int, height: int) -> float:
    points = _valid_points(person)
    if len(points) < 3:
        return math.inf
    x0, y0 = points.min(axis=0)
    x1, y1 = points.max(axis=0)
    padding = max(x1 - x0, y1 - y0) * 0.08
    dx = max(x0 - padding - click_x, 0.0, click_x - x1 - padding)
    dy = max(y0 - padding - click_y, 0.0, click_y - y1 - padding)
    outside = math.hypot(dx / width, dy / height)
    center = points.mean(axis=0)
    center_distance = math.hypot((center[0] - click_x) / width, (center[1] - click_y) / height)
    return outside + center_distance * 0.01


def _select_seed(json_dir: Path, selection: SubjectSelection, width: int, height: int, fps: float) -> np.ndarray:
    """Pixel centroid of the clicked subject at the selection time — the anchor
    the frame-to-frame tracker chains from."""
    files = sorted(json_dir.glob("*.json"), key=_frame_number)
    if not files:
        raise ValueError(f"{json_dir.name}: no pose frames were produced.")

    target = round(selection.time_s * fps)
    nearby = sorted(files, key=lambda p: abs(_frame_number(p) - target))[:7]
    click_x, click_y = selection.x * width, selection.y * height
    best: tuple[float, Optional[np.ndarray]] | None = None
    for path in nearby:
        people = json.loads(path.read_text()).get("people", [])
        frame_delta = abs(_frame_number(path) - target)
        for person in people:
            score = _click_distance(person, click_x, click_y, width, height) + frame_delta * 0.002
            if best is None or score < best[0]:
                best = (score, _centroid(person))

    if best is None or best[0] > 0.2 or best[1] is None:
        raise ValueError(
            f"{json_dir.name}: no detected person was found near the selected point at {selection.time_s:.2f}s. "
            "Choose a frame where the subject is clearly visible."
        )
    return best[1]


def _video_properties(project_dir: Path, camera: str) -> tuple[int, int, float]:
    videos = sorted(p for p in (project_dir / "videos").glob(f"{camera}.*") if p.is_file())
    if not videos:
        raise ValueError(f"{camera}: trial video was not found.")
    cap = cv2.VideoCapture(str(videos[0]))
    try:
        if not cap.isOpened():
            raise ValueError(f"{camera}: trial video could not be opened.")
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
    finally:
        cap.release()
    if width <= 0 or height <= 0:
        raise ValueError(f"{camera}: trial video dimensions could not be read.")
    if not math.isfinite(fps) or fps <= 0:
        fps = 30.0
    return width, height, fps


def _nearest_person(people: list[dict], anchor: np.ndarray, gate: float) -> Optional[int]:
    """Index of the person whose valid-keypoint centroid is closest to `anchor`,
    or None if the nearest is beyond `gate` pixels (subject absent this frame)."""
    best: tuple[float, int] | None = None
    for index, person in enumerate(people):
        c = _centroid(person)
        if c is None:
            continue
        d = float(np.hypot(*(c - anchor)))
        if best is None or d < best[0]:
            best = (d, index)
    if best is None or best[0] > gate:
        return None
    return best[1]


def _track_subject(json_dir: Path, seed: np.ndarray, gate: float, seed_frame: int) -> dict[Path, int]:
    """Follow the subject across every frame by chaining nearest-centroid from the
    seed, forward and backward in time. Returns {frame_path: chosen_person_index};
    frames where the subject is absent are omitted."""
    files = sorted(json_dir.glob("*.json"), key=_frame_number)
    people_by_file = {p: json.loads(p.read_text()).get("people", []) for p in files}
    order = sorted(range(len(files)), key=lambda i: abs(_frame_number(files[i]) - seed_frame))
    start = order[0] if order else 0

    chosen: dict[Path, int] = {}

    def walk(indices: range) -> None:
        anchor = seed
        for i in indices:
            path = files[i]
            idx = _nearest_person(people_by_file[path], anchor, gate)
            if idx is not None:
                chosen[path] = idx
                c = _centroid(people_by_file[path][idx])
                if c is not None:
                    anchor = c
    walk(range(start, len(files)))
    walk(range(start - 1, -1, -1))
    return chosen


def filter_pose_to_subject(
    project_dir: Path,
    cameras: list[str],
    selections: dict[str, SubjectSelection | dict],
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, int]:
    """Keep only the clicked subject in every pose frame, following them across
    frames by spatial tracking (not a fixed list index, which drifts to the wrong
    person the moment detections reorder). Writes filtered JSON directly into
    pose/, reading from the one-time pristine backup pose-all/ — no per-run copies.
    """
    pose = project_dir / "pose"
    if not pose.is_dir():
        raise ValueError("Pose-estimation output is missing.")
    raw = project_dir / "pose-all"
    if not raw.exists():
        shutil.copytree(pose, raw)  # pristine unfiltered backup, first run only

    normalized = {
        camera: value if isinstance(value, SubjectSelection) else SubjectSelection.model_validate(value)
        for camera, value in selections.items()
    }
    missing = [camera for camera in cameras if camera not in normalized]
    if missing:
        raise ValueError(f"Select the subject in every camera; missing: {', '.join(missing)}.")

    kept: dict[str, int] = {}
    for camera in cameras:
        width, height, fps = _video_properties(project_dir, camera)
        src_dir = _json_dir(raw, camera)
        seed = _select_seed(src_dir, normalized[camera], width, height, fps)
        seed_frame = round(normalized[camera].time_s * fps)
        gate = 0.2 * math.hypot(width, height)  # max plausible centroid jump between frames
        chosen = _track_subject(src_dir, seed, gate, seed_frame)

        dst_dir = _json_dir(pose, camera)
        for path in src_dir.glob("*.json"):
            data = json.loads(path.read_text())
            people = data.get("people", [])
            idx = chosen.get(path)
            data["people"] = [people[idx]] if idx is not None and idx < len(people) else [{}]
            (dst_dir / path.name).write_text(json.dumps(data))
        kept[camera] = len(chosen)
        total = len(list(src_dir.glob("*.json")))
        log(f"{camera}: tracked subject across {kept[camera]}/{total} frames from {normalized[camera].time_s:.2f}s")
    return kept
