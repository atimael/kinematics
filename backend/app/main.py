"""FastAPI app: projects, calibration, processing, SSE progress, results."""
from __future__ import annotations

import asyncio
import json
import mimetypes
import sys
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

from app import projects
from app.models import PROCESSING_STAGES, ProjectMeta, ProjectParams, ResultsSummary, SubjectSelection
from app.pipeline import outputs
from app.pipeline.config import write_config
from app.pipeline.runner import manager

# Windows can only spawn/stream subprocesses (the pipeline worker) on the asyncio
# Proactor loop; the Selector loop raises NotImplementedError, which surfaces as
# "Failed to launch worker". Force Proactor before uvicorn creates the loop —
# this module is imported before the server starts.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="Pose2Sim Kinematics", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- helpers

def _meta_or_404(project_id: str) -> ProjectMeta:
    meta = projects.load_meta(project_id)
    if not meta:
        raise HTTPException(404, "Project not found")
    return meta


def _camera_or_404(meta: ProjectMeta, camera: str) -> str:
    if camera not in meta.cameras:
        raise HTTPException(404, f"Unknown camera {camera}; expected one of {meta.cameras}")
    return camera


async def _save_upload(dest: Path, upload: UploadFile) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with dest.open("wb") as fh:
        while chunk := await upload.read(1 << 20):
            fh.write(chunk)
            size += len(chunk)
    return size


def _detect_extensions_and_rewrite(meta: ProjectMeta) -> None:
    """Match Config.toml file extensions to what was actually uploaded."""
    params = meta.params
    for cam in meta.cameras:
        d = projects.intrinsics_dir(meta.id, cam)
        files = [f for f in d.iterdir() if f.is_file()] if d.exists() else []
        if files:
            params.intrinsics_extension = files[0].suffix.lstrip(".").lower()
            break
    ed = projects.extrinsics_dir(meta.id)
    efiles = sorted(f for f in ed.glob("*") if f.is_file()) if ed.exists() else []
    if efiles:
        params.extrinsics_extension = efiles[0].suffix.lstrip(".").lower()
    vd = projects.videos_dir(meta.id)
    vfiles = sorted(f for f in vd.glob("*") if f.is_file()) if vd.exists() else []
    if vfiles:
        params.video_extension = vfiles[0].suffix.lstrip(".").lower()
    write_config(projects.project_dir(meta.id), params)
    meta.params = params
    projects.save_meta(meta)


# --------------------------------------------------------------------------- projects

@app.post("/api/projects", response_model=ProjectMeta)
def create_project(params: ProjectParams) -> ProjectMeta:
    return projects.create_project(params)


@app.get("/api/projects", response_model=list[ProjectMeta])
def list_projects() -> list[ProjectMeta]:
    return sorted(projects.list_metas(), key=lambda m: m.id)


@app.get("/api/projects/{project_id}", response_model=ProjectMeta)
def get_project(project_id: str) -> ProjectMeta:
    return _meta_or_404(project_id)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    if not projects.delete_project(project_id):
        raise HTTPException(404, "Project not found")
    return {"deleted": True}


# --------------------------------------------------------------------------- calibration uploads

@app.post("/api/projects/{project_id}/calibration/intrinsics/{camera}")
async def upload_intrinsics(project_id: str, camera: str, files: list[UploadFile] = File(...)) -> dict:
    meta = _meta_or_404(project_id)
    _camera_or_404(meta, camera)
    target = projects.intrinsics_dir(project_id, camera)
    projects.clear_uploads(target)
    saved = []
    for f in files:
        name = Path(f.filename or "frame").name
        await _save_upload(target / name, f)
        saved.append(name)
    return {"camera": camera, "saved": saved}


@app.post("/api/projects/{project_id}/calibration/extrinsics/{camera}")
async def upload_extrinsics(project_id: str, camera: str, file: UploadFile = File(...)) -> dict:
    meta = _meta_or_404(project_id)
    _camera_or_404(meta, camera)
    ext = Path(file.filename or "img.png").suffix.lstrip(".").lower() or "png"
    target = projects.extrinsics_dir(project_id)
    for stale in target.glob(f"{camera}_ext.*"):
        stale.unlink()
    await _save_upload(target / f"{camera}_ext.{ext}", file)
    return {"camera": camera, "saved": f"{camera}_ext.{ext}"}


