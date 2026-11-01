@echo off
setlocal
if not defined VCVARS64 set "VCVARS64=D:\file\01_softwares\visual studio\VC\Auxiliary\Build\vcvars64.bat"
call "%VCVARS64%" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0.."
if not exist build mkdir build
cl /nologo /EHsc /std:c++17 tests\test_stm_telemetry.cpp /Fo:build\test_stm.obj /Fe:build\test_stm.exe
if errorlevel 1 exit /b 1
build\test_stm.exe
if errorlevel 1 exit /b 1
cl /nologo tests\test_telemetry_queue.c /Fo:build\test_queue.obj /Fe:build\test_queue.exe
if errorlevel 1 exit /b 1
build\test_queue.exe
if errorlevel 1 exit /b 1
if not defined JSON_INCLUDE set "JSON_INCLUDE=%USERPROFILE%\Documents\Arduino\libraries\ArduinoJson\src"
cl /nologo /EHsc /std:c++17 /I"%JSON_INCLUDE%" tests\test_signal_telemetry.cpp /Fo:build\test_signal.obj /Fe:build\test_signal.exe
if errorlevel 1 exit /b 1
build\test_signal.exe
exit /b %errorlevel%
