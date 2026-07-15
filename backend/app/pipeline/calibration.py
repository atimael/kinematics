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

import os
import tempfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import rtoml

cv2.ocl.setUseOpenCL(False)
# Detection is parallelised at the Python level (one thread per frame); keep each
# OpenCV call single-threaded so the two don't oversubscribe the cores.
cv2.setNumThreads(1)
_DET_WORKERS = max(2, (os.cpu_count() or 4))

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


def _extract(video: Path, out_dir: Path) -> int:
    """Extract evenly spaced detection frames without a system ffmpeg install.

    OpenCV wheels include their own video backend, so this also works on locked
    down Windows machines where ffmpeg is not on PATH. The previous command used
    macOS-only VideoToolbox acceleration and failed before producing any frames
    on Windows.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"{video.name}: the video could not be opened. Try an MP4 file encoded with H.264.")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps <= 0:
        fps = 30.0
    sample_step = max(fps / _EXTRACT_FPS, 1.0)
    next_sample = 0.0
    input_index = 0
    output_index = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if input_index + 1e-6 < next_sample:
                input_index += 1
                continue

            height, width = frame.shape[:2]
            if width <= 0 or height <= 0:
                input_index += 1
                next_sample += sample_step
                continue
            scaled_height = max(1, round(height * _DET_WIDTH / width))
            interpolation = cv2.INTER_AREA if width > _DET_WIDTH else cv2.INTER_LINEAR
            frame = cv2.resize(frame, (_DET_WIDTH, scaled_height), interpolation=interpolation)

            output_index += 1
            dest = out_dir / f"f_{output_index:05d}.jpg"
            if not cv2.imwrite(str(dest), frame):
                raise ValueError(f"{video.name}: failed to write extracted calibration frames.")
            next_sample += sample_step
            input_index += 1
    finally:
        cap.release()

    return output_index


def _detect_one_file(jpg: Path, size: tuple[int, int]) -> Optional[tuple[int, np.ndarray]]:
    gray = cv2.cvtColor(cv2.imread(str(jpg)), cv2.COLOR_BGR2GRAY)
    pts = _detect_one(gray, size)
    return (int(jpg.stem.split("_")[1]), pts) if pts is not None else None


def _detect_in_dir(frame_dir: Path, size: tuple[int, int]) -> dict[int, np.ndarray]:
    """Detect the board in every extracted frame. Runs one thread per frame —
    cv2.imread and findChessboardCorners release the GIL, so this scales with
    cores and is the difference between a slow and a quick calibration."""
    jpgs = sorted(frame_dir.glob("f_*.jpg"))
    found: dict[int, np.ndarray] = {}
    with ThreadPoolExecutor(max_workers=_DET_WORKERS) as pool:
        for res in pool.map(lambda p: _detect_one_file(p, size), jpgs):
            if res is not None:
                found[res[0]] = res[1]
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

def _solve_world_extrinsics(
    cameras: list[str],
    poses: dict[str, dict[int, tuple]],
    detections: dict[str, dict[int, np.ndarray]],
    K_s: dict[str, np.ndarray],
    dist: dict[str, np.ndarray],
    objp: np.ndarray,
    log: Callable[[str], None] = lambda _m: None,
) -> tuple[dict[str, tuple], str]:
    """Place every camera in one world frame. Returns {camera: (R, t)} (world->camera)
    and the reference camera name.

    Hardware-synced cameras (consistent same-frame relative board pose) are grouped
    and solved by chained relative poses. Each group — INCLUDING a single unsynced
    camera on its own — is then registered to the reference by rigidly aligning its
    metric board-centroid trajectory at the best time offset. A solo camera is placeable
    because its trajectory comes from its own solvePnP board pose, no pair required.
    """
    # 1. Group cameras that are hardware-synced: a pair counts as synced when its
    # SAME-frame relative pose is consistent (tight cluster of translations).
    parent = {c: c for c in cameras}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _stereo_relative(a: str, b: str, common: list[int]) -> Optional[tuple]:
        """Accurate a->b relative pose from all co-visible board corners, jointly
        optimised (cv2.stereoCalibrate). A plain checkerboard viewed from different
        angles gets numbered 180°-rotated between cameras, which breaks the corner
        correspondence — so we try b's corners as-is AND reversed and keep whichever
        gives the lower stereo reprojection error. Returns (R, t, flip_b) or None if
        neither ordering fits well. flip_b tells the caller b's corners are reversed
        relative to a (needed so triangulation pairs the same physical corners)."""
        if len(common) < 6:
            return None
        objpts = [objp.reshape(-1, 1, 3).astype(np.float32) for _ in common]
        img_a = [detections[a][k].reshape(-1, 1, 2).astype(np.float32) for k in common]
        w = int(round(K_s[a][0, 2] * 2)) or 1600
        h = int(round(K_s[a][1, 2] * 2)) or 1200
        best = None
        for flip in (False, True):
            img_b = [(detections[b][k][::-1] if flip else detections[b][k]).reshape(-1, 1, 2).astype(np.float32)
                     for k in common]
            try:
                ret, *_, R, T, _, _ = cv2.stereoCalibrate(
                    objpts, img_a, img_b, K_s[a], dist[a], K_s[b], dist[b], (w, h),
                    flags=cv2.CALIB_FIX_INTRINSIC,
                    criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-5),
                )
            except cv2.error:
                continue
            if np.isfinite(ret) and (best is None or ret < best[0]):
                best = (ret, R, T.reshape(3), flip)
        if best is None or best[0] > 1.5:  # px; neither ordering fits -> genuinely bad pair
            return None
        return best[1], best[2], best[3]

    rel_cache: dict[tuple[str, str], tuple] = {}
    pair_flip: dict[tuple[str, str], bool] = {}
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
                refined = _stereo_relative(a, b, common)
                if refined is not None:
                    R_ref, t_ref, flip_b = refined
                    rel_cache[(a, b)] = (R_ref, t_ref)
                    pair_flip[(a, b)] = pair_flip[(b, a)] = flip_b
                    log(f"Pair {a}-{b}: stereo-calibrated from {len(common)} shared views (corner flip: {flip_b})")
                else:
                    rel_cache[(a, b)] = (R_ab, t_ab)
                    pair_flip[(a, b)] = pair_flip[(b, a)] = False
                    log(f"Pair {a}-{b}: averaged relative pose from {len(common)} shared views (stereo fit poor)")
                parent[find(a)] = find(b)

    groups: dict[str, list[str]] = {}
    for c in cameras:
        groups.setdefault(find(c), []).append(c)
    # Reference = the largest synced group: it has a triangulated (clean) board
    # trajectory, so every other group registers to the most reliable anchor.
    groups = sorted(groups.values(), key=len, reverse=True)
    log("Synced camera groups (reference first): " + ", ".join("{" + ",".join(g) + "}" for g in groups))

    # Propagate the per-pair corner-flip parity within each group so its cameras
    # agree on the physical numbering of the board corners (needed to triangulate).
    corner_flip = {c: False for c in cameras}
    for g in groups:
        placed = {g[0]: False}
        stack = [g[0]]
        while stack:
            p = stack.pop()
            for c in g:
                if c not in placed and (p, c) in pair_flip:
                    placed[c] = placed[p] ^ pair_flip[(p, c)]
                    stack.append(c)
        corner_flip.update(placed)

    def _board_corners(c: str, k: int) -> np.ndarray:
        d = detections[c][k]
        return d[::-1] if corner_flip[c] else d

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

    # 3. Board 3D-center trajectory per group (in that group's frame). With >=2
    # cameras seeing the board we triangulate; with a single camera we fall back
    # to its solvePnP board pose (metric, thanks to the known square size). The
    # single-camera path is what lets an unsynced or solo camera be placed at all
    # — it is registered to the reference by its board trajectory in stage 4.
    objp_centroid = objp.mean(axis=0)

    def group_traj(g: list[str]) -> dict[int, np.ndarray]:
        Pm = {c: K_s[c] @ np.hstack([gpose[c][0], gpose[c][1].reshape(3, 1)]) for c in g}
        traj: dict[int, np.ndarray] = {}
        for k in set().union(*[set(detections[c]) for c in g]):
            here = [c for c in g if k in detections[c]]
            if len(here) >= 2:
                a, b = here[:2]
                ua = cv2.undistortPoints(_board_corners(a, k), K_s[a], dist[a], P=K_s[a]).reshape(-1, 2)
                ub = cv2.undistortPoints(_board_corners(b, k), K_s[b], dist[b], P=K_s[b]).reshape(-1, 2)
                X = cv2.triangulatePoints(Pm[a], Pm[b], ua.T, ub.T)
                traj[k] = ((X[:3] / X[3]).T).mean(axis=0)
            elif here and k in poses[here[0]]:
                c = here[0]
                R_bc, t_bc, _ = poses[c][k]
                board_c = R_bc @ objp_centroid + t_bc  # board centroid in camera c's frame
                R_g, t_g = gpose[c]
                traj[k] = R_g.T @ (board_c - t_g)  # -> group frame
        return traj

    trajs = [group_traj(g) for g in groups]

    # 4. Register groups into one world frame. Two groups can be linked when the
    # board's 3D path overlaps in time between them (rigid Kabsch at the best time
    # offset). A planar board is only ever co-visible to NEIGHBOURING cameras, so
    # we chain neighbour-to-neighbour: build the graph of linkable group pairs and
    # walk a spanning tree out from the reference group. No group ever has to
    # co-see the board with all the others — only with a neighbour in the chain.
    def link(traj_ref: dict, traj_other: dict):
        """Best rigid map from traj_other's frame into traj_ref's frame over the
        time-offset search: (residual_m, R, t, offset, n_overlap) or None, plus the
        largest shared-frame count seen (for diagnostics)."""
        span = _EXTRACT_FPS * _MAX_SYNC_OFFSET_S
        best = None
        max_overlap = 0
        ko = set(traj_other)
        for off in range(-span, span + 1):
            ks = [k for k in traj_ref if (k + off) in ko]
            max_overlap = max(max_overlap, len(ks))
            if len(ks) < 6:
                continue
            P_ref = np.array([traj_ref[k] for k in ks])
            P_oth = np.array([traj_other[k + off] for k in ks])
            R, t = _kabsch(P_oth, P_ref)
            res = float(np.median(np.linalg.norm((P_oth @ R.T + t) - P_ref, axis=1)))
            if best is None or res < best[0]:
                best = (res, R, t, off, len(ks))
        return best, max_overlap

    _LINK_TOL_M = 0.10
    ng = len(groups)

    # Pairwise: edge[(i, j)] maps group j's frame -> group i's frame when their
    # board paths align closely enough. overlap/residual are kept for diagnostics.
    edge: dict[tuple[int, int], tuple] = {}
    overlap: dict[tuple[int, int], int] = {}
    residual: dict[tuple[int, int], Optional[float]] = {}
    for i in range(ng):
        for j in range(i + 1, ng):
            best, max_ov = link(trajs[i], trajs[j])
            overlap[(i, j)] = overlap[(j, i)] = max_ov
            residual[(i, j)] = residual[(j, i)] = best[0] if best else None
            if best is not None and best[0] <= _LINK_TOL_M:
                _, R, t, off, nov = best
                edge[(i, j)] = (R, t)
                edge[(j, i)] = _invert(R, t)
                log(f"Link {{{','.join(groups[i])}}} <-> {{{','.join(groups[j])}}}: "
                    f"offset {off / _EXTRACT_FPS:+.1f}s, fit {best[0] * 1000:.0f} mm over {nov} frames")

    # Spanning tree out from the reference (group 0), chaining transforms to world.
    group_to_world: dict[int, tuple] = {0: (np.eye(3), np.zeros(3))}
    stack = [0]
    while stack:
        i = stack.pop()
        Riw, tiw = group_to_world[i]
        for j in range(ng):
            if j in group_to_world or (i, j) not in edge:
                continue
            Rji, tji = edge[(i, j)]  # j frame -> i frame
            group_to_world[j] = (Riw @ Rji, Riw @ tji + tiw)  # j frame -> world
            stack.append(j)

    unplaced = [gi for gi in range(ng) if gi not in group_to_world]
    if unplaced:
        gi = unplaced[0]
        grp = "{" + ",".join(groups[gi]) + "}"
        placed = list(group_to_world)
        best_ov = max((overlap[(p, gi)] for p in placed), default=0)
        reslist = [residual[(p, gi)] for p in placed if residual[(p, gi)] is not None]
        if best_ov < 6 or not reslist:
            raise ValueError(
                f"Camera group {grp} never shares the board's path with the rest of the rig "
                f"(at most {best_ov} shared frames with any connected group, need ≥6). The board must pass through "
                "the OVERLAP between neighbouring cameras so the chain reaches this group — sweep it slowly around "
                "the whole capture volume, handing it off from one camera's view to the next, not just in front of "
                "these cameras."
            )
        raise ValueError(
            f"Camera group {grp} overlaps the rig but couldn't be aligned (best fit {min(reslist) * 1000:.0f} mm "
            f"over {best_ov} shared frames, need <{_LINK_TOL_M * 1000:.0f} mm). The board was likely too far or "
            "oblique where these views overlap — record it larger and more front-on in the space the groups share."
        )

    world: dict[str, tuple] = {}
    for gi in range(ng):
        Rgw, tgw = group_to_world[gi]
        for c in groups[gi]:
            Rc, tc = gpose[c]
            world[c] = (Rc @ Rgw.T, tc - Rc @ Rgw.T @ tgw)
    ref = groups[0][0]
    return world, ref


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
    with ThreadPoolExecutor(max_workers=min(4, len(cameras))) as pool:
        tasks = {c: pool.submit(_extract, videos[c], tmp / c) for c in cameras}
        for c, task in tasks.items():
            log(f"{c}: extracted {task.result()} frames")

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

    world, ref = _solve_world_extrinsics(cameras, poses, detections, K_s, dist, objp, log)

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

    # Guard against a degenerate extrinsics solve: every non-reference camera
    # must sit at a distinct pose. If they all collapse onto the reference origin
    # (all-zero translation), triangulation silently produces garbage and trims
    # the trial to a few frames — fail loudly here instead.
    others = [c for c in cameras if c != ref]
    for c in cameras:
        vals = calib_toml[c]["rotation"] + calib_toml[c]["translation"]
        if any(not np.isfinite(v) for v in vals):
            raise ValueError(f"{c}: calibration produced non-finite extrinsics — check board detection.")
    if others and all(all(abs(v) < 1e-9 for v in calib_toml[c]["translation"]) for c in others):
        raise ValueError(
            "Extrinsics collapsed to the origin (all cameras share one pose). "
            "The checkerboard was likely not co-visible across camera pairs — re-record calibration "
            "so overlapping cameras see the board together."
        )

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
