"""Clinical gait analysis for prosthetic socket comparison.

Built for transtibial amputee gait: the defensible core is spatiotemporal
SYMMETRY (depends only on foot-contact timing, survives markerless noise);
joint kinematics are reported as 'indicative' and symmetry-relative.

Gait events are detected with the coordinate-based method (Zeni et al. 2008):
heel strike = foot-vs-pelvis most ANTERIOR along the walking axis; toe-off =
foot-vs-pelvis most POSTERIOR. The walking axis is the principal direction of
pelvis travel, so it's robust to our non-gravity-aligned world frame.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


def _marker(df: pd.DataFrame, m: str) -> Optional[np.ndarray]:
    cols = [f"{m}_{ax}" for ax in ("X", "Y", "Z")]
    if all(c in df.columns for c in cols):
        return df[cols].to_numpy(dtype=float)
    return None


def _smooth(x: np.ndarray, win: int) -> np.ndarray:
    if win < 3:
        return x
    k = np.ones(win) / win
    return np.convolve(x, k, mode="same")


def detect_events(trc: pd.DataFrame, fps: float) -> dict:
    pelvis = _marker(trc, "Hip")
    if pelvis is None:
        raise ValueError("No pelvis (Hip) marker — cannot detect gait events.")
    centred = pelvis - pelvis.mean(0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    axis = vt[0]
    if np.dot(pelvis[-1] - pelvis[0], axis) < 0:
        axis = -axis

    win = max(3, int(fps * 0.08))
    min_dist = max(1, int(fps * 0.6))  # same-foot events no closer than 0.6 s (rejects false strikes)
    events: dict = {"axis": axis.tolist()}
    for side, heel, toe in (("r", "RHeel", "RBigToe"), ("l", "LHeel", "LBigToe")):
        h, t = _marker(trc, heel), _marker(trc, toe)
        if h is None or t is None:
            events[side] = {"HS": [], "TO": []}
            continue
        hs_sig = _smooth((h - pelvis) @ axis, win)
        to_sig = _smooth((t - pelvis) @ axis, win)
        hs, _ = find_peaks(hs_sig, distance=min_dist, prominence=0.25 * np.nanstd(hs_sig))
        to, _ = find_peaks(-to_sig, distance=min_dist, prominence=0.25 * np.nanstd(to_sig))
        events[side] = {"HS": hs.tolist(), "TO": to.tolist()}
    return events


def _med(vals: list[float], lo: float = -np.inf, hi: float = np.inf) -> Optional[float]:
    vals = [v for v in vals if lo < v < hi]
    return float(np.median(vals)) if vals else None


def _cycle_times(hs: list[int], to: list[int], t: np.ndarray) -> dict:
    stances, swings, strides = [], [], []
    for i in range(len(hs) - 1):
        h0, h1 = hs[i], hs[i + 1]
        stride = float(t[h1] - t[h0])
        if not 0.5 < stride < 2.5:  # implausible stride -> skip (likely a missed/false event)
            continue
        strides.append(stride)
        between = [x for x in to if h0 < x < h1]
        if between:
            off = between[0]
            stances.append(float(t[off] - t[h0]))
            swings.append(float(t[h1] - t[off]))
    st, sw, sr = _med(stances), _med(swings), _med(strides)
    return {
        "stance_time": st,
        "swing_time": sw,
        "stride_time": sr,
        "stance_pct": (st / sr * 100) if st and sr else None,
    }


def _step_lengths(trc: pd.DataFrame, events: dict, axis: np.ndarray) -> dict:
    """Step length per side = anterior distance between heels at that side's heel strike."""
    rheel, lheel = _marker(trc, "RHeel"), _marker(trc, "LHeel")
    out = {"r": None, "l": None}
    if rheel is None or lheel is None:
        return out
    proj_r, proj_l = rheel @ axis, lheel @ axis
    for side, hs, lead, trail in (("r", events["r"]["HS"], proj_r, proj_l), ("l", events["l"]["HS"], proj_l, proj_r)):
        lengths = [abs(float(lead[k] - trail[k])) for k in hs if k < len(lead)]
        out[side] = _med(lengths, 0.1, 1.5)  # physiological step length 0.1–1.5 m
    return out


def _asym(p: Optional[float], s: Optional[float]) -> Optional[float]:
    """Signed symmetry index (%): >0 means the prosthetic value is larger."""
    if p is None or s is None or (p + s) == 0:
        return None
    return round((p - s) / (0.5 * (p + s)) * 100, 1)


def _ratio(p: Optional[float], s: Optional[float]) -> Optional[float]:
    if p is None or s is None or s == 0:
        return None
    return round(p / s, 3)


