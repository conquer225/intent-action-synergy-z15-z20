param([string]$Gcc='C:/mingw64/mingw64/bin/gcc.exe')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    & $Gcc -std=c11 -O2 -Wall -Wextra -Werror -Itests/include -Isrc/app src/app/eye_tracker.c src/app/hdmi_overlay.c tests/test_eye_tracker.c -o tests/test_eye_tracker.exe
    if ($LASTEXITCODE -ne 0) { throw 'Gaze test compilation failed' }
    & ./tests/test_eye_tracker.exe
    if ($LASTEXITCODE -ne 0) { throw "Gaze boundary tests failed: $LASTEXITCODE" }
    & $Gcc -std=c11 -O2 -Wall -Wextra -Werror -Itests/include -Isrc/app src/app/eye_tracker.c tests/test_eye_features.c -o tests/test_eye_features.exe
    if ($LASTEXITCODE -ne 0) { throw 'Eye feature test compilation failed' }
    & ./tests/test_eye_features.exe
    if ($LASTEXITCODE -ne 0) { throw 'Eye feature regression failed' }
    & $Gcc -std=c11 -O2 -Wall -Wextra -Werror -Itests/include -Isrc/app src/app/haar.c src/app/auto_face.c tests/test_localization.c -lm -o tests/test_localization.exe
    if ($LASTEXITCODE -ne 0) { throw 'Localization test compilation failed' }
    & ./tests/test_localization.exe
    if ($LASTEXITCODE -ne 0) { throw "Localization boundary tests failed: $LASTEXITCODE" }
    & $Gcc -std=c11 -O2 -Wall -Wextra -Werror -shared -Itests/include src/app/haar.c src/app/auto_face.c -lm -o tests/localize.dll
    if ($LASTEXITCODE -ne 0) { throw 'Replay library compilation failed' }
    & $Gcc -std=c11 -O2 -Wall -Wextra -Werror -Itests/video_mock -Itests/include -Isrc/app tests/test_video_io.c -o tests/test_video_io.exe
    if ($LASTEXITCODE -ne 0) { throw 'Video ownership test compilation failed' }
    & ./tests/test_video_io.exe
    if ($LASTEXITCODE -ne 0) { throw "Video ownership tests failed: $LASTEXITCODE" }
    foreach($name in @('test_video_live','test_live_osd')) {
        & $Gcc -std=c11 -O2 -Wall -Wextra -Werror -Itests/video_mock -Itests/include -Isrc/app "tests/$name.c" -o "tests/$name.exe"
        if($LASTEXITCODE -ne 0){throw "Compilation failed: $name"}
        & "./tests/$name.exe"
        if($LASTEXITCODE -ne 0){throw "Regression failed: $name"}
    }
    Write-Output 'PASS gaze state boundaries, uniform/noise rejection, ROI bounds, video ownership and display-only OSD'
    & $Gcc -std=c11 -O2 -Wall -Wextra -Werror -Itests/include -Ilinux linux/dma_shutdown.c tests/test_dma_shutdown.c -o tests/test_dma_shutdown.exe
    if ($LASTEXITCODE -ne 0) {throw 'Linux DMA shutdown compilation failed'}
    & ./tests/test_dma_shutdown.exe
    if ($LASTEXITCODE -ne 0) {throw 'Linux DMA shutdown regression failed'}
    & $Gcc -std=c11 -O2 -Wall -Wextra -Werror -Itests/include -Isrc/app src/app/haar.c src/app/auto_face.c src/app/eye_tracker.c src/app/net_protocol.c src/app/net_control.c tests/test_net_probe.c -lm -o tests/test_net_probe.exe
    if ($LASTEXITCODE -ne 0) {throw 'PC recovery probe compilation failed'}
    & ./tests/test_net_probe.exe
    if ($LASTEXITCODE -ne 0) {throw 'PC recovery probe regression failed'}
} finally { Pop-Location }
