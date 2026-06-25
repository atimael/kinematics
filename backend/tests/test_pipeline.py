"""Unit tests for config generation and output parsing (no Pose2Sim run needed)."""
from pathlib import Path

from app.models import ProjectParams
from app.pipeline import outputs
from app.pipeline.config import build_config_dict

TRC = """PathFileType\t4\t(X/Y/Z)\ttest.trc
DataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\tOrigDataRate\tOrigDataStartFrame\tOrigNumFrames
60\t60\t2\t2\tm\t60\t1\t2
Frame#\tTime\tRHip\t\t\tRKnee\t\t
\t\tX1\tY1\tZ1\tX2\tY2\tZ2
1\t0.000\t0.1\t0.2\t0.3\t0.4\t0.5\t0.6
2\t0.0167\t0.11\t0.21\t0.31\t0.41\t0.51\t0.61
"""

MOT = """test
version=1
nRows=2
nColumns=3
inDegrees=yes
endheader
time\thip_flexion_r\tknee_angle_r
0.000\t10.5\t-5.2
0.0167\t11.0\t-4.8
"""


def test_parse_trc(tmp_path: Path):
    p = tmp_path / "a.trc"
    p.write_text(TRC)
    df, info = outputs.parse_trc(p)
    assert info["markers"] == ["RHip", "RKnee"]
    assert info["units"] == "m"
    assert list(df.columns) == ["Frame", "Time", "RHip_X", "RHip_Y", "RHip_Z", "RKnee_X", "RKnee_Y", "RKnee_Z"]
    assert df.shape == (2, 8)
    assert abs(df["RKnee_Z"].iloc[1] - 0.61) < 1e-9


def test_parse_mot(tmp_path: Path):
    p = tmp_path / "a.mot"
    p.write_text(MOT)
    df, info = outputs.parse_mot(p)
    assert info["in_degrees"] is True
    assert info["columns"] == ["hip_flexion_r", "knee_angle_r"]
    assert df["Time"].iloc[0] == 0.0
    assert abs(df["knee_angle_r"].iloc[0] + 5.2) < 1e-9


def test_chart_series_and_csv(tmp_path: Path):
    p = tmp_path / "a.mot"
    p.write_text(MOT)
    df, _ = outputs.parse_mot(p)
    chart = outputs.chart_series(df, ["knee_angle_r"])
    assert chart["time"] == [0.0, 0.0167]
    assert chart["series"]["knee_angle_r"] == [-5.2, -4.8]
    assert b"knee_angle_r" in outputs.df_to_csv_bytes(df)


def test_config_is_headless_and_calculate():
    cfg = build_config_dict(ProjectParams(name="t", n_cameras=3, square_size_mm=105))
    cal = cfg["calibration"]
    assert cal["calibration_type"] == "calculate"
    assert cal["calculate"]["extrinsics"]["extrinsics_method"] == "board"
    # Every interactive flag must be off (incl. the nested board override).
    assert cfg["pose"]["display_detection"] is False
    assert cfg["pose"]["device"] == "CPU"
    assert cfg["synchronization"]["synchronization_gui"] is False
    assert cal["calculate"]["intrinsics"]["show_detection_intrinsics"] is False
    assert cal["calculate"]["extrinsics"]["show_reprojection_error"] is False
    assert cal["calculate"]["extrinsics"]["board"]["show_reprojection_error"] is False


def test_config_corner_and_biometrics():
    cfg = build_config_dict(
        ProjectParams(name="t", n_cameras=4, board_corners_h=6, board_corners_w=7,
                      square_size_mm=105, participant_height_m=1.8, participant_mass_kg=75)
    )
    intr = cfg["calibration"]["calculate"]["intrinsics"]
    assert intr["intrinsics_corners_nb"] == [6, 7]
    assert intr["intrinsics_square_size"] == 105
    assert cfg["project"]["participant_height"] == 1.8
    assert cfg["project"]["participant_mass"] == 75
