@echo off
setlocal
if not defined VCVARS64 set "VCVARS64=D:\file\01_softwares\visual studio\VC\Auxiliary\Build\vcvars64.bat"
call "%VCVARS64%" >nul
if not "%errorlevel%"=="0" exit /b 1
cd /d "%~dp0"
if not defined JSON_INCLUDE set "JSON_INCLUDE=%USERPROFILE%\Documents\Arduino\libraries\ArduinoJson\src"
set "MPU_TEST_BUILD=%~dp0..\build\mpu_vertical_tests"
if not exist "%MPU_TEST_BUILD%" mkdir "%MPU_TEST_BUILD%"
cl /nologo /std:c++17 /EHsc /W4 test_motion.cpp /Fo"%MPU_TEST_BUILD%\test_motion.obj" /Fe:"%MPU_TEST_BUILD%\test_motion.exe"
if not "%errorlevel%"=="0" exit /b 1
"%MPU_TEST_BUILD%\test_motion.exe"
if not "%errorlevel%"=="0" exit /b 1
cl /nologo /std:c++17 /EHsc /W4 test_swipe.cpp /Fo"%MPU_TEST_BUILD%\test_swipe.obj" /Fe:"%MPU_TEST_BUILD%\test_swipe.exe"
if not "%errorlevel%"=="0" exit /b 1
"%MPU_TEST_BUILD%\test_swipe.exe"
if not "%errorlevel%"=="0" exit /b 1
cl /nologo /std:c++17 /EHsc /W4 test_tilt_test.cpp /Fo"%MPU_TEST_BUILD%\test_tilt_test.obj" /Fe:"%MPU_TEST_BUILD%\test_tilt_test.exe"
if not "%errorlevel%"=="0" exit /b 1
"%MPU_TEST_BUILD%\test_tilt_test.exe"
if not "%errorlevel%"=="0" exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /DNOUSER /DNOMINMAX /DWIN32_LEAN_AND_MEAN /Imultistubs /I"%JSON_INCLUDE%" /FI"%~dp0multistubs/TestHandConfig.h" test_mpu_vertical_runtime.cpp ..\esp32\MultiControlS3\GloveController.cpp ..\esp32\MultiControlS3\GloveRadio.cpp ..\esp32\MultiControlS3\HapticFeedback.cpp ..\esp32\MultiControlS3\PendulumLink.cpp ..\esp32\MultiControlS3\NetworkControl.cpp /Fo"%MPU_TEST_BUILD%\\" /Fe:"%MPU_TEST_BUILD%\test_mpu_vertical_runtime.exe"
if not "%errorlevel%"=="0" exit /b 1
"%MPU_TEST_BUILD%\test_mpu_vertical_runtime.exe"
if not "%errorlevel%"=="0" exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /DNOUSER /DNOMINMAX /DWIN32_LEAN_AND_MEAN /Imultistubs /I"%JSON_INCLUDE%" /FI"%~dp0multistubs/TestHandConfig.h" test_multicontrol_runtime.cpp ..\esp32\MultiControlS3\GloveController.cpp ..\esp32\MultiControlS3\GloveRadio.cpp ..\esp32\MultiControlS3\HapticFeedback.cpp ..\esp32\MultiControlS3\PendulumLink.cpp ..\esp32\MultiControlS3\NetworkControl.cpp /Fo"%MPU_TEST_BUILD%\\" /Fe:"%MPU_TEST_BUILD%\test_multicontrol_runtime.exe"
if not "%errorlevel%"=="0" exit /b 1
"%MPU_TEST_BUILD%\test_multicontrol_runtime.exe"
exit /b %errorlevel%
