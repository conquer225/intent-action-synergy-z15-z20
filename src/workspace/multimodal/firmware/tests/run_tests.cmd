@echo off
setlocal
if not defined VCVARS64 set "VCVARS64=D:\file\01_softwares\visual studio\VC\Auxiliary\Build\vcvars64.bat"
call "%VCVARS64%" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0"
cl /nologo /std:c++17 /EHsc /W4 test_input.cpp /Fe:test_input.exe
if errorlevel 1 exit /b 1
test_input.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /utf-8 /W3 /DPENDULUM_HEADLESS=1 /Istubs /I..\stm32\Hardware /I..\stm32\System /I..\stm32\User test_pendulum.c ..\stm32\User\RemoteControl.c ..\stm32\User\PID.c /Fe:test_pendulum.exe
if errorlevel 1 exit /b 1
test_pendulum.exe
exit /b %errorlevel%
