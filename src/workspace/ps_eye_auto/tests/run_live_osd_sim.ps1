param([string]$Vivado='D:/vivado/Vivado/2023.1')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$out=Join-Path (Split-Path $root -Parent) 'local/ps_live_osd_sim'
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $out
try {
    & "$Vivado/bin/xvlog.bat" -sv "$root/hardware/source/rtl/live_osd_core.sv" "$root/hardware/source/rtl/live_osd.v" "$root/tests/tb_live_osd.sv"
    if($LASTEXITCODE -ne 0){throw 'OSD compile failed'}
    & "$Vivado/bin/xelab.bat" tb_live_osd -s tb_live_osd --debug typical
    if($LASTEXITCODE -ne 0){throw 'OSD elaboration failed'}
    & "$Vivado/bin/xsim.bat" tb_live_osd -runall -log tb_live_osd.log
    if($LASTEXITCODE -ne 0 -or !(Select-String tb_live_osd.log -Pattern 'PASS tb_live_osd' -Quiet)){throw 'OSD simulation failed'}
    Copy-Item tb_live_osd.log "$root/report/tb_live_osd.log" -Force
} finally {Pop-Location}
