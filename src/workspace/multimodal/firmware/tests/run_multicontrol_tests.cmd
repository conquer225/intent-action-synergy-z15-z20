@echo off
setlocal
if not defined VCVARS64 set "VCVARS64=D:\file\01_softwares\visual studio\VC\Auxiliary\Build\vcvars64.bat"
call "%VCVARS64%" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0"
if not defined JSON_INCLUDE set "JSON_INCLUDE=%USERPROFILE%\Documents\Arduino\libraries\ArduinoJson\src"
cl /nologo /std:c++17 /EHsc /W4 test_multicontrol.cpp /Fe:test_multicontrol.exe
if errorlevel 1 exit /b 1
test_multicontrol.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 test_swipe.cpp /Fe:test_swipe.exe
if errorlevel 1 exit /b 1
test_swipe.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 test_hand_feedback.cpp /Fe:test_hand_feedback.exe
if errorlevel 1 exit /b 1
test_hand_feedback.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /Inanostubs test_nano_runtime.cpp /Fe:test_nano_unverified.exe
if errorlevel 1 exit /b 1
test_nano_unverified.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /Inanostubs /FI"%~dp0multistubs/TestHandConfig.h" test_nano_runtime.cpp /Fe:test_nano_runtime.exe
if errorlevel 1 exit /b 1
test_nano_runtime.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /I"%JSON_INCLUDE%" test_network.cpp /Fe:test_network.exe
if errorlevel 1 exit /b 1
test_network.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /DNOUSER /DNOMINMAX /DWIN32_LEAN_AND_MEAN /Imultistubs /I"%JSON_INCLUDE%" /FI"%~dp0multistubs/TestHandConfig.h" test_multicontrol_runtime.cpp ..\esp32\MultiControlS3\GloveController.cpp ..\esp32\MultiControlS3\GloveRadio.cpp ..\esp32\MultiControlS3\HapticFeedback.cpp ..\esp32\MultiControlS3\PendulumLink.cpp ..\esp32\MultiControlS3\NetworkControl.cpp /Fe:test_multicontrol_runtime.exe
if errorlevel 1 exit /b 1
test_multicontrol_runtime.exe
exit /b %errorlevel%
