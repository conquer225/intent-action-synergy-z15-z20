@echo off
setlocal
if not defined VCVARS64 set "VCVARS64=D:\file\01_softwares\visual studio\VC\Auxiliary\Build\vcvars64.bat"
call "%VCVARS64%" >nul
if not "%errorlevel%"=="0" exit /b 1
cd /d "%~dp0"
cl /nologo /std:c++17 /EHsc /W4 /Ic3stubs /FI"%~dp0c3stubs/TestWifiConfig.h" test_c3_runtime.cpp /Fe:test_c3_runtime.exe
if not "%errorlevel%"=="0" exit /b 1
test_c3_runtime.exe
if not "%errorlevel%"=="0" exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /DTEST_C3_EMPTY_PASSWORD /Ic3stubs /FI"%~dp0c3stubs/TestWifiConfig.h" test_c3_runtime.cpp /Fe:test_c3_no_credentials.exe
if not "%errorlevel%"=="0" exit /b 1
test_c3_no_credentials.exe
exit /b %errorlevel%
