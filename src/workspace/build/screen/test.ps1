param([string]$Vivado='D:\vivado\Vivado\2023.1',[string[]]$Only=@('tb_relative','tb_screen_capture','tb_screen_control','tb_screen_serial','tb_screen_pixels'))
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$out=Join-Path $root 'local/screen_sim'
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $out
try {
 $files=@('relative_eye','screen_capture','screen_control','screen_serial','screen_pixels') | ForEach-Object {"$root/src/screen/$_.sv"}
 $files+="$root/src/eye/uart.sv"
 $tbs=@($Only | ForEach-Object {"$root/sim/screen/$_.sv"})
 & "$Vivado/bin/xvlog.bat" -sv @files @tbs
 if($LASTEXITCODE -ne 0){throw 'Compile failed'}
 foreach($test in $Only){
  & "$Vivado/bin/xelab.bat" $test -s $test --debug typical
  if($LASTEXITCODE -ne 0){throw "Elaboration failed: $test"}
  & "$Vivado/bin/xsim.bat" $test -runall -log "$test.log"
  if($LASTEXITCODE -ne 0 -or !(Select-String "$test.log" -Pattern "PASS $test" -Quiet)){throw "Simulation failed: $test"}
  Copy-Item "$test.log" "$root/report/screen/$test.log" -Force
 }
}finally{Pop-Location}
