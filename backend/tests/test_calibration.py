"""Regression tests for the cross-platform calibration input path."""
from pathlib import Path

import cv2
import numpy as np

from app.pipeline import calibration


def _write_test_video(path: Path, *, frames: int = 8, fps: float = 4.0) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (320, 240),
    )
    assert writer.isOpened()
    try:
        for i in range(frames):
            image = np.full((240, 320, 3), i * 20, dtype=np.uint8)
            writer.write(image)
    finally:
        writer.release()


def test_kabsch_recovers_rigid_transform():
    """Solo/unsynced cameras are now placed by rigidly registering their board
    trajectory to the reference — that hinges on _kabsch recovering the exact
    transform between two views of the same moving board."""
    rng = np.random.default_rng(1)
    src = rng.uniform(-1, 1, (30, 3))
    angle = np.array([0.3, -0.5, 0.2])
    R_true, _ = cv2.Rodrigues(angle)
    t_true = np.array([1.2, -0.4, 0.8])
    dst = (R_true @ src.T).T + t_true

    R, t = calibration._kabsch(src, dst)

    assert np.allclose(R @ src.T + t.reshape(3, 1), dst.T, atol=1e-9)
    assert np.linalg.norm(R - R_true) < 1e-9
    assert np.linalg.norm(t - t_true) < 1e-9


def test_extract_frames_does_not_require_external_ffmpeg(tmp_path: Path, monkeypatch):
    video = tmp_path / "input.avi"
    frames_dir = tmp_path / "frames"
    _write_test_video(video)

    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(calibration, "_DET_WIDTH", 160)

    extracted = calibration._extract(video, frames_dir)

    frames = sorted(frames_dir.glob("f_*.jpg"))
    assert extracted == 8
    assert len(frames) == 8
    assert cv2.imread(str(frames[0])).shape[:2] == (120, 160)
