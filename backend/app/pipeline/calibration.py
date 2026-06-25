"""Headless multi-camera calibration with OpenCV.

Pose2Sim's own `calculate` extrinsics path is interactive (matplotlib clicker /
Tk dialog) and assumes one checkerboard view shared by every camera. For cameras
spread AROUND a subject, a flat board never faces more than a couple of cameras
at once, so that assumption fails.

Instead we calibrate from the per-camera checkerboard videos directly:
  • intrinsics  — cv2.calibrateCamera on detected board views per camera;
  • extrinsics  — for every camera PAIR, frames where both see the board give
    their relative pose; we build a graph and chain the pairs through their
    overlaps into one world frame (reference camera = origin).

Detection is robust: OpenCL off (its cache flakes on Macs), and the board's
inner-corner count is auto-resolved if the entered value is wrong.

Output is a `Calib.toml` in Pose2Sim's exact format; downstream stages consume
it unchanged. Joint angles are invariant to the world frame's orientation, so a
reference-camera world is fine for kinematics.
"""
from __future__ import annotations

import subprocess
import tempfile
from collections import deque
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import rtoml

cv2.ocl.setUseOpenCL(False)

_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}
_IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
_CLASSIC_FLAGS = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
_SUBPIX = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

_EXTRACT_FPS = 4
_DET_WIDTH = 1600
_MAX_INTRINSIC_VIEWS = 25
_MAX_SYNC_OFFSET_S = 12  # cameras may be started up to this far apart


# ----------------------------------------------------------------------------- detection

def _detect_one(gray: np.ndarray, size: tuple[int, int]) -> Optional[np.ndarray]:
    ok, pts = cv2.findChessboardCorners(gray, size, _CLASSIC_FLAGS)
    if ok:
        return cv2.cornerSubPix(gray, pts, (11, 11), (-1, -1), _SUBPIX).astype(np.float32)
    ok, pts = cv2.findChessboardCornersSB(gray, size)
    if ok:
        return pts.astype(np.float32)
    return None


def _candidate_sizes(configured: tuple[int, int]) -> list[tuple[int, int]]:
    h, w = configured
    seen, ordered = set(), []

    def add(a: int, b: int):
        if a >= 3 and b >= 3 and (a, b) not in seen:
            seen.add((a, b))
            ordered.append((a, b))

    add(h, w)
    add(w, h)
    for a, b in sorted([(a, b) for a in range(3, 12) for b in range(3, 12)],
                       key=lambda s: abs(s[0] - h) + abs(s[1] - w)):
        add(a, b)
    return ordered


def _resolve_size(grays: list[np.ndarray], configured: tuple[int, int]) -> Optional[tuple[int, int]]:
    if not grays:
        return None
    for size in _candidate_sizes(configured):
        if sum(1 for g in grays if _detect_one(g, size) is not None) >= min(2, len(grays)):
            return size
    return None


def object_points(size: tuple[int, int], square_m: float) -> np.ndarray:
    h, w = size
    objp = np.zeros((h * w, 3), np.float32)
    objp[:, :2] = np.mgrid[0:h, 0:w].T.reshape(-1, 2) * square_m
    return objp


# ----------------------------------------------------------------------------- frame extraction

def _camera_video(intr_dir: Path) -> Optional[Path]:
    if not intr_dir.exists():
        return None
    vids = sorted(f for f in intr_dir.iterdir() if f.is_file() and f.suffix.lower() in _VIDEO_EXT)
    return vids[0] if vids else None


