@echo off
setlocal
cd /d "%~dp0"

rem GPU inference build. onnxruntime-gpu 1.27.x needs CUDA 13.x + cuDNN 9; the
rem [cuda,cudnn] extra below pulls them as pip packages, so no separate CUDA
rem Toolkit install is needed (just an NVIDIA driver new enough for CUDA 13).
set "ORT_GPU_VERSION=1.27.0"
set "VENV_PY=backend\.venv\Scripts\python.exe"

rem Pick a Python launcher: prefer the py launcher, else python on PATH.
set "PYTHON="
where py.exe >nul 2>&1 && set "PYTHON=py -3"
if not defined PYTHON (
    where python.exe >nul 2>&1 && set "PYTHON=python"
)
if not defined PYTHON goto :missing_python

where pnpm.cmd >nul 2>&1 || where pnpm.exe >nul 2>&1 || goto :missing_pnpm

echo [1/5] Creating the Python environment...
rem Recreate only a broken venv (missing python.exe); reuse a good one so re-runs are fast.
if exist "backend\.venv" if not exist "%VENV_PY%" rmdir /s /q "backend\.venv"
if not exist "%VENV_PY%" %PYTHON% -m venv backend\.venv
if not exist "%VENV_PY%" goto :venv_broken

echo [2/5] Updating pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto :failed

echo [3/5] Installing the backend...
"%VENV_PY%" -m pip install -r backend\requirements.txt
if errorlevel 1 goto :failed

echo [4/5] Enabling GPU inference (onnxruntime-gpu + CUDA/cuDNN pip packages)...
rem pose2sim pulls the CPU-only onnxruntime; swap it for the CUDA build and pull
rem the matching CUDA 13.x + cuDNN 9 runtime as pip packages ([cuda,cudnn]).
"%VENV_PY%" -m pip uninstall -y onnxruntime
"%VENV_PY%" -m pip install "onnxruntime-gpu[cuda,cudnn]==%ORT_GPU_VERSION%"
if errorlevel 1 goto :failed
"%VENV_PY%" -c "import sys; sys.path.insert(0,'backend'); from app.pipeline.config import require_cuda; require_cuda(); print('GPU (CUDA) ENABLED')" || echo WARNING: GPU is not ready yet - see the message above. Pose estimation will refuse to run until CUDA works.

echo [5/5] Installing the frontend...
pushd frontend
call pnpm install
set "RESULT=%errorlevel%"
popd
if not "%RESULT%"=="0" goto :failed

echo.
echo Installation complete. Run windows-dev.cmd to start the app.
exit /b 0

:missing_python
echo Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH", then open a NEW terminal and run this file again.
exit /b 1

:venv_broken
echo.
echo The virtual environment was not created ("%VENV_PY%" is missing).
echo This almost always means Windows is using the Microsoft Store STUB of Python,
echo or the "py" launcher has no real Python 3.x installed.
echo.
echo Fix:
echo   1. Install real Python 3.12 from https://www.python.org/downloads/ (tick "Add to PATH").
echo   2. Turn OFF Settings ^> Apps ^> Advanced app settings ^> App execution aliases
echo      for "python.exe" and "python3.exe".
echo   3. Open a NEW terminal and run this file again.
exit /b 1

:missing_pnpm
echo pnpm was not found. Install pnpm (https://pnpm.io/installation), reopen this terminal, and run this file again.
exit /b 1

:failed
echo.
echo Installation failed. The error above contains the failing command.
exit /b 1
