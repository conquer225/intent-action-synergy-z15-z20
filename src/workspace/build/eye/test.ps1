param([string]$Vivado='D:\vivado\Vivado\2023.1', [string[]]$Only=@())
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$out=Join-Path $root 'local/eye_sim'
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $out
try {
 $files=@('eye_features.sv','gaze_control.sv','uart.sv','sccb_master.sv','camera_capture.sv','serial_control.sv','frame_store.sv') | ForEach-Object {Join-Path $root "src/eye/$_"}
 $tests=@('tb_core','tb_uart','tb_sccb','tb_capture','tb_serial','tb_frame_store','tb_snapshot')
 if($Only.Count){$tests=$Only}
 $tbs=@($tests | ForEach-Object {Join-Path $root "sim/eye/$_.sv"})
 & "$Vivado/bin/xvlog.bat" -sv @files @tbs
 if($LASTEXITCODE -ne 0){throw 'HDL compile failed'}
 foreach($test in $tests){
  & "$Vivado/bin/xelab.bat" $test -s $test --debug typical
  if($LASTEXITCODE -ne 0){throw "Elaboration failed: $test"}
  & "$Vivado/bin/xsim.bat" $test -runall -log "$test.log"
  if($LASTEXITCODE -ne 0 -or !(Select-String -Path "$test.log" -Pattern "PASS $test" -Quiet)){throw "Simulation failed: $test"}
  Copy-Item "$test.log" (Join-Path $root "report/eye/$test.log") -Force
 }
} finally {Pop-Location}
