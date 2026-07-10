# Kinematics — local markerless 3D motion capture

A local web app that turns multi-camera video into accurate 3D kinematics using
[Pose2Sim](https://github.com/perfanalytics/pose2sim) + OpenSim. Calibrate your
cameras, upload trial footage, and export joint angles and 3D marker
trajectories as CSV — all on your machine, no cloud.

```
calibration footage ──▶ camera calibration ──▶ trial footage ──▶ pose → triangulation
                                                                    → filtering → OpenSim IK
                                                          ──▶ joint angles + 3D positions (CSV)
```

## Architecture

| Part | Stack | Role |
|------|-------|------|
| `backend/` | Python · FastAPI · Pose2Sim · OpenSim · OpenCV | Wraps the pipeline, runs stages in a headless worker subprocess, streams progress over SSE, parses `.trc`/`.mot` → JSON/CSV |
| `frontend/` | React 19 · Vite · Tailwind v4 · TanStack Query · Recharts | 4-step wizard: calibration → trial videos → processing → results |

Calibration is computed directly with OpenCV (`calibrateCamera` + `solvePnP`) so
it runs fully unattended; every other stage is Pose2Sim, run with all
interactive/plot flags disabled and CPU inference (reliable on Apple Silicon).

## Prerequisites

- **Python 3.11+** (tested on 3.12, macOS arm64 — OpenSim 4.6 ships a universal2 wheel, so no conda needed)
- **Node + [pnpm](https://pnpm.io)**

## Setup

```bash
make install          # creates backend/.venv, pip-installs Pose2Sim + deps, pnpm installs the UI
```

The first processing run downloads the RTMPose models (~40 MB) to `~/.cache/rtmlib`.

## Run

```bash
make dev              # backend on :8000, UI on http://localhost:5173
```

Or in two terminals: `make backend` and `make frontend`.

### No `make`?

Install it (macOS: `xcode-select --install`; Debian/Ubuntu: `sudo apt install
make`; Fedora: `sudo dnf install make`), or run the targets by hand:

```bash
# make install
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt
cd frontend && pnpm install && cd ..

# make backend  (terminal 1)
cd backend && MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen PYTHONPATH=. \
  .venv/bin/python -m uvicorn app.main:app --reload --port 8000

# make frontend (terminal 2)
cd frontend && pnpm dev
```

## Windows installation

The repository includes Windows launchers, so `make`, administrator access, and
a separate ffmpeg installation are not required. Run them from the repo root in
PowerShell or Command Prompt.

### Prerequisites

- **Python 3.11–3.13, 64-bit** from [python.org](https://www.python.org/downloads/windows/) —
  choose the current-user install and tick *"Add python.exe to PATH"*. OpenSim
  4.6 ships `win_amd64` wheels for these versions, so no conda is needed.
- **Node** + **[pnpm](https://pnpm.io/installation)** installed for the current user.

### Setup

```powershell
.\windows-install.cmd
```

The first processing run downloads the RTMPose models (~40 MB) to
`%USERPROFILE%\.cache\rtmlib`.

### Run

From the repo root:

```powershell
.\windows-dev.cmd
```

This starts the backend in a second terminal and the frontend at
`http://localhost:5173`.

For manual startup, use two terminals.

**Backend** (`http://localhost:8000`):

```powershell
cd backend
$env:MPLBACKEND="Agg"; $env:QT_QPA_PLATFORM="offscreen"; $env:PYTHONPATH="."
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

**Frontend** (`http://localhost:5173`):

```powershell
cd frontend
pnpm dev
```

Tests: `cd backend; $env:PYTHONPATH="."; .venv\Scripts\python -m pytest -q`.

## How to record (read this — it determines accuracy)

Pose2Sim triangulates the **same motion seen from several cameras**, so accuracy
depends on the capture:

1. **Cameras** — 2 minimum, **3–4+ recommended**. Mount them rigidly (do not move
   them after calibration), spread around the capture volume, all genuinely
   seeing the subject. Start them as simultaneously as possible.
2. **Checkerboard** — a rigid printed checkerboard. Note its **inner-corner count**
   (intersections where black squares meet — e.g. a board of 7×8 squares has 6×7
   inner corners) and **square size in mm**.
3. **Intrinsics footage** (per camera, once per camera/lens): a short clip of the
   checkerboard waved slowly at many angles/distances across the frame.
4. **Extrinsics footage** (per camera, once per session): place the board flat in
   the capture volume where **all cameras can see it at the same instant**; grab
   one synchronized frame/short clip per camera. This defines the shared world
   frame.
5. **Trial footage** (per camera): one clip per camera of the movement to analyze.

## Using the app

1. **Create a session** — name, camera count, board inner-corners + square size,
   participant height & mass (measured values → accurate OpenSim scaling).
2. **Calibration** — upload each camera's intrinsics clip and extrinsics board
   frame, run calibration, review the per-camera reprojection error
   (< 0.5 px excellent, < 1 px fine), accept.
3. **Trial videos** — one clip per camera. If other people are visible, pause each
   preview on a clear frame and select the same subject in every camera before processing.
4. **Results** — joint-angle and 3D-trajectory charts; **Download CSV** for each.

## Outputs

- **Joint angles** (`*_joint_angles.csv`): `time` + one column per OpenSim
  coordinate in **degrees** (e.g. `hip_flexion_r`, `knee_angle_r`, `ankle_angle_r`).
- **3D marker positions** (`*_marker_positions.csv`): `Frame`, `Time` + `X/Y/Z`
  per marker in **meters** (Y-up).

Raw pipeline artifacts (`.trc`, `.mot`, `.c3d`, scaled `.osim`) live in each
project under `backend/data/projects/<id>/`.

## Notes

- **CPU inference** is forced on purpose: `device='auto'` selects Apple's CoreML
  provider, which miscomputes the detector and silently produces garbage
  keypoints. CPU is slower (a few minutes per clip) but correct.
- Tests: `make test-backend`.
- This project uses **only your own footage**. The Pose2Sim demo dataset is not
  bundled or required.
```
