param([Parameter(Mandatory=$true)][string]$EvidenceDirectory,
      [switch]$CompileVendorSource,
      [switch]$ArbiterNonblockingDiagnostic,
      [switch]$ArbiterDeferredRequestDiagnostic,
      [switch]$DdrConsumerTimingDiagnostic)
$ErrorActionPreference='Stop'
$tool='D:/ruanjian/2025.2/Vivado/bin'
$vendor='D:/ruanjian/2025.2/Vivado/data/ip/xilinx/processing_system7_vip_v1_0/hdl'
$wrapper='D:/ican/codex_project/eeg_apps_z15/output/pl_pipeline_build_v2025_2_20260927/project/pl_filter_candidate_dma.gen/sources_1/bd/filter_candidate/ip/filter_candidate_processing_system7_0_0/sim/filter_candidate_processing_system7_0_0.v'
$bench=Join-Path $PSScriptRoot 'hp0_ddr_probe_tb.sv'
if(Test-Path -LiteralPath $EvidenceDirectory){throw 'Preserve prior probe evidence: select a new directory'}
if(($ArbiterNonblockingDiagnostic -or $ArbiterDeferredRequestDiagnostic -or $DdrConsumerTimingDiagnostic) -and !$CompileVendorSource){throw 'Timing diagnostic requires local source compilation'}
if(@($ArbiterNonblockingDiagnostic,$ArbiterDeferredRequestDiagnostic,$DdrConsumerTimingDiagnostic).Where({$_}).Count -gt 1){throw 'Run one timing diagnostic at a time'}
New-Item -ItemType Directory -Path $EvidenceDirectory | Out-Null
Copy-Item -LiteralPath 'D:/ican/codex_project/eeg_apps_z15/output/pl_full_chain_cosim_v2025_2_20260928/export/xsim/xsim.ini' -Destination $EvidenceDirectory
$vendorFile=Join-Path $vendor 'processing_system7_vip_v1_0_vl_rfs.sv'
if($ArbiterNonblockingDiagnostic -or $ArbiterDeferredRequestDiagnostic -or $DdrConsumerTimingDiagnostic){
 $actual=(Get-FileHash -LiteralPath $vendorFile -Algorithm SHA256).Hash
 $expected='A8EA5002290E272EB93E3D78AF20FA381CC4D1D1DE3D1967BDB7AFBA851B9305'
 if($actual -ne $expected){throw "Unexpected vendor source hash: $actual"}
 $original=[System.IO.File]::ReadAllText($vendorFile)
 $moduleName=if($ArbiterNonblockingDiagnostic -or $ArbiterDeferredRequestDiagnostic){'processing_system7_vip_v1_0_24_arb_wr_4'}else{'processing_system7_vip_v1_0_24_ddrc'}
 $start=$original.IndexOf("module $moduleName(")
 $end=$original.IndexOf('endmodule',$start)+9
 if($start -lt 0 -or $end -lt 9){throw 'Vendor arbiter module not found'}
 $module=$original.Substring($start,$end-$start)
 if($ArbiterNonblockingDiagnostic){
  $patched=[regex]::Replace($module,'\bprt_req\s*=\s*','prt_req <= ')
  if($patched -eq $module -or ([regex]::Matches($module,'\bprt_req\s*=\s*')).Count -ne 22){throw 'Unexpected vendor arbiter assignment layout'}
  $change='22 prt_req blocking assignments to nonblocking'
 } elseif($ArbiterDeferredRequestDiagnostic){
  $needle='\bprt_req\s*=\s*1\s*;'
  if(([regex]::Matches($module,$needle)).Count -ne 16){throw 'Unexpected request assertion layout'}
  $patched=[regex]::Replace($module,$needle,'#0 prt_req = 1;')
  $change='defer 16 request assertions one delta cycle; no changes to request deassertion'
 } else {
  $needle='(?m)^([ \t]*)if\(wr_req\) begin'
  if(([regex]::Matches($module,$needle)).Count -ne 1){throw 'Unexpected DDR consumer layout'}
  $patched=[regex]::Replace($module,$needle,{param($match) "$($match.Groups[1].Value)#1; // diagnostic only: sample settled arbitration payload`r`n$($match.Value)"})
  $change='one 1 ns delayed request sample in DDR consumer'
 }
 $localSource=Join-Path $EvidenceDirectory 'ps7_vip_timing_diagnostic.sv'
 [System.IO.File]::WriteAllText($localSource,$original.Substring(0,$start)+$patched+$original.Substring($end),[System.Text.UTF8Encoding]::new($false))
 $vendorFile=$localSource
 @("original_sha256=$actual","diagnostic_sha256=$((Get-FileHash -LiteralPath $localSource -Algorithm SHA256).Hash)","isolated_module=$moduleName","change=$change; vendor installation untouched") | Set-Content -LiteralPath (Join-Path $EvidenceDirectory 'diagnostic_change.txt')
}
function Invoke-Checked([string]$exe,[string[]]$toolArgs){
 & $exe @toolArgs | Out-Null
 if($LASTEXITCODE -ne 0){throw "$exe failed: $LASTEXITCODE; inspect logs"}
}
Push-Location -LiteralPath $EvidenceDirectory
try {
 if($CompileVendorSource){
  Invoke-Checked (Join-Path $tool 'xvlog.bat') @('--sv','--work','xil_defaultlib','-L','xilinx_vip','-d','XILINX_SIMULATOR','-i',$vendor,'-i','D:/ruanjian/2025.2/Vivado/data/xilinx_vip/include',$vendorFile,'-log','compile_vendor.log')
 }
 Invoke-Checked (Join-Path $tool 'xvlog.bat') @('--sv','--work','xil_defaultlib','-L','xilinx_vip',$wrapper,$bench,'-log','compile_probe.log')
 Invoke-Checked (Join-Path $tool 'xelab.bat') @('--debug','typical','--relax','--mt','2','-L','xil_defaultlib','-L','processing_system7_vip_v1_0_24','-L','axi_vip_v1_1_22','-L','uvm','-L','xilinx_vip','-L','unisims_ver','-L','secureip','--snapshot','hp0_ddr_probe_tb','xil_defaultlib.hp0_ddr_probe_tb','-log','elaborate_probe.log')
 Invoke-Checked (Join-Path $tool 'xsim.bat') @('hp0_ddr_probe_tb','-runall','-log','probe.log')
 $result=Get-Content -LiteralPath 'probe.log' -Raw
 if($result -notmatch 'PROBE_HP_WRITES_PASS AW=5 W=80 B=5' -or $result -notmatch 'PROBE_RESULT '){throw 'Probe did not complete its checks'}
 if($result -match 'HP0_DDR_MINIMAL_REPRODUCED'){
  Write-Output 'HP0_DDR_MINIMAL_REPRODUCED: transport completed, strict DDR check failed.'
 } elseif($result -match 'HP0_DDR_MINIMAL_PASS' -and $result -notmatch 'Fatal:|AXI4_ERR[MS]_'){
  if(([regex]::Matches($result,'(?m)^PROBE_DDR_CONSUME_EDGE ')).Count -ne 5){throw 'Expected exactly five DDR request observations'}
  Write-Output 'HP0_DDR_MINIMAL_PASS'
 } else {throw 'Unexpected probe result'}
} finally {Pop-Location}
