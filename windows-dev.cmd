@echo off
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
    echo The Python environment is missing. Run windows-install.cmd first.
    exit /b 1
)

where pnpm.cmd >nul 2>&1
if errorlevel 1 (
    where pnpm.exe >nul 2>&1
    if errorlevel 1 (
        echo pnpm was not found. Run windows-install.cmd after installing pnpm.
        exit /b 1
    )
)

set "MPLBACKEND=Agg"
set "QT_QPA_PLATFORM=offscreen"
set "PYTHONPATH=."

echo Starting the backend in a second window...
start "Kinematics backend" /D "%CD%\backend" "%CD%\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000

echo Starting the frontend at http://localhost:5173 ...
pushd frontend
call pnpm dev
set "RESULT=%errorlevel%"
popd
exit /b %RESULT%
