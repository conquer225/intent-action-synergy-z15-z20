param([string]$Vivado='D:\vivado\Vivado\2023.1', [switch]$DeviceDisplay)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$out=Join-Path $root 'local/eye_pipeline_sim'
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $out
try {
 $files=@(Get-ChildItem "$root/src/eye" -File | Where-Object {$_.Extension -in @('.sv','.v')} | ForEach-Object {$_.FullName})
 $displayFiles=Get-ChildItem "$root/src/third_party/projectf" -Filter '*.v'
 if(!$DeviceDisplay){
  $displayFiles=$displayFiles | Where-Object {$_.Name -notin @('display_clocks.v','serializer_10to1.v')}
  $files+="$root/sim/eye/display_test_models.sv"
 }
 $files+=@($displayFiles | ForEach-Object {$_.FullName})
 & "$Vivado/bin/xvlog.bat" -sv @files "$root/sim/eye/tb_pipeline.sv" "$Vivado/data/verilog/src/glbl.v"
 if($LASTEXITCODE -ne 0){throw 'Pipeline HDL compile failed'}
 & "$Vivado/bin/xelab.bat" -L xpm -L unisims_ver -L unimacro_ver -L secureip tb_pipeline glbl -s tb_pipeline --debug typical
 if($LASTEXITCODE -ne 0){throw 'Pipeline elaboration failed'}
 & "$Vivado/bin/xsim.bat" tb_pipeline -runall -log tb_pipeline.log
 if($LASTEXITCODE -ne 0 -or !(Select-String tb_pipeline.log -Pattern 'PASS tb_pipeline' -Quiet)){throw 'Pipeline simulation failed'}
 Copy-Item tb_pipeline.log "$root/report/eye/tb_pipeline.log" -Force
}finally {Pop-Location}
