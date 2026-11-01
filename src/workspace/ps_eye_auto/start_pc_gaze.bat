@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\pc_gaze_preview.py %*
) else (
    python tools\pc_gaze_preview.py %*
)
if errorlevel 1 (
    echo.
    echo Startup failed. See PC_GAZE.md for setup and troubleshooting.
    pause
)
