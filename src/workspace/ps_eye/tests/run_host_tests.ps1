$ErrorActionPreference = 'Stop'
$root = 'D:/fpga/z15_multimodal/ps_eye'
$exe = Join-Path $root 'tests/test_eye_tracker.exe'
& 'C:/mingw64/mingw64/bin/gcc.exe' -std=c11 -Wall -Wextra -I(Join-Path $root 'tests/include') -I(Join-Path $root 'src/app') (Join-Path $root 'src/app/eye_tracker.c') (Join-Path $root 'src/app/hdmi_overlay.c') (Join-Path $root 'tests/test_eye_tracker.c') -o $exe
if ($LASTEXITCODE -ne 0) { throw 'Host test compile failed.' }
& $exe
if ($LASTEXITCODE -ne 0) { throw "Host test failed: $LASTEXITCODE" }
