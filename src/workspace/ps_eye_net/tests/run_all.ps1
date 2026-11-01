param([string]$Python='python')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    & $Python tools/build_pc_runtime.py
    if($LASTEXITCODE -ne 0){throw 'PC build failed'}
    & $Python tools/build_host_core.py
    if($LASTEXITCODE -ne 0){throw 'Host core build failed'}
    & $PSScriptRoot/run_host_tests.ps1 *> report/host_tests.txt
    & $Python tests/test_network.py *> report/network_tests.txt
    if($LASTEXITCODE -ne 0){Get-Content report/network_tests.txt;throw 'UDP/controller regression failed'}
    & $PSScriptRoot/run_live_osd_sim.ps1 *> report/rtl_tests.txt
    & $Python tools/inspect_boot_reference.py
    if($LASTEXITCODE -ne 0){throw 'Boot reference verification failed'}
    & $Python tools/verify_release.py
    if($LASTEXITCODE -ne 0){throw 'Release verification failed'}
    Write-Output 'PASS host C, real UDP loopback, controller, JPEG, shutdown, RTL and release identity; no board claim'
} finally {Pop-Location}
