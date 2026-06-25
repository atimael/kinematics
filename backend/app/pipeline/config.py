"""Generate a version-matched Pose2Sim Config.toml.

Strategy: start from the demo Config.toml shipped *inside the installed
Pose2Sim package* (so every default is exactly what this library version
expects), then override only the keys we control. All interactive GUI/plot
flags are forced off so stages never block a headless worker.
"""
from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path

import rtoml

from app.models import ProjectParams


@lru_cache(maxsize=1)
def _demo_config() -> dict:
    import Pose2Sim

    demo = Path(Pose2Sim.__file__).parent / "Demo_SinglePerson" / "Config.toml"
    cfg = rtoml.load(demo)
    # Custom skeleton table is only consulted for custom pose models; drop it
    # so it can never interfere and to keep the generated file clean.
    cfg.get("pose", {}).pop("CUSTOM", None)
    return cfg


# Every interactive/blocking flag, keyed by dotted path -> forced value.
_HEADLESS_OVERRIDES: dict[str, object] = {
    "pose.display_detection": False,
    "pose.save_video": "none",
    "pose.overwrite_pose": False,
    "synchronization.synchronization_gui": False,
    "synchronization.display_sync_plots": False,
    "synchronization.save_sync_plots": False,
    "calibration.calculate.save_debug_images": True,
    "calibration.calculate.intrinsics.show_detection_intrinsics": False,
    "calibration.calculate.extrinsics.show_reprojection_error": False,
    # Pose2Sim clobbers the line above back to True when it is False, reading
    # this nested key instead (calibration.py: `if not show_reprojection_error`).
    # Must also be False or the headless extrinsics step opens a GUI clicker.
    "calibration.calculate.extrinsics.board.show_reprojection_error": False,
    "triangulation.show_interp_indices": False,
    "filtering.display_figures": False,
    "filtering.save_filt_plots": False,
}


def _set(cfg: dict, dotted: str, value: object) -> None:
    keys = dotted.split(".")
    node = cfg
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value


def build_config_dict(params: ProjectParams) -> dict:
    cfg = copy.deepcopy(_demo_config())

    corners = [params.board_corners_h, params.board_corners_w]

    overrides: dict[str, object] = {
        "project.project_dir": ".",
        "project.multi_person": params.multi_person,
        "project.participant_height": params.participant_height_m
        if params.participant_height_m is not None
        else "auto",
        "project.participant_mass": params.participant_mass_kg
        if params.participant_mass_kg is not None
        else 70.0,
        "project.frame_rate": params.frame_rate if params.frame_rate is not None else "auto",
        "project.frame_range": "all",
        "pose.pose_model": params.pose_model,
        "pose.mode": params.pose_mode,
        # Force CPU/onnxruntime: device='auto' picks MPS on Apple Silicon, whose
        # onnxruntime CoreML provider miscomputes output ranks on the YOLOX
        # detector and silently produces garbage keypoints (-> nothing
        # triangulates). CPU inference is slower but correct.
        "pose.device": "CPU",
        "pose.backend": "onnxruntime",
        # Parallel pose workers deadlock onnxruntime on macOS (worker hangs at 0%
        # CPU mid-run). Sequential is slower but reliable.
        "pose.parallel_workers_pose": 1,
        # Calibration: compute from the user's checkerboard footage, board extrinsics.
        "calibration.calibration_type": "calculate",
        "calibration.calculate.intrinsics.intrinsics_extension": params.intrinsics_extension,
        "calibration.calculate.intrinsics.intrinsics_corners_nb": corners,
        "calibration.calculate.intrinsics.intrinsics_square_size": params.square_size_mm,
        "calibration.calculate.extrinsics.calculate_extrinsics": True,
        "calibration.calculate.extrinsics.extrinsics_method": "board",
        "calibration.calculate.extrinsics.extrinsics_extension": params.extrinsics_extension,
        "calibration.calculate.extrinsics.board.board_position": params.board_position,
        "calibration.calculate.extrinsics.board.extrinsics_corners_nb": corners,
        "calibration.calculate.extrinsics.board.extrinsics_square_size": params.square_size_mm,
        # Filtering + IK
        "filtering.type": "butterworth",
        "filtering.butterworth.cut_off_frequency": params.filter_cutoff_hz,
        "kinematics.use_augmentation": params.do_marker_augmentation,
        "kinematics.use_simple_model": params.use_simple_model,
    }

    for path, value in {**overrides, **_HEADLESS_OVERRIDES}.items():
        _set(cfg, path, value)

    return cfg


def write_config(project_dir: Path, params: ProjectParams) -> Path:
    cfg = build_config_dict(params)
    out = project_dir / "Config.toml"
    rtoml.dump(cfg, out)
    return out
