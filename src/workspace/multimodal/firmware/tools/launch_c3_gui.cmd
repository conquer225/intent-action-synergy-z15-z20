@echo off
setlocal
netsh wlan connect name=NaoDun-Control ssid=NaoDun-Control
if not "%errorlevel%"=="0" (
  echo Could not request the C3 Wi-Fi connection. Check its power and the saved WLAN profile.
  pause
  exit /b 1
)
timeout /t 3 /nobreak >nul
python "%~dp0pc_gui.py" --host 192.168.4.2 --port 9000
if not "%errorlevel%"=="0" pause