def _extract(video: Path, out_dir: Path) -> "subprocess.Popen":
    out_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        ["ffmpeg", "-v", "error", "-hwaccel", "videotoolbox", "-i", str(video),
         "-vf", f"fps={_EXTRACT_FPS},scale={_DET_WIDTH}:-1", "-an", str(out_dir / "f_%05d.jpg")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _detect_in_dir(frame_dir: Path, size: tuple[int, int]) -> dict[int, np.ndarray]:
    found: dict[int, np.ndarray] = {}
    for jpg in sorted(frame_dir.glob("f_*.jpg")):
        gray = cv2.cvtColor(cv2.imread(str(jpg)), cv2.COLOR_BGR2GRAY)
        pts = _detect_one(gray, size)
        if pts is not None:
            found[int(jpg.stem.split("_")[1])] = pts
    return found


# ----------------------------------------------------------------------------- pose math

def _board_pose(objp: np.ndarray, imgp: np.ndarray, K: np.ndarray, dist: np.ndarray):
    ok, rvec, tvec = cv2.solvePnP(objp, imgp, K, dist)
    if not ok:
        return None
    R, _ = cv2.Rodrigues(rvec)
    proj, _ = cv2.projectPoints(objp, rvec, tvec, K, dist)
    err = float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - imgp.reshape(-1, 2)) ** 2, axis=1))))
    return R, tvec.reshape(3), err


def _relative(pose_a, pose_b):
    """Transform points from camera A's frame into camera B's frame."""
    Ra, ta, _ = pose_a
    Rb, tb, _ = pose_b
    Rba = Rb @ Ra.T
    tba = tb - Rba @ ta
    return Rba, tba


def _invert(R: np.ndarray, t: np.ndarray):
    return R.T, -R.T @ t


def _offset_by_consistency(pa: dict, pb: dict, fps: int) -> tuple[int, int, float]:
    """Frame offset between two unsynced cameras, found geometrically: rigid
    cameras have ONE fixed relative pose, so the true offset is the one where the
    per-frame relative translation is most consistent (board co-detection alone
    is too weak — a waved board lines up at many wrong shifts)."""
    span = fps * _MAX_SYNC_OFFSET_S
    best = None  # (spread_m, -count, off)
    for off in range(-span, span + 1):
        aligned = [(k, k + off) for k in pa if (k + off) in pb]
        if len(aligned) < 5:
            continue
        ts = np.array([_relative(pa[ka], pb[kb])[1] for ka, kb in aligned])
        spread = float(np.median(np.linalg.norm(ts - np.median(ts, axis=0), axis=1)))
        cand = (round(spread, 4), -len(aligned), off)
        if best is None or cand < best:
            best = cand
    if best is None:
        return 0, 0, 1e9
    off = best[2]
    cnt = sum(1 for k in pa if (k + off) in pb)
    return off, cnt, best[0]


def _velocities(centroids: dict[int, np.ndarray]) -> dict[int, float]:
    """Per-frame board image-speed (px/frame), so we can prefer near-still moments."""
    ks = sorted(centroids)
    vel: dict[int, float] = {}
    for i, k in enumerate(ks):
        nbrs = ([ks[i - 1]] if i > 0 else []) + ([ks[i + 1]] if i < len(ks) - 1 else [])
        vel[k] = min((float(np.linalg.norm(centroids[k] - centroids[n])) / abs(k - n) for n in nbrs), default=1e9)
    return vel


def _solve_global_offsets(n: int, meas: list[tuple], reject_frames: float) -> np.ndarray:
    """Per-camera time offset (frames, cam0=0) from noisy pairwise measurements.
    A waved board makes some pairwise offsets lock onto wrong peaks; we fit all
    measurements jointly and iteratively drop the worst outlier until consistent."""
    active = list(range(len(meas)))
    o = np.zeros(n)
    for _ in range(len(meas)):
        rows, rhs = [], []
        for ia, ib, off, _w in (meas[i] for i in active):
            row = np.zeros(n - 1)
            if ia > 0:
                row[ia - 1] = -1
            if ib > 0:
                row[ib - 1] = 1
            rows.append(row)
            rhs.append(off)
        sol, *_ = np.linalg.lstsq(np.array(rows, float), np.array(rhs, float), rcond=None)
        o = np.concatenate([[0.0], sol])
        res = {i: abs((o[meas[i][1]] - o[meas[i][0]]) - meas[i][2]) for i in active}
        worst = max(active, key=lambda i: res[i])
        if res[worst] <= reject_frames or len(active) <= n - 1:
            break
        active.remove(worst)
    return o