@app.get("/api/projects/{project_id}/calibration/files")
def calibration_files(project_id: str) -> dict:
    meta = _meta_or_404(project_id)
    intr, extr = {}, {}
    for cam in meta.cameras:
        d = projects.intrinsics_dir(project_id, cam)
        intr[cam] = sorted(f.name for f in d.iterdir() if f.is_file()) if d.exists() else []
        ed = projects.extrinsics_dir(project_id)
        hits = sorted(f.name for f in ed.glob(f"{cam}_ext.*")) if ed.exists() else []
        extr[cam] = hits[0] if hits else None
    return {"intrinsics": intr, "extrinsics": extr}


@app.post("/api/projects/{project_id}/calibration/run")
async def run_calibration(project_id: str) -> dict:
    meta = _meta_or_404(project_id)
    for cam in meta.cameras:
        d = projects.intrinsics_dir(project_id, cam)
        if not d.exists() or not any(f.is_file() for f in d.iterdir()):
            raise HTTPException(400, f"Missing checkerboard footage for {cam}")
        # Extrinsics are derived from the videos during the calibration job.
    # Remove stale calibration tomls so downstream picks the fresh one.
    for old in projects.calibration_dir(project_id).glob("*.toml"):
        old.unlink()
    _detect_extensions_and_rewrite(meta)
    try:
        job = await manager.start(project_id, "calibration", ["calibration"])
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return {"job_id": job.id}


@app.post("/api/projects/{project_id}/calibration/accept")
def accept_calibration(project_id: str) -> ProjectMeta:
    meta = _meta_or_404(project_id)
    if meta.calibration.status != "done":
        raise HTTPException(400, "Calibration has not completed successfully")
    meta.calibration.status = "accepted"
    meta.status = "calibrated"
    projects.save_meta(meta)
    return meta


# --------------------------------------------------------------------------- trial videos + processing

@app.post("/api/projects/{project_id}/videos/{camera}")
async def upload_video(project_id: str, camera: str, file: UploadFile = File(...)) -> dict:
    meta = _meta_or_404(project_id)
    _camera_or_404(meta, camera)
    ext = Path(file.filename or "v.mp4").suffix.lstrip(".").lower() or "mp4"
    vd = projects.videos_dir(project_id)
    for stale in vd.glob(f"{camera}.*"):
        stale.unlink()
    await _save_upload(vd / f"{camera}.{ext}", file)
    meta.subject_selections.pop(camera, None)
    meta.job = None
    if meta.status in ("processing", "processed", "failed"):
        meta.status = "calibrated"
    projects.clear_processing_outputs(project_id)
    projects.save_meta(meta)
    return {"camera": camera, "saved": f"{camera}.{ext}"}


@app.get("/api/projects/{project_id}/videos")
def list_videos(project_id: str) -> dict:
    meta = _meta_or_404(project_id)
    vd = projects.videos_dir(project_id)
    out = {}
    for cam in meta.cameras:
        hits = sorted(f.name for f in vd.glob(f"{cam}.*")) if vd.exists() else []
        out[cam] = hits[0] if hits else None
    return out


@app.get("/api/projects/{project_id}/videos/{camera}/file")
def get_video(project_id: str, camera: str) -> FileResponse:
    meta = _meta_or_404(project_id)
    _camera_or_404(meta, camera)
    hits = sorted(p for p in projects.videos_dir(project_id).glob(f"{camera}.*") if p.is_file())
    if not hits:
        raise HTTPException(404, f"Missing trial video for {camera}")
    media_type = mimetypes.guess_type(hits[0].name)[0] or "application/octet-stream"
    return FileResponse(hits[0], media_type=media_type)


@app.put("/api/projects/{project_id}/videos/{camera}/selection", response_model=ProjectMeta)
def save_subject_selection(project_id: str, camera: str, selection: SubjectSelection) -> ProjectMeta:
    meta = _meta_or_404(project_id)
    _camera_or_404(meta, camera)
    if not list(projects.videos_dir(project_id).glob(f"{camera}.*")):
        raise HTTPException(400, f"Upload a trial video for {camera} first")
    meta.subject_selections[camera] = selection
    meta.job = None
    if meta.status in ("processing", "processed", "failed"):
        meta.status = "calibrated"
    projects.clear_processing_outputs(project_id, keep_pose=True)
    projects.save_meta(meta)
    return meta


