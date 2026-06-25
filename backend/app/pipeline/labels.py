"""Human-readable labels for OpenSim coordinate names and TRC marker names."""
from __future__ import annotations

import re

_SIDE = {"r": "Right", "l": "Left"}

# Explicit labels for the biomechanically meaningful coordinates.
_BASE: dict[str, str] = {
    "pelvis_tilt": "Pelvis tilt (forward/back)",
    "pelvis_list": "Pelvis obliquity (side tilt)",
    "pelvis_rotation": "Pelvis rotation",
    "pelvis_tx": "Pelvis position — forward",
    "pelvis_ty": "Pelvis position — up",
    "pelvis_tz": "Pelvis position — sideways",
    "neck_flexion": "Neck flexion",
    "neck_bending": "Neck lateral bending",
    "neck_rotation": "Neck rotation",
    "Abs_r1": "Trunk rotation 1",
    "Abs_r2": "Trunk rotation 2",
    "Abs_r3": "Trunk rotation 3",
    "Abs_t1": "Trunk shift 1",
    "Abs_t2": "Trunk shift 2",
}

_PER_SIDE = {
    "hip_flexion_{s}": "{S} hip flexion",
    "hip_adduction_{s}": "{S} hip adduction",
    "hip_rotation_{s}": "{S} hip rotation (internal)",
    "knee_angle_{s}": "{S} knee flexion",
    "knee_angle_{s}_beta": "{S} knee (coupling)",
    "ankle_angle_{s}": "{S} ankle dorsiflexion",
    "subtalar_angle_{s}": "{S} subtalar (inversion)",
    "mtp_angle_{s}": "{S} toe flexion (MTP)",
    "arm_flex_{s}": "{S} shoulder flexion",
    "arm_add_{s}": "{S} shoulder adduction",
    "arm_rot_{s}": "{S} shoulder rotation",
    "elbow_flex_{s}": "{S} elbow flexion",
    "pro_sup_{s}": "{S} forearm pronation",
    "wrist_flex_{s}": "{S} wrist flexion",
    "wrist_dev_{s}": "{S} wrist deviation",
}
for _tpl, _lbl in _PER_SIDE.items():
    for _s, _S in _SIDE.items():
        _BASE[_tpl.format(s=_s)] = _lbl.format(S=_S)

_SPINE_MOTION = {
    "Flex_Ext": "flexion/extension",
    "Lat_Bending": "lateral bending",
    "axial_rotation": "axial rotation",
}
_METERS = {"pelvis_tx", "pelvis_ty", "pelvis_tz", "Abs_t1", "Abs_t2"}


def angle_label(key: str) -> str:
    if key in _BASE:
        return _BASE[key]
    m = re.match(r"^(L\d+)_(S\d+|L\d+|T\d+)_(.+)$", key)  # spine, e.g. L5_S1_Flex_Ext
    if m:
        return f"Spine {m.group(1)}–{m.group(2)} {_SPINE_MOTION.get(m.group(3), m.group(3))}"
    return key.replace("_", " ").strip().capitalize()


def angle_unit(key: str) -> str:
    return "m" if key in _METERS else "°"


def marker_label(name: str) -> str:
    raw = name.replace("_study", "")
    side = ""
    m = re.match(r"^([rRlL])[._]?(.+)$", raw)
    if raw[:1] in "RL" and len(raw) > 1 and raw[1:2].isupper():  # RHip, LKnee
        side, raw = _SIDE[raw[0].lower()] + " ", raw[1:]
    elif m and m.group(1).lower() in _SIDE and (raw[1:2] in "._" or raw[:2].lower() in ("r_", "l_")):
        side, raw = _SIDE[m.group(1).lower()] + " ", m.group(2)
    raw = re.sub(r"(?<!^)(?=[A-Z])", " ", raw)  # split camelCase
    raw = raw.replace("_", " ").replace(".", " ").strip()
    label = (side + raw).strip()
    return label[:1].upper() + label[1:] if label else name