def _average_relative(pairs: list[tuple]) -> tuple[np.ndarray, np.ndarray]:
    """Average several relative poses (cam A -> cam B): mean translation, SVD-averaged rotation."""
    Rs = [p[0] for p in pairs]
    ts = [p[1] for p in pairs]
    U, _, Vt = np.linalg.svd(sum(Rs))
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Vt
    return R, np.mean(ts, axis=0)


def _cluster_relative(rels: list[tuple], tol: float = 0.08):
    """Largest tight cluster of relative poses (rejects 180° board-flip frames)."""
    ts = np.array([r[1] for r in rels])
    counts = [int(np.sum(np.linalg.norm(ts - ts[i], axis=1) < tol)) for i in range(len(ts))]
    best = int(np.argmax(counts))
    inl = [j for j in range(len(ts)) if np.linalg.norm(ts[j] - ts[best]) < tol]
    return _average_relative([rels[j] for j in inl]), len(inl)


def _kabsch(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rigid transform (no scale) mapping src -> dst:  dst ≈ R @ src + t."""
    cs, cd = src.mean(0), dst.mean(0)
    H = (src - cs).T @ (dst - cd)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    return R, cd - R @ cs


# ----------------------------------------------------------------------------- public API

def calibrate_project(
    project_dir: Path,
    cameras: list[str],
    corners: tuple[int, int],
    square_mm: float,
    board_position: str = "horizontal",
    every_n_sec: float = 1.0,  # unused; kept for signature compatibility
    log: Callable[[str], None] = lambda _m: None,
) -> dict:
    square_m = square_mm / 1000.0
    cal_dir = project_dir / "calibration"
    videos = {c: _camera_video(cal_dir / "intrinsics" / f"int_{c}_img") for c in cameras}
    for c in cameras:
        if videos[c] is None:
            raise ValueError(f"{c}: a checkerboard video is required (image-only calibration isn't supported for spread cameras).")

    tmp = Path(tempfile.mkdtemp(prefix="calib_"))
    log("Extracting frames from the checkerboard videos…")
    procs = {c: _extract(videos[c], tmp / c) for c in cameras}
    for c, p in procs.items():
        p.wait()

    # Resolve the real board size from frames spread across the whole clip of
    # every camera (the board comes and goes, so don't just sample the start).
    probe = []
    for c in cameras:
        fs = sorted((tmp / c).glob("f_*.jpg"))
        if not fs:
            raise ValueError(f"{c}: no frames could be extracted from the video — is it a valid video file?")
        probe.extend(cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2GRAY) for f in fs[:: max(1, len(fs) // 5)][:5])
    size = _resolve_size(probe, corners)
    if size is None:
        raise ValueError(
            f"The {corners[0]}×{corners[1]} checkerboard wasn't found in the videos (every size from 3×3 to "
            "11×11 was tried). Count the INNER corners — the intersections where black squares meet."
        )
    if tuple(size) != tuple(corners):
        log(f"Board {corners[0]}×{corners[1]} didn't match; auto-detected {size[0]}×{size[1]} inner corners.")
    objp = object_points(size, square_m)

    # Detect board + calibrate intrinsics per camera.
    detections: dict[str, dict[int, np.ndarray]] = {}
    intr: dict[str, dict] = {}
    native = {}
    for c in cameras:
        det = _detect_in_dir(tmp / c, size)
        detections[c] = det
        log(f"{c}: board detected in {len(det)} frames")
        if len(det) < 4:
            raise ValueError(f"{c}: board detected in only {len(det)} frames (need ≥4). Use a clearer/longer clip or wave the board toward {c} more.")
        cap = cv2.VideoCapture(str(videos[c]))
        nw, nh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        det_dims = cv2.imread(str(next((tmp / c).glob("f_*.jpg")))).shape[:2]
        det_w = det_dims[1]
        keys = sorted(det)[:: max(1, len(det) // _MAX_INTRINSIC_VIEWS)][:_MAX_INTRINSIC_VIEWS]
        rms, K_s, dist, _, _ = cv2.calibrateCamera([objp] * len(keys), [det[k] for k in keys], (det_dims[1], det_dims[0]), None, None)
        s = nw / det_w  # scale intrinsics from detection res up to the camera's native res
        K = np.array([[K_s[0, 0] * s, 0, K_s[0, 2] * s], [0, K_s[1, 1] * s, K_s[1, 2] * s], [0, 0, 1]])
        intr[c] = {"K_s": K_s, "K": K, "dist": dist.ravel(), "rms": float(rms)}
        native[c] = (nw, nh)
        log(f"{c}: intrinsics from {len(keys)} views, RMS {rms:.3f} px")

    # Per-camera board pose + image centroid at each detected frame.
    poses: dict[str, dict[int, tuple]] = {}
    centroids: dict[str, dict[int, np.ndarray]] = {}
    for c in cameras:
        pc, cc = {}, {}
        for k, imgp in detections[c].items():
            p = _board_pose(objp, imgp, intr[c]["K_s"], intr[c]["dist"])
            if p is not None:
                pc[k] = p
                cc[k] = imgp.reshape(-1, 2).mean(axis=0)
        poses[c], centroids[c] = pc, cc
    K_s = {c: intr[c]["K_s"] for c in cameras}
    dist = {c: intr[c]["dist"] for c in cameras}

    # 1. Group cameras that are hardware-synced: a pair counts as synced when its
    # SAME-frame relative pose is consistent (tight cluster of translations).
    parent = {c: c for c in cameras}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    rel_cache: dict[tuple[str, str], tuple] = {}
    for ia in range(len(cameras)):
        for ib in range(ia + 1, len(cameras)):
            a, b = cameras[ia], cameras[ib]
            common = [k for k in poses[a] if k in poses[b]]
            if len(common) < 8:
                continue
            # Synced cameras share a fixed relative pose at the SAME frame index;
            # tolerance is generous (single-frame solvePnP on a far board is noisy,
            # esp. wide-angle) but unsynced pairs scatter over metres, not cm.
            (R_ab, t_ab), n = _cluster_relative([_relative(poses[a][k], poses[b][k]) for k in common], tol=0.3)
            if n >= 10:
                rel_cache[(a, b)] = (R_ab, t_ab)
                parent[find(a)] = find(b)

    groups: dict[str, list[str]] = {}
    for c in cameras:
        groups.setdefault(find(c), []).append(c)
    groups = list(groups.values())
    log("Synced camera groups: " + ", ".join("{" + ",".join(g) + "}" for g in groups))
    if any(len(g) < 2 for g in groups):
        solo = [g[0] for g in groups if len(g) < 2]
        raise ValueError(
            f"Camera(s) {', '.join(solo)} aren't time-synced with any other camera and never share a same-instant "
            "board view, so they can't be placed. Sync them (or pair each with a neighbour) and re-record."
        )

    # 2. Within-group extrinsics: chain the synced relative poses (group frame = group[0]).
    gpose: dict[str, tuple] = {}
    for g in groups:
        gpose[g[0]] = (np.eye(3), np.zeros(3))
        stack = [g[0]]
        while stack:
            p = stack.pop()
            Rp, tp = gpose[p]
            for c in g:
                if c in gpose:
                    continue
                if (p, c) in rel_cache:
                    R_pc, t_pc = rel_cache[(p, c)]
                elif (c, p) in rel_cache:
                    R_pc, t_pc = _invert(*rel_cache[(c, p)])
                else:
                    continue
                gpose[c] = (R_pc @ Rp, R_pc @ tp + t_pc)
                stack.append(c)

    # 3. Board 3D-center trajectory per group (in that group's frame).
    def group_traj(g: list[str]) -> dict[int, np.ndarray]:
        Pm = {c: K_s[c] @ np.hstack([gpose[c][0], gpose[c][1].reshape(3, 1)]) for c in g}
        traj: dict[int, np.ndarray] = {}
        for k in set().union(*[set(detections[c]) for c in g]):
            here = [c for c in g if k in detections[c]]
            if len(here) < 2:
                continue
            a, b = here[:2]
            ua = cv2.undistortPoints(detections[a][k], K_s[a], dist[a], P=K_s[a]).reshape(-1, 2)
            ub = cv2.undistortPoints(detections[b][k], K_s[b], dist[b], P=K_s[b]).reshape(-1, 2)
            X = cv2.triangulatePoints(Pm[a], Pm[b], ua.T, ub.T)
            traj[k] = ((X[:3] / X[3]).T).mean(axis=0)
        return traj

    trajs = [group_traj(g) for g in groups]

    # 4. Link every group to group 0 by registering the board's 3D trajectory
    # (rigid Kabsch fit at the best time offset — no fragile corner matching).
    def link(traj_ref: dict, traj_other: dict):
        span = _EXTRACT_FPS * _MAX_SYNC_OFFSET_S
        best = None
        ko = set(traj_other)
        for off in range(-span, span + 1):
            ks = [k for k in traj_ref if (k + off) in ko]
            if len(ks) < 6:
                continue
            P_ref = np.array([traj_ref[k] for k in ks])
            P_oth = np.array([traj_other[k + off] for k in ks])
            R, t = _kabsch(P_oth, P_ref)
            res = float(np.median(np.linalg.norm((P_oth @ R.T + t) - P_ref, axis=1)))
            if best is None or res < best[0]:
                best = (res, R, t, off)
        return best

    world: dict[str, tuple] = {c: gpose[c] for c in groups[0]}
    ref = groups[0][0]
    for gi in range(1, len(groups)):
        res = link(trajs[0], trajs[gi])
        if res is None or res[0] > 0.10:
            raise ValueError(
                f"Couldn't align camera group {{{','.join(groups[gi])}}} to the others — the board's path wasn't "
                "seen clearly enough by both groups. Wave the board through the shared space a bit more."
            )
        _, Rl, tl, off = res
        log(f"Linked {{{','.join(groups[gi])}}} → reference: time offset {off / _EXTRACT_FPS:+.1f}s, fit {res[0] * 1000:.0f} mm")
        for c in groups[gi]:
            Rc, tc = gpose[c]
            world[c] = (Rc @ Rl.T, tc - Rc @ Rl.T @ tl)

    # Write Calib.toml.
    calib_toml: dict = {}
    report: list[dict] = []
    for c in cameras:
        R, t = world[c]
        rvec, _ = cv2.Rodrigues(R)
        K, dist = intr[c]["K"], intr[c]["dist"]
        calib_toml[c] = {
            "name": c,
            "size": [float(native[c][0]), float(native[c][1])],
            "matrix": [[float(K[0, 0]), 0.0, float(K[0, 2])], [0.0, float(K[1, 1]), float(K[1, 2])], [0.0, 0.0, 1.0]],
            "distortions": [float(dist[0]), float(dist[1]), float(dist[2]), float(dist[3])],
            "rotation": [float(x) for x in rvec.reshape(3)],
            "translation": [float(x) for x in t],
            "fisheye": False,
        }
        report.append({
            "camera": c,
            "reproj_error_px": round(intr[c]["rms"], 4),
            "intrinsics_error_px": round(intr[c]["rms"], 4),
            "intrinsics_views": len(detections[c]),
            "board_detected": True,
        })

    calib_toml["metadata"] = {"adjusted": False, "error": 0.0}
    out = cal_dir / "Calib.toml"
    rtoml.dump(calib_toml, out)
    return {
        "calib_file": out.name,
        "cameras": report,
        "max_error_px": max(c["reproj_error_px"] for c in report),
        "resolved_corners": [int(size[0]), int(size[1])],
        "reference_camera": ref,
    }
