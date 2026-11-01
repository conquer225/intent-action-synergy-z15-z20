@echo off
setlocal
cd /d "%~dp0.."
python tools\screen_monitor.py
if errorlevel 1 pause
