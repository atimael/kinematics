"""Project lifecycle + on-disk Pose2Sim layout.

Each project is a self-contained Pose2Sim *single-trial* directory:

    data/projects/<id>/
      Config.toml
      project.json                      # our ProjectMeta
      calibration/
        intrinsics/int_cam01_img/ ...   # per-camera checkerboard footage
        extrinsics/cam01_ext.png  ...   # one synchronized board frame per camera
        Calib_board.toml                # produced by the calibration stage
      videos/cam01.mp4 ...              # trial footage (one per camera)
      pose/ pose-3d/ kinematics/        # created by the pipeline
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from app.models import ProjectMeta, ProjectParams
from app.pipeline.config import write_config

DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "projects"


def camera_names(n: int) -> list[str]:
    return [f"cam{i:02d}" for i in range(1, n + 1)]


def project_dir(project_id: str) -> Path:
    return DATA_ROOT / project_id


def intrinsics_dir(project_id: str, camera: str) -> Path:
    return project_dir(project_id) / "calibration" / "intrinsics" / f"int_{camera}_img"


def extrinsics_dir(project_id: str) -> Path:
    return project_dir(project_id) / "calibration" / "extrinsics"


def videos_dir(project_id: str) -> Path:
    return project_dir(project_id) / "videos"


def calibration_dir(project_id: str) -> Path:
    return project_dir(project_id) / "calibration"


def _meta_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.json"


def create_project(params: ProjectParams) -> ProjectMeta:
    project_id = uuid.uuid4().hex[:12]
    cams = camera_names(params.n_cameras)
    root = project_dir(project_id)

    for cam in cams:
        intrinsics_dir(project_id, cam).mkdir(parents=True, exist_ok=True)
    extrinsics_dir(project_id).mkdir(parents=True, exist_ok=True)
    videos_dir(project_id).mkdir(parents=True, exist_ok=True)

    write_config(root, params)

    meta = ProjectMeta(id=project_id, params=params, cameras=cams)
    save_meta(meta)
    return meta


def save_meta(meta: ProjectMeta) -> None:
    _meta_path(meta.id).write_text(meta.model_dump_json(indent=2))


def load_meta(project_id: str) -> ProjectMeta | None:
    p = _meta_path(project_id)
    if not p.exists():
        return None
    return ProjectMeta.model_validate_json(p.read_text())


def list_metas() -> list[ProjectMeta]:
    if not DATA_ROOT.exists():
        return []
    out = []
    for child in DATA_ROOT.iterdir():
        if child.is_dir() and (m := load_meta(child.name)):
            out.append(m)
    return out


def delete_project(project_id: str) -> bool:
    root = project_dir(project_id)
    if root.exists():
        shutil.rmtree(root)
        return True
    return False


def clear_uploads(dir_path: Path) -> None:
    """Remove existing files in an upload target so re-uploads don't accumulate."""
    if dir_path.exists():
        for f in dir_path.iterdir():
            if f.is_file():
                f.unlink()
