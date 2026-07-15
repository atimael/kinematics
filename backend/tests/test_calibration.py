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


def _look_at(eye: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ground-truth world->cam pose for a camera at `eye` looking at `target`."""
    up = np.array([0.0, 1.0, 0.0])
    f = target - eye
    f = f / np.linalg.norm(f)
    r = np.cross(up, f)
    r = r / np.linalg.norm(r)
    u = np.cross(f, r)
    R = np.stack([r, u, f])
    return R, -R @ eye


def test_unsynced_solo_cameras_are_placed_and_recovered():
    """The real regression: independently-recorded cameras (different time offsets,
    no shared same-instant board view) must still be calibrated. Drives the actual
    production solver with a synced pair + two solo cameras and checks it recovers
    the ground-truth extrinsics instead of raising 'aren't time-synced'."""
    rng = np.random.default_rng(7)
    cams = ["cam01", "cam02", "cam03", "cam04"]
    board_center = np.zeros(3)
    eyes = {
        "cam01": np.array([0.0, 0.0, -2.5]),   # reference
        "cam02": np.array([0.3, 0.0, -2.5]),   # hardware-synced with cam01
        "cam03": np.array([-2.2, 0.0, -1.0]),  # solo, time-offset
        "cam04": np.array([2.0, 0.3, -1.2]),   # solo, time-offset
    }
    gt = {c: _look_at(eyes[c], board_center) for c in cams}
    offsets = {"cam01": 0, "cam02": 0, "cam03": 8, "cam04": 11}

    T = 60
    objp = calibration.object_points((6, 7), 0.1)
    board = []
    for tt in range(T):
        Rw, _ = cv2.Rodrigues(rng.uniform(-0.3, 0.3, 3))
        tw = np.array([0.25 * np.sin(tt / 6), 0.2 * np.cos(tt / 5), 0.15 * np.sin(tt / 8)])
        board.append((Rw, tw))

    K = np.array([[900.0, 0, 640], [0, 900.0, 360], [0, 0, 1]])
    dist0 = np.zeros(4)
    poses: dict = {c: {} for c in cams}
    detections: dict = {c: {} for c in cams}
    for c in cams:
        Rc, tc = gt[c]
        for k in range(T):
            wt = k + offsets[c]
            if not (0 <= wt < T):
                continue
            Rw, tw = board[wt]
            Rbc, tbc = Rc @ Rw, Rc @ tw + tc  # board -> camera
            rvec, _ = cv2.Rodrigues(Rbc)
            imgp, _ = cv2.projectPoints(objp, rvec, tbc, K, dist0)
            detections[c][k] = imgp.reshape(-1, 1, 2).astype(np.float32)
            poses[c][k] = (Rbc, tbc, 0.0)

    world, ref = calibration._solve_world_extrinsics(
        cams, poses, detections, {c: K for c in cams}, {c: dist0 for c in cams}, objp
    )

    assert ref == "cam01"
    assert set(world) == set(cams)  # every camera placed, including the solo ones
    Rr, tr = gt[ref]
    for c in cams:
        Rc, tc = gt[c]
        gt_R, gt_t = Rc @ Rr.T, tc - Rc @ Rr.T @ tr  # ground truth relative to reference
        wR, wt = world[c]
        rot_deg = np.degrees(np.arccos(np.clip((np.trace(wR @ gt_R.T) - 1) / 2, -1, 1)))
        assert rot_deg < 0.05, f"{c} rotation off by {rot_deg} deg"
        assert np.linalg.norm(wt - gt_t) < 1e-3, f"{c} translation off by {np.linalg.norm(wt - gt_t)} m"


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
