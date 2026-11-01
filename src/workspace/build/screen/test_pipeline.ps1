param([string]$Vivado='D:\vivado\Vivado\2023.1')
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$out=Join-Path $root 'local/screen_pipeline_sim'
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $out
try {
 $files=@(Get-ChildItem "$root/src/screen" -File | Where-Object {$_.Extension -in @('.sv','.v')} | ForEach-Object {$_.FullName})
 $files+=@('reset_sync.sv','sccb_master.sv','camera_init.sv','uart.sv','frame_store.sv','visual_mailbox.sv') | ForEach-Object {"$root/src/eye/$_"}
 $files+=@(Get-ChildItem "$root/src/third_party/projectf" -Filter '*.v' | Where-Object {$_.Name -notin @('display_clocks.v','serializer_10to1.v')} | ForEach-Object {$_.FullName})
 $files+="$root/sim/eye/display_test_models.sv"
 & "$Vivado/bin/xvlog.bat" -sv @files "$root/sim/screen/tb_screen_pipeline.sv" "$Vivado/data/verilog/src/glbl.v"
 if($LASTEXITCODE -ne 0){throw 'Pipeline compile failed'}
 & "$Vivado/bin/xelab.bat" -L xpm -L unisims_ver -L unimacro_ver -L secureip tb_screen_pipeline glbl -s tb_screen_pipeline --debug typical
 if($LASTEXITCODE -ne 0){throw 'Pipeline elaboration failed'}
 & "$Vivado/bin/xsim.bat" tb_screen_pipeline -runall -log tb_screen_pipeline.log
 if($LASTEXITCODE -ne 0 -or !(Select-String tb_screen_pipeline.log -Pattern 'PASS tb_screen_pipeline' -Quiet)){throw 'Pipeline test failed'}
 Copy-Item tb_screen_pipeline.log "$root/report/screen/tb_screen_pipeline.log" -Force
}finally{Pop-Location}
