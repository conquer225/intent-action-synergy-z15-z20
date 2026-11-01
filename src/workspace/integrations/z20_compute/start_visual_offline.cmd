@echo off
setlocal
cd /d "%~dp0"
set "VISUAL_DEMO_PYTHON=%~dp0build\reconstruction-venv\Scripts\python.exe"
if not exist "%VISUAL_DEMO_PYTHON%" (
  echo Prepared Python environment is missing. See VISUAL_DEMO_GUIDE.md.
  pause
  exit /b 1
)
"%VISUAL_DEMO_PYTHON%" -m z20_compute.visual_offline
if errorlevel 1 pause