@app.delete("/api/projects/{project_id}/videos/{camera}/selection", response_model=ProjectMeta)
def clear_subject_selection(project_id: str, camera: str) -> ProjectMeta:
    meta = _meta_or_404(project_id)
    _camera_or_404(meta, camera)
    meta.subject_selections.pop(camera, None)
    meta.job = None
    if meta.status in ("processing", "processed", "failed"):
        meta.status = "calibrated"
    projects.clear_processing_outputs(project_id, keep_pose=True)
    projects.save_meta(meta)
    return meta


def _processing_stages(meta: ProjectMeta) -> list[str]:
    stages = [s.value for s in PROCESSING_STAGES]
    if not meta.params.do_synchronization:
        stages.remove("synchronization")
    if not meta.params.do_marker_augmentation:
        stages.remove("markerAugmentation")
    return stages


@app.post("/api/projects/{project_id}/process")
async def run_processing(project_id: str) -> dict:
    meta = _meta_or_404(project_id)
    if meta.calibration.status not in ("done", "accepted"):
        raise HTTPException(400, "Run and accept calibration first")
    for cam in meta.cameras:
        if not list(projects.videos_dir(project_id).glob(f"{cam}.*")):
            raise HTTPException(400, f"Missing trial video for {cam}")
    if meta.subject_selections and set(meta.subject_selections) != set(meta.cameras):
        missing = [cam for cam in meta.cameras if cam not in meta.subject_selections]
        raise HTTPException(400, f"Select the subject in every camera; missing: {', '.join(missing)}")
    _detect_extensions_and_rewrite(meta)
    try:
        job = await manager.start(project_id, "processing", _processing_stages(meta))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return {"job_id": job.id, "stages": _processing_stages(meta)}


# --------------------------------------------------------------------------- SSE progress

