"""Generate a version-matched Pose2Sim Config.toml.

Strategy: start from the demo Config.toml shipped *inside the installed
Pose2Sim package* (so every default is exactly what this library version
expects), then override only the keys we control. All interactive GUI/plot
flags are forced off so stages never block a headless worker.
"""
from __future__ import annotations

import copy
import logging
import platform
from functools import lru_cache
from pathlib import Path

import rtoml

from app.models import ProjectParams

log = logging.getLogger("uvicorn.error")


def select_pose_runtime() -> dict:
    """Force the discrete NVIDIA GPU (CUDA) for pose inference off macOS.

    CUDA runs ONLY on an NVIDIA card — an Intel/AMD integrated GPU is not a CUDA
    device, so this can never fall back to the iGPU. It also does not fall back to
    CPU: the worker calls require_cuda() before pose estimation and fails loudly if
    the NVIDIA runtime is missing, so a job never silently crawls on the CPU. macOS
    stays on CPU (Apple Silicon MPS yields garbage keypoints; macOS is dev-only).
    """
    if platform.system() == "Darwin":
        return {"device": "cpu", "backend": "onnxruntime", "workers": 1}
    # One worker: a single GPU is saturated by one session and parallel sessions
    # contend for VRAM. Use "cuda:0" here to pin a specific card if a host ever
    # has more than one NVIDIA GPU.
    return {"device": "cuda", "backend": "onnxruntime", "workers": 1}


def require_cuda() -> None:
    """Fail loudly if GPU inference is forced but the NVIDIA CUDA provider is absent,
    rather than letting onnxruntime silently fall back to the CPU."""
    try:
        import onnxruntime as ort

        available = ort.get_available_providers()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"onnxruntime is not usable ({exc!r}); cannot run GPU pose estimation.") from exc
    if "CUDAExecutionProvider" not in available:
        raise RuntimeError(
            "GPU inference is forced (pose.device=cuda) but no CUDAExecutionProvider is available "
            f"(providers: {available}). Install onnxruntime-gpu and the NVIDIA CUDA 12.x + cuDNN runtime "
            "(windows-install.cmd installs the pip package). Refusing to fall back to CPU or the integrated GPU."
        )


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
    runtime = select_pose_runtime()
    log.info("Pose runtime: device=%s backend=%s workers=%s",
             runtime["device"], runtime["backend"], runtime["workers"])

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
        "pose.det_frequency": params.det_frequency,
        # Device/backend/workers are chosen for the host (CUDA GPU when present).
        "pose.device": runtime["device"],
        "pose.backend": runtime["backend"],
        "pose.parallel_workers_pose": runtime["workers"],
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
