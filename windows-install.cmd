@echo off
setlocal
cd /d "%~dp0"

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

echo [1/4] Creating the Python environment...
%PYTHON% -m venv backend\.venv
if errorlevel 1 goto :failed

echo [2/4] Updating pip...
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :failed

echo [3/4] Installing the backend...
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 goto :failed

echo [4/4] Installing the frontend...
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