@app.get("/api/projects/{project_id}/jobs/{job_id}/stream")
async def stream_job(project_id: str, job_id: str, request: Request) -> StreamingResponse:
    job = manager.get(job_id)
    if not job or job.project_id != project_id:
        raise HTTPException(404, "Job not found")
    queue = manager.subscribe(job)

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("type") == "end":
                    break
        finally:
            manager.unsubscribe(job, queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/projects/{project_id}/job")
def current_job(project_id: str) -> dict:
    meta = _meta_or_404(project_id)
    active = manager.active_for(project_id)
    return {"job": (active.to_state().model_dump() if active else (meta.job.model_dump() if meta.job else None))}


# --------------------------------------------------------------------------- results

@app.get("/api/projects/{project_id}/results", response_model=ResultsSummary)
def results_summary(project_id: str) -> ResultsSummary:
    meta = _meta_or_404(project_id)
    root = projects.project_dir(project_id)
    summary = ResultsSummary(calibration=meta.calibration)

    mot = outputs.find_angles_mot(root)
    if mot:
        df, info = outputs.parse_mot(mot)
        summary.has_angles = True
        summary.angle_columns = info["columns"]
        summary.n_frames = info["n_frames"]
        if len(df) > 1:
            summary.duration_s = round(float(df["Time"].iloc[-1] - df["Time"].iloc[0]), 3)

    trc = outputs.find_positions_trc(root)
    if trc:
        df, info = outputs.parse_trc(trc)
        summary.has_positions = True
        summary.marker_names = info["markers"]
        summary.frame_rate = info["data_rate"]
        if summary.n_frames is None:
            summary.n_frames = info["n_frames"]
    return summary


@app.get("/api/projects/{project_id}/results/gait")
def gait_analysis(project_id: str) -> dict:
    _meta_or_404(project_id)
    root = projects.project_dir(project_id)
    trc, mot = outputs.find_positions_trc(root), outputs.find_angles_mot(root)
    if not trc or not mot:
        raise HTTPException(404, "Results not ready")
    tdf, tinfo = outputs.parse_trc(trc)
    mdf, _ = outputs.parse_mot(mot)
    from app.pipeline import gait

    try:
        return gait.gait_report(tdf, mdf, tinfo["data_rate"] or 60.0)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/projects/{project_id}/results/gait.csv")
def gait_csv(project_id: str) -> Response:
    _meta_or_404(project_id)
    root = projects.project_dir(project_id)
    trc, mot = outputs.find_positions_trc(root), outputs.find_angles_mot(root)
    if not trc or not mot:
        raise HTTPException(404, "Results not ready")
    tdf, tinfo = outputs.parse_trc(trc)
    mdf, _ = outputs.parse_mot(mot)
    from app.pipeline import gait

    try:
        report = gait.gait_report(tdf, mdf, tinfo["data_rate"] or 60.0)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Section", "Metric", "Value", "Unit"])
    for section, key in (("Spatiotemporal", "spatiotemporal"), ("Joint kinematics", "kinematics")):
        for r in report[key]:
            w.writerow([section, r["label"], "" if r["value"] is None else r["value"], r["unit"]])
    return Response(
        buf.getvalue().encode(), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={project_id}_gait_summary.csv"},
    )


@app.get("/api/projects/{project_id}/results/angles/table")
def angles_table(project_id: str) -> dict:
    _meta_or_404(project_id)
    mot = outputs.find_angles_mot(projects.project_dir(project_id))
    if not mot:
        raise HTTPException(404, "No joint-angle output yet")
    df, info = outputs.parse_mot(mot)
    return {"rows": outputs.angle_summary(df), "n_frames": info["n_frames"]}


@app.get("/api/projects/{project_id}/results/angles.json")
def angles_json(project_id: str, columns: str | None = None, kind: str = "angle") -> dict:
    meta = _meta_or_404(project_id)
    mot = outputs.find_angles_mot(projects.project_dir(project_id))
    if not mot:
        raise HTTPException(404, "No joint-angle output yet")
    df, info = outputs.parse_mot(mot)
    cols = columns.split(",") if columns else info["columns"]
    if kind == "velocity":
        data = outputs.angle_velocity_series(df, cols)
        unit = "deg/s"
    else:
        data = outputs.chart_series(df, cols)
        unit = "deg" if info["in_degrees"] else "rad"
    return {
        "unit": unit,
        "kind": kind,
        "columns": info["columns"],
        "labels": outputs.angle_label_map(info["columns"]),
        **data,
    }


@app.get("/api/projects/{project_id}/results/positions.json")
def positions_json(project_id: str, markers: str | None = None, kind: str = "position") -> dict:
    meta = _meta_or_404(project_id)
    trc = outputs.find_positions_trc(projects.project_dir(project_id))
    if not trc:
        raise HTTPException(404, "No 3D position output yet")
    df, info = outputs.parse_trc(trc)
    from app.pipeline import labels as _labels

    marker_labels = {m: _labels.marker_label(m) for m in info["markers"]}
    chosen = markers.split(",") if markers else info["markers"][:1]
    if kind == "speed":
        data = outputs.marker_speed_series(df, chosen)
        return {"unit": "m/s", "kind": "speed", "markers": info["markers"], "marker_labels": marker_labels, **data}
    cols = [f"{m}_{ax}" for m in chosen for ax in ("X", "Y", "Z")]
    data = outputs.chart_series(df, cols)
    return {"unit": info["units"], "kind": "position", "markers": info["markers"], "marker_labels": marker_labels, **data}


@app.get("/api/projects/{project_id}/results/angles.csv")
def angles_csv(project_id: str) -> Response:
    _meta_or_404(project_id)
    mot = outputs.find_angles_mot(projects.project_dir(project_id))
    if not mot:
        raise HTTPException(404, "No joint-angle output yet")
    df, _ = outputs.parse_mot(mot)
    return Response(
        outputs.labeled_angles_csv(df), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={project_id}_joint_angles.csv"},
    )


@app.get("/api/projects/{project_id}/results/positions.csv")
def positions_csv(project_id: str) -> Response:
    _meta_or_404(project_id)
    trc = outputs.find_positions_trc(projects.project_dir(project_id))
    if not trc:
        raise HTTPException(404, "No 3D position output yet")
    df, _ = outputs.parse_trc(trc)
    return Response(
        outputs.labeled_positions_csv(df), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={project_id}_marker_positions.csv"},
    )


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
