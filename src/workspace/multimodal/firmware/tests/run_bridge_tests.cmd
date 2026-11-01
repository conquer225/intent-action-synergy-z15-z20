@echo off
setlocal
if not defined VCVARS64 set "VCVARS64=D:\file\01_softwares\visual studio\VC\Auxiliary\Build\vcvars64.bat"
call "%VCVARS64%" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0"
cl /nologo /std:c++17 /EHsc /W4 test_bridge.cpp /Fe:test_bridge.exe
if errorlevel 1 exit /b 1
test_bridge.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /Ibridgestubs test_pendulum_link.cpp ..\esp32\MultiControlS3\PendulumLink.cpp /Fe:test_pendulum_link.exe
if errorlevel 1 exit /b 1
test_pendulum_link.exe
exit /b %errorlevel%
