"""Parse Pose2Sim/OpenSim outputs (.trc 3D markers, .mot joint angles).

Both are tab-separated with bespoke headers. We parse them into tidy pandas
frames, then expose CSV bytes (download) and downsampled JSON (charts).
"""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from app.pipeline import labels


# ----------------------------------------------------------------------------- TRC

def parse_trc(path: Path) -> tuple[pd.DataFrame, dict]:
    text = Path(path).read_text()
    lines = text.splitlines()

    meta_keys = lines[1].split("\t")
    meta_vals = lines[2].split("\t")
    meta = dict(zip(meta_keys, meta_vals))

    header = lines[3].split("\t")
    markers = [h.strip() for h in header[2:] if h.strip()]

    columns = ["Frame", "Time"]
    for m in markers:
        columns += [f"{m}_X", f"{m}_Y", f"{m}_Z"]

    # Data starts at the first line whose first token is an integer frame index.
    start = next(
        i
        for i in range(4, len(lines))
        if lines[i].split("\t")[0].strip().lstrip("-").isdigit()
    )

    df = pd.read_csv(
        io.StringIO("\n".join(lines[start:])),
        sep="\t",
        header=None,
        usecols=range(len(columns)),
        names=columns,
    )
    info = {
        "data_rate": _to_float(meta.get("DataRate")),
        "n_frames": _to_int(meta.get("NumFrames")),
        "n_markers": _to_int(meta.get("NumMarkers")),
        "units": meta.get("Units"),
        "markers": markers,
    }
    return df, info


# ----------------------------------------------------------------------------- MOT

def parse_mot(path: Path) -> tuple[pd.DataFrame, dict]:
    text = Path(path).read_text()
    lines = text.splitlines()

    in_degrees = True
    header_idx = None
    for i, line in enumerate(lines):
        low = line.strip().lower()
        if low.startswith("indegrees"):
            in_degrees = low.endswith("yes")
        if low == "endheader":
            header_idx = i + 1
            break
    if header_idx is None:
        raise ValueError(f"No 'endheader' found in {path}")

    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])), sep="\t")
    df = df.rename(columns={df.columns[0]: "Time"})
    info = {
        "in_degrees": in_degrees,
        "columns": [c for c in df.columns if c != "Time"],
        "n_frames": len(df),
    }
    return df, info


# ----------------------------------------------------------------------------- helpers

def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode()


def angle_summary(df: pd.DataFrame) -> list[dict]:
    """Per-joint summary stats with human-readable labels (the results table)."""
    t = df["Time"].to_numpy()
    out = []
    for c in df.columns:
        if c == "Time":
            continue
        s = df[c].astype(float)
        vel = np.gradient(s.to_numpy(), t)
        out.append({
            "key": c,
            "label": labels.angle_label(c),
            "unit": labels.angle_unit(c),
            "min": round(float(s.min()), 2),
            "max": round(float(s.max()), 2),
            "mean": round(float(s.mean()), 2),
            "range": round(float(s.max() - s.min()), 2),
            # 95th percentile, not max: a few glitchy frames spike the raw
            # derivative to non-physical values; this is the robust peak speed.
            "peak_vel": round(float(np.nanpercentile(np.abs(vel), 95)), 1),  # unit per second
        })
    return out


def angle_velocity_series(df: pd.DataFrame, columns: list[str], max_points: int = 600) -> dict:
    t = df["Time"].to_numpy()
    vdf = pd.DataFrame({"Time": df["Time"]})
    for c in columns:
        if c in df.columns:
            vdf[c] = np.gradient(df[c].astype(float).to_numpy(), t)
    return chart_series(vdf, columns, max_points)


def marker_speed_series(df: pd.DataFrame, markers: list[str], max_points: int = 600) -> dict:
    """Linear speed magnitude (m/s) per marker = |d(x,y,z)/dt|."""
    t = df["Time"].to_numpy()
    sdf = pd.DataFrame({"Time": df["Time"]})
    for m in markers:
        axes = [f"{m}_{ax}" for ax in ("X", "Y", "Z")]
        if all(a in df.columns for a in axes):
            comps = [np.gradient(df[a].astype(float).to_numpy(), t) for a in axes]
            sdf[m] = np.sqrt(sum(c ** 2 for c in comps))
    return chart_series(sdf, markers, max_points)


def angle_label_map(columns: list[str]) -> dict[str, dict]:
    return {c: {"label": labels.angle_label(c), "unit": labels.angle_unit(c)} for c in columns}


def labeled_angles_csv(df: pd.DataFrame) -> bytes:
    rename = {"Time": "Time (s)"}
    for c in df.columns:
        if c != "Time":
            rename[c] = f"{labels.angle_label(c)} ({labels.angle_unit(c)})"
    return df.rename(columns=rename).to_csv(index=False).encode()


def labeled_positions_csv(df: pd.DataFrame) -> bytes:
    rename = {"Frame": "Frame", "Time": "Time (s)"}
    for c in df.columns:
        if c.endswith(("_X", "_Y", "_Z")):
            base, ax = c.rsplit("_", 1)
            rename[c] = f"{labels.marker_label(base)} — {ax} (m)"
    return df.rename(columns=rename).to_csv(index=False).encode()


def _downsample(df: pd.DataFrame, max_points: int) -> pd.DataFrame:
    if len(df) <= max_points:
        return df
    step = math.ceil(len(df) / max_points)
    return df.iloc[::step].reset_index(drop=True)


def _json_safe(values) -> list:
    out = []
    for v in values:
        f = float(v)
        out.append(None if (math.isnan(f) or math.isinf(f)) else round(f, 6))
    return out


def chart_series(df: pd.DataFrame, columns: list[str], max_points: int = 600) -> dict:
    """Return {time: [...], series: {col: [...]}} downsampled for plotting."""
    d = _downsample(df, max_points)
    time = d["Time"] if "Time" in d.columns else d.index.to_series()
    series = {c: _json_safe(d[c]) for c in columns if c in d.columns}
    return {"time": _json_safe(time), "series": series}


# ----------------------------------------------------------------------------- file discovery

def find_positions_trc(project_dir: Path) -> Optional[Path]:
    pose3d = project_dir / "pose-3d"
    if not pose3d.is_dir():
        return None
    for suffix in ("*_LSTM.trc", "*_filt.trc", "*.trc"):
        files = sorted(pose3d.glob(suffix), key=lambda p: p.stat().st_mtime, reverse=True)
        files = [f for f in files if not f.name.endswith("_LSTM.trc")] if suffix == "*.trc" else files
        if files:
            return files[0]
    return None


def find_angles_mot(project_dir: Path) -> Optional[Path]:
    kin = project_dir / "kinematics"
    if not kin.is_dir():
        return None
    files = sorted(kin.glob("*.mot"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None
