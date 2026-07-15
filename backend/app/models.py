from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Stage(str, Enum):
    calibration = "calibration"
    poseEstimation = "poseEstimation"
    synchronization = "synchronization"
    personAssociation = "personAssociation"
    triangulation = "triangulation"
    filtering = "filtering"
    markerAugmentation = "markerAugmentation"
    kinematics = "kinematics"


PROCESSING_STAGES: list[Stage] = [
    Stage.poseEstimation,
    Stage.synchronization,
    Stage.personAssociation,
    Stage.triangulation,
    Stage.filtering,
    Stage.markerAugmentation,
    Stage.kinematics,
]


class ProjectParams(BaseModel):
    """User-facing capture + processing parameters for one project."""

    name: str = Field(..., min_length=1, max_length=120)
    n_cameras: int = Field(4, ge=2, le=12)

    # Checkerboard (inner corners — intersections, NOT square count).
    board_corners_h: int = Field(6, ge=3, le=30)
    board_corners_w: int = Field(7, ge=3, le=30)
    square_size_mm: float = Field(105.0, gt=0)
    board_position: Literal["horizontal", "vertical"] = "horizontal"

    # Subject biometrics — measured values give accurate OpenSim scaling.
    participant_height_m: Optional[float] = Field(None, gt=0.3, le=2.6)
    participant_mass_kg: Optional[float] = Field(None, gt=2, le=300)

    frame_rate: Optional[float] = Field(None, gt=0, description="None -> auto-detect from video")
    multi_person: bool = False

    # Pipeline behaviour
    do_synchronization: bool = True
    do_marker_augmentation: bool = True
    use_simple_model: bool = False  # full OpenSim model = more accurate IK
    filter_cutoff_hz: float = Field(6.0, gt=0)

    pose_model: str = "Body_with_feet"
    pose_mode: Literal["lightweight", "balanced", "performance"] = "balanced"
    # Detector runs every Nth frame; keypoints are tracked in between. Pose2Sim's
    # own default is 4 — running detection every frame (1) is ~4x the detector work
    # for negligible accuracy gain on walking. Device/backend/workers are chosen
    # per host, so they are not user parameters.
    det_frequency: int = Field(4, ge=1, le=30)

    intrinsics_extension: str = "mp4"
    extrinsics_extension: str = "png"
    video_extension: str = "mp4"


class CameraError(BaseModel):
    camera: str
    reproj_error_px: Optional[float] = None  # extrinsics board reprojection error
    intrinsics_error_px: Optional[float] = None
    intrinsics_views: Optional[int] = None  # checkerboard views used for intrinsics
    board_detected: Optional[bool] = None


class SubjectSelection(BaseModel):
    """A user click identifying the subject in one camera's trial video."""

    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    time_s: float = Field(..., ge=0)


class CalibrationResult(BaseModel):
    status: Literal["pending", "running", "done", "failed", "accepted"] = "pending"
    calib_file: Optional[str] = None
    cameras: list[CameraError] = []
    max_error_px: Optional[float] = None
    message: Optional[str] = None


class JobState(BaseModel):
    id: str
    kind: Literal["calibration", "processing"]
    status: Literal["queued", "running", "done", "failed"] = "queued"
    stages: list[str] = []
    current_stage: Optional[str] = None
    pct: float = 0.0
    error: Optional[str] = None


class ResultsSummary(BaseModel):
    has_angles: bool = False
    has_positions: bool = False
    n_frames: Optional[int] = None
    duration_s: Optional[float] = None
    frame_rate: Optional[float] = None
    angle_columns: list[str] = []
    marker_names: list[str] = []
    calibration: Optional[CalibrationResult] = None


class ProjectMeta(BaseModel):
    id: str
    params: ProjectParams
    cameras: list[str]
    status: Literal["created", "calibrated", "processing", "processed", "failed"] = "created"
    calibration: CalibrationResult = CalibrationResult()
    subject_selections: dict[str, SubjectSelection] = Field(default_factory=dict)
    job: Optional[JobState] = None
