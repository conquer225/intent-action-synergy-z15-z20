@echo off
setlocal
cd /d "%~dp0"
if not exist "build\reconstruction-venv\Scripts\python.exe" (
  echo Missing PC environment. See PSEUDO_LIDAR.md.
  exit /b 1
)
if not exist "build\reconstruction\models\yolo26m-depth.pt" (
  echo Missing official yolo26m-depth.pt. See PSEUDO_LIDAR.md.
  exit /b 1
)
"build\reconstruction-venv\Scripts\python.exe" -m z20_compute.pseudo_lidar --backend yolo26 --model "build\reconstruction\models\yolo26m-depth.pt" --npy "build\navigator\scene-bgr.npy" --output "artifacts\yolo26-preview"
exit /b %errorlevel%
