@echo off
pushd "%~dp0"
python -m z20_compute.fixed_photo_demo
set "demo_exit=%errorlevel%"
if not "%demo_exit%"=="0" pause
popd
exit /b %demo_exit%
