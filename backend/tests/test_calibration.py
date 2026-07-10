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
