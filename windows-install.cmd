@echo off
setlocal
cd /d "%~dp0"

rem GPU inference build. onnxruntime-gpu 1.27.x needs CUDA 12.x + cuDNN 9 on the
rem machine. If your CUDA differs, change this to a matching onnxruntime-gpu build.
set "ORT_GPU_VERSION=1.27.0"

where py.exe >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON=py -3"
) else (
    where python.exe >nul 2>&1
    if errorlevel 1 goto :missing_python
    set "PYTHON=python"
)

where pnpm.cmd >nul 2>&1
if errorlevel 1 (
    where pnpm.exe >nul 2>&1
    if errorlevel 1 goto :missing_pnpm
)

echo [1/5] Creating the Python environment...
%PYTHON% -m venv backend\.venv
if errorlevel 1 goto :failed

echo [2/5] Updating pip...
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :failed

echo [3/5] Installing the backend...
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 goto :failed

echo [4/5] Enabling GPU inference (onnxruntime-gpu)...
rem pose2sim pulls the CPU-only onnxruntime; swap it for the CUDA build so the
rem pose estimation runs on the NVIDIA GPU instead of the CPU.
backend\.venv\Scripts\python.exe -m pip uninstall -y onnxruntime
backend\.venv\Scripts\python.exe -m pip install "onnxruntime-gpu==%ORT_GPU_VERSION%"
if errorlevel 1 goto :failed
backend\.venv\Scripts\python.exe -c "import onnxruntime as ort; ps=ort.get_available_providers(); print('ONNX Runtime providers:', ps); print('GPU (CUDA) ENABLED' if 'CUDAExecutionProvider' in ps else 'WARNING: CUDA provider NOT available - will run on CPU. Install CUDA 12.x + cuDNN 9.')"

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
echo Python 3.11 or newer was not found. Install it for the current user and enable "Add Python to PATH".
exit /b 1

:missing_pnpm
echo pnpm was not found. Install pnpm for the current user, reopen this terminal, and run this file again.
echo https://pnpm.io/installation
exit /b 1

:failed
echo.
echo Installation failed. The error above contains the failing command.
exit /b 1
