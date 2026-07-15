"""Regression tests for manually selecting one subject in crowded videos."""
import json
from pathlib import Path

import cv2
import numpy as np

from app.models import SubjectSelection
from app.pipeline.subject_selection import filter_pose_to_subject


def _person(cx: float, cy: float) -> dict:
    points = []
    for dx, dy in [(-20, -40), (20, -40), (0, 0), (-15, 45), (15, 45)]:
        points.extend([cx + dx, cy + dy, 0.95])
    return {"person_id": [-1], "pose_keypoints_2d": points}


def _write_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (640, 480))
    assert writer.isOpened()
    try:
        for _ in range(3):
            writer.write(np.zeros((480, 640, 3), dtype=np.uint8))
    finally:
        writer.release()


def _write_pose(path: Path, people: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1.3, "people": people}))


def test_filter_keeps_clicked_subject_and_backs_up_raw(tmp_path: Path):
    project = tmp_path / "project"
    _write_video(project / "videos" / "cam01.avi")
    pose_dir = project / "pose" / "cam01_json"
    for frame in range(3):
        _write_pose(
            pose_dir / f"cam01_{frame:06d}.json",
            [_person(120 + frame * 2, 220), _person(500 - frame * 2, 230)],
        )

    kept = filter_pose_to_subject(
        project,
        cameras=["cam01"],
        selections={"cam01": SubjectSelection(x=0.78, y=0.48, time_s=0.1)},
    )

    assert kept == {"cam01": 3}  # subject tracked across all frames
    selected = json.loads((project / "pose" / "cam01_json" / "cam01_000002.json").read_text())
    raw = json.loads((project / "pose-all" / "cam01_json" / "cam01_000002.json").read_text())
    assert len(selected["people"]) == 1
    assert selected["people"][0]["pose_keypoints_2d"][0] == 476  # the clicked (right-side) person
    assert len(raw["people"]) == 2  # pristine backup untouched
    # No per-run scratch directories are left behind.
    assert not (project / "pose-selected.tmp").exists()
    assert not (project / "pose-restored.tmp").exists()


def test_tracking_survives_detection_reorder(tmp_path: Path):
    """The subject must be followed by position, not list index: when detections
    reorder frame-to-frame, a fixed index would flip to the wrong person."""
    project = tmp_path / "project"
    _write_video(project / "videos" / "cam01.avi")
    pose_dir = project / "pose" / "cam01_json"
    n = 20
    for frame in range(n):
        subject = _person(100 + frame * 15, 240)   # walks left -> right
        distractor = _person(560, 120)              # parked in a corner
        people = [subject, distractor] if frame % 2 == 0 else [distractor, subject]
        _write_pose(pose_dir / f"cam01_{frame:06d}.json", people)

    # Click the subject at its mid-trial position (frame 10 -> x ~= 250 / 640).
    filter_pose_to_subject(
        project,
        cameras=["cam01"],
        selections={"cam01": SubjectSelection(x=250 / 640, y=240 / 480, time_s=1.0)},
    )

    for frame in range(n):
        people = json.loads((pose_dir / f"cam01_{frame:06d}.json").read_text())["people"]
        assert len(people) == 1
        cx = people[0]["pose_keypoints_2d"][6]  # x of the 3rd keypoint (offset 0 from centre)
        assert abs(cx - (100 + frame * 15)) < 60  # stayed on the moving subject, not the corner distractor
