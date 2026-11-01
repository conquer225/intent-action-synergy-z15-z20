@echo off
setlocal EnableDelayedExpansion
if not defined VCVARS64 set "VCVARS64=D:\file\01_softwares\visual studio\VC\Auxiliary\Build\vcvars64.bat"
call "%VCVARS64%" >nul
if not "!errorlevel!"=="0" exit /b 1
cd /d "%~dp0"
if not defined JSON_INCLUDE set "JSON_INCLUDE=%USERPROFILE%\Documents\Arduino\libraries\ArduinoJson\src"
set "BOOT_TEST_BUILD=%~dp0..\build\boot_tests"
if not exist "%BOOT_TEST_BUILD%" mkdir "%BOOT_TEST_BUILD%"
cl /nologo /std:c++17 /EHsc /W4 /DNOUSER /DNOMINMAX /DWIN32_LEAN_AND_MEAN /Imultistubs /I"%JSON_INCLUDE%" /FI"%~dp0multistubs/TestHandConfig.h" test_boot_runtime.cpp ..\esp32\MultiControlS3\GloveController.cpp ..\esp32\MultiControlS3\GloveRadio.cpp ..\esp32\MultiControlS3\HapticFeedback.cpp ..\esp32\MultiControlS3\PendulumLink.cpp ..\esp32\MultiControlS3\NetworkControl.cpp /Fo"%BOOT_TEST_BUILD%\\" /Fe:"%BOOT_TEST_BUILD%\test_boot_runtime.exe"
if not "!errorlevel!"=="0" exit /b 1
if not "%~1"=="" (
  "%BOOT_TEST_BUILD%\test_boot_runtime.exe" %*
  if not "!errorlevel!"=="0" exit /b 1
  exit /b 0
)
for %%s in (local cancel moving late remote hand-off pend-off missing-poses unverified usb-blocked glove-direct glove-locate glove-nano) do (
  "%BOOT_TEST_BUILD%\test_boot_runtime.exe" %%s
  if not "!errorlevel!"=="0" exit /b 1
)
exit /b 0
