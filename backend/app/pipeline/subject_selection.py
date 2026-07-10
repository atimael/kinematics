"""Filter tracked 2D poses to the subject selected in each camera preview."""
from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path
from typing import Callable

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


def _select_track(json_dir: Path, selection: SubjectSelection, width: int, height: int, fps: float) -> int:
    files = sorted(json_dir.glob("*.json"), key=_frame_number)
    if not files:
        raise ValueError(f"{json_dir.name}: no pose frames were produced.")

    target = round(selection.time_s * fps)
    nearby = sorted(files, key=lambda p: abs(_frame_number(p) - target))[:7]
    click_x, click_y = selection.x * width, selection.y * height
    best: tuple[float, int] | None = None
    for path in nearby:
        people = json.loads(path.read_text()).get("people", [])
        frame_delta = abs(_frame_number(path) - target)
        for index, person in enumerate(people):
            score = _click_distance(person, click_x, click_y, width, height) + frame_delta * 0.002
            if best is None or score < best[0]:
                best = (score, index)

    if best is None or best[0] > 0.2:
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


def restore_unfiltered_pose(project_dir: Path) -> bool:
    """Restore pose/ from pose-all/ before rerunning with a new selection."""
    raw = project_dir / "pose-all"
    if not raw.is_dir():
        return False
    pose = project_dir / "pose"
    replacement = project_dir / "pose-restored.tmp"
    if replacement.exists():
        shutil.rmtree(replacement)
    shutil.copytree(raw, replacement)
    if pose.exists():
        shutil.rmtree(pose)
    replacement.rename(pose)
    return True


def filter_pose_to_subject(
    project_dir: Path,
    cameras: list[str],
    selections: dict[str, SubjectSelection | dict],
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, int]:
    """Keep the clicked subject's stable Sports2D track in every pose frame."""
    pose = project_dir / "pose"
    if not pose.is_dir():
        raise ValueError("Pose-estimation output is missing.")
    raw = project_dir / "pose-all"
    if not raw.exists():
        shutil.copytree(pose, raw)

    normalized = {
        camera: value if isinstance(value, SubjectSelection) else SubjectSelection.model_validate(value)
        for camera, value in selections.items()
    }
    missing = [camera for camera in cameras if camera not in normalized]
    if missing:
        raise ValueError(f"Select the subject in every camera; missing: {', '.join(missing)}.")

    tracks: dict[str, int] = {}
    for camera in cameras:
        width, height, fps = _video_properties(project_dir, camera)
        tracks[camera] = _select_track(_json_dir(raw, camera), normalized[camera], width, height, fps)
        log(f"{camera}: selected subject track #{tracks[camera]} at {normalized[camera].time_s:.2f}s")

    selected = project_dir / "pose-selected.tmp"
    if selected.exists():
        shutil.rmtree(selected)
    shutil.copytree(raw, selected)
    for camera, track in tracks.items():
        for path in _json_dir(selected, camera).glob("*.json"):
            data = json.loads(path.read_text())
            people = data.get("people", [])
            data["people"] = [people[track]] if track < len(people) else [{}]
            path.write_text(json.dumps(data))

    if pose.exists():
        shutil.rmtree(pose)
    selected.rename(pose)
    return tracks
