@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\pc_preview.py %*
) else (
    python tools\pc_preview.py %*
)
if errorlevel 1 (
    echo.
    echo Startup failed. See PC_TEST.md for Python setup and model rebuild.
    pause
)
