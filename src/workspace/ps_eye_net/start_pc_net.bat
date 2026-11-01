@echo off
cd /d "%~dp0"
set /p "BOARD_IP=Z15 wireless IPv4 (from board log): "
if "%BOARD_IP%"=="" set BOARD_IP=192.168.1.10
python tools/net_monitor.py --board "%BOARD_IP%"
if errorlevel 1 pause