def _kinematics(mot: pd.DataFrame, events: dict, n: int) -> dict:
    """Ankle/knee metrics per side, indexed by the trc frame events."""
    out: dict = {}
    for side in ("r", "l"):
        hs = [k for k in events[side]["HS"] if k < n]
        to = [k for k in events[side]["TO"] if k < n]
        ankle = mot[f"ankle_angle_{side}"].to_numpy() if f"ankle_angle_{side}" in mot else None
        knee = mot[f"knee_angle_{side}"].to_numpy() if f"knee_angle_{side}" in mot else None
        peak_df, pf_pushoff, knee_swing, knee_ic = [], [], [], []
        for i in range(len(hs) - 1):
            h0, h1 = hs[i], hs[i + 1]
            offs = [x for x in to if h0 < x < h1]
            if not offs:
                continue
            off = offs[0]
            if ankle is not None:
                peak_df.append(float(np.nanmax(ankle[h0:off])))          # max dorsiflexion in stance
                lo = max(h0, int(off - 0.3 * (off - h0)))
                pf_pushoff.append(float(np.nanmax(ankle[lo:off + 1]) - np.nanmin(ankle[lo:off + 1])))  # PF excursion at push-off
            if knee is not None:
                knee_swing.append(float(np.nanmax(knee[off:h1])))        # peak flexion in swing
                knee_ic.append(float(knee[h0]))                          # flexion at initial contact
        out[side] = {
            "peak_ankle_dorsiflexion": round(float(np.median(peak_df)), 1) if peak_df else None,
            "ankle_pushoff_pf_range": round(float(np.median(pf_pushoff)), 1) if pf_pushoff else None,
            "peak_knee_flexion_swing": round(float(np.median(knee_swing)), 1) if knee_swing else None,
            "knee_flexion_initial_contact": round(float(np.median(knee_ic)), 1) if knee_ic else None,
        }
    return out


def gait_report(trc: pd.DataFrame, mot: pd.DataFrame, fps: float) -> dict:
    events = detect_events(trc, fps)
    axis = np.array(events["axis"])
    t = trc["Time"].to_numpy(dtype=float)

    cyc = {s: _cycle_times(sorted(events[s]["HS"]), sorted(events[s]["TO"]), t) for s in ("r", "l")}
    steplen = _step_lengths(trc, events, axis)

    # Step time (heel-strike to contralateral heel-strike) — most noise-robust.
    def _step_time(lead: list[int], trail: list[int]) -> Optional[float]:
        vals = []
        for h in sorted(lead):
            prev = [x for x in trail if x < h]
            if prev:
                vals.append(float(t[h] - t[prev[-1]]))
        return _med(vals, 0.2, 1.5)

    step_time = {
        "r": _step_time(events["r"]["HS"], events["l"]["HS"]),
        "l": _step_time(events["l"]["HS"], events["r"]["HS"]),
    }
    n_steps = len(events["r"]["HS"]) + len(events["l"]["HS"])
    duration = float(t[-1] - t[0]) if len(t) > 1 else 0.0
    cadence = round(n_steps / duration * 60, 1) if duration else None

    pelvis = _marker(trc, "Hip")
    speed = round(abs(float((pelvis[-1] - pelvis[0]) @ axis)) / duration, 3) if duration else None

    kin = _kinematics(mot, events, len(t))

    def paired(label: str, unit: str, r, l, *, robust: bool = False, ratio: bool = True, scale: float = 1.0):
        rv = round(r * scale, 2) if r is not None else None
        lv = round(l * scale, 2) if l is not None else None
        rows = [
            {"label": f"{label} — R", "unit": unit, "value": rv, "robust": robust},
            {"label": f"{label} — L", "unit": unit, "value": lv, "robust": robust},
        ]
        if ratio:
            rows.append({"label": f"{label} ratio (R/L)", "unit": "", "value": _ratio(rv, lv),
                         "derived": True, "robust": robust})
        else:
            rows.append({"label": f"{label} asymmetry", "unit": "%", "value": _asym(rv, lv),
                         "derived": True, "robust": robust})
        return rows

    spatiotemporal = [
        {"label": "Cadence", "unit": "steps/min", "value": cadence},
        {"label": "Walking speed", "unit": "m/s", "value": speed},
        {"label": "Walking speed", "unit": "km/h", "value": round(speed * 3.6, 2) if speed else None},
        *paired("Step time", "s", step_time["r"], step_time["l"], robust=True),
        *paired("Step length", "mm", steplen["r"], steplen["l"], robust=True, scale=1000),
        *paired("Stride time", "s", cyc["r"]["stride_time"], cyc["l"]["stride_time"]),
        *paired("Stance time", "s", cyc["r"]["stance_time"], cyc["l"]["stance_time"]),
        *paired("Swing time", "s", cyc["r"]["swing_time"], cyc["l"]["swing_time"]),
        *paired("Stance phase", "%", cyc["r"]["stance_pct"], cyc["l"]["stance_pct"], ratio=False),
    ]

    kinematics = []
    for label, key in [
        ("Peak ankle dorsiflexion (stance)", "peak_ankle_dorsiflexion"),
        ("Ankle plantarflexion range (push-off)", "ankle_pushoff_pf_range"),
        ("Peak knee flexion (swing)", "peak_knee_flexion_swing"),
        ("Knee flexion at initial contact", "knee_flexion_initial_contact"),
    ]:
        kinematics += paired(label, "°", kin["r"][key], kin["l"][key], ratio=False)

    return {
        "n_steps": n_steps,
        "n_strides": {"r": max(0, len(events["r"]["HS"]) - 1), "l": max(0, len(events["l"]["HS"]) - 1)},
        "duration_s": round(duration, 2),
        "cadence_steps_min": cadence,
        "walking_speed_ms": speed,
        "spatiotemporal": spatiotemporal,
        "kinematics": kinematics,
        "enough_steps": n_steps >= 4,
    }


def _r(v: Optional[float]) -> Optional[float]:
    return round(v, 3) if v is not None else None
