param([Parameter(Mandatory=$true)][string]$SimulationDirectory,
      [switch]$DisableOptimizations,
      [switch]$ObserveBackend,
      [string]$DiagnosticVendorSource)
$ErrorActionPreference='Stop'
$tool='D:/ruanjian/2025.2/Vivado/bin'
$libraries=@('xil_defaultlib','axi_infrastructure_v1_1_0','axi_vip_v1_1_22',
 'processing_system7_vip_v1_0_24','proc_sys_reset_v5_0_17','xlconstant_v1_1_10',
 'axi_datamover_v5_1_37','axi_sg_v4_1_21','axi_dma_v7_1_37','axi_lite_ipif_v3_0_4',
 'interrupt_control_v3_1_5','axi_gpio_v2_0_37','generic_baseblocks_v2_1_2',
 'axi_register_slice_v2_1_36','fifo_generator_v13_2_14','axi_data_fifo_v2_1_36',
 'axi_crossbar_v2_1_38','axi_protocol_converter_v2_1_37','uvm','xilinx_vip',
 'smartconnect_v1_0','unisims_ver','unimacro_ver','secureip','xpm')
$libArgs=foreach($library in $libraries){'-L';$library}
function Invoke-Checked([string]$exe,[string[]]$toolArgs){
 & $exe @toolArgs | Out-Null
 if($LASTEXITCODE -ne 0){throw "$exe failed: $LASTEXITCODE; inspect saved logs"}
}
Push-Location -LiteralPath $SimulationDirectory
try {
 if($ObserveBackend){Write-Warning 'Bus/control observation only: DDR mismatches are recorded, not accepted. This run cannot qualify deployment.'}
 if($DiagnosticVendorSource){
  if(!(Test-Path -LiteralPath $DiagnosticVendorSource -PathType Leaf)){throw 'Diagnostic vendor source not found'}
  Write-Warning 'Locally modified PS7 VIP model: strict checks are diagnostic only; this does not qualify the unmodified vendor model or hardware.'
  Invoke-Checked (Join-Path $tool 'xvlog.bat') @('--sv','--work','xil_defaultlib','-L','xilinx_vip','-d','XILINX_SIMULATOR','-i','D:/ruanjian/2025.2/Vivado/data/ip/xilinx/processing_system7_vip_v1_0/hdl','-i','D:/ruanjian/2025.2/Vivado/data/xilinx_vip/include',$DiagnosticVendorSource,'-log','compile_diagnostic_vendor.log')
 }
 Invoke-Checked (Join-Path $tool 'xvlog.bat') @('--incr','--relax','-L','xilinx_vip','-prj','vlog.prj')
 Invoke-Checked (Join-Path $tool 'xvhdl.bat') @('--incr','--relax','-prj','vhdl.prj')
 $suffix=if($DisableOptimizations){'_o0'}else{''}
 $snapshot="full_chain_reset_tb$suffix"
 $optimization=if($DisableOptimizations){@('--O0')}else{@()}
 Invoke-Checked (Join-Path $tool 'xelab.bat') (@('--incr','--debug','typical','--relax','--mt','2')+$optimization+$libArgs+@('--snapshot',$snapshot,'xil_defaultlib.full_chain_reset_tb','xil_defaultlib.glbl','-log',"elaborate_full_chain$suffix.log"))
 foreach($case in @('normal_drain','transient_stall','blocked')){
  $extra=if($case -eq 'normal_drain'){@()}else{@('-testplusarg',$case)}
  if($ObserveBackend){$extra+=@('-testplusarg','observe_backend')}
  $scope=if($ObserveBackend){'_bus_observation'}else{''}
  $log="$case$suffix$scope.log"
  Invoke-Checked (Join-Path $tool 'xsim.bat') (@($snapshot)+$extra+@('-runall','-log',$log))
  $text=Get-Content -LiteralPath $log -Raw
  $terminal=if($case -eq 'blocked'){'FULL_BLOCKED_LOCKOUT_PASS'}else{'FULL_GUARDED_RECOVERY_PASS'}
  foreach($marker in @('FULL_NORMAL_BUS_PASS','FULL_FILTER_DMA_HP_PASS','FULL_BOTH_INFLIGHT','NEW_SUBMISSION_REJECTED',$terminal)){
   if($text -notmatch $marker){throw "Missing '$marker': $log"}
  }
  $errors='Fatal:|(?m)^ERROR:|^Error:|XILINX_FATAL|AXI4_ERR[MS]_'
  $runtime=($text -split 'Executing Axi4 End Of Simulation checks',2)[0]
  if($runtime -match $errors -or ($case -ne 'blocked' -and $text -match $errors)){
   throw "Unexpected simulation/protocol failure: $log"
  }
  if($case -eq 'blocked' -and ($text -match 'Fatal:|GUARDED_LOCAL_RESET_PASS|FULL_GUARDED_RECOVERY_PASS')){
   throw "Blocked case reset/restarted or failed: $log"
  }
  if($case -eq 'blocked'){
   $end=($text -split 'Executing Axi4 End Of Simulation checks',2)[1]
   if($end -notmatch 'AXI4_ERRS_BRESP_ALL_DONE_EOS'){
    throw "Missing expected outstanding-write EOS diagnostic: $log"
   }
   if(($end -replace 'AXI4_ERRS_BRESP_ALL_DONE_EOS','EXPECTED_PENDING_WRITES') -match $errors){
    throw "Unexpected EOS protocol failure: $log"
   }
  }
  if(!$ObserveBackend -and $text -match 'VIP_DDR_MISMATCH'){throw "DDR backend mismatch: $log"}
  if(!$ObserveBackend -and $text -notmatch "$terminal[^\r\n]*backend_mismatches=0"){
   throw "Strict DDR zero-mismatch terminal missing: $log"
  }
  if(!$ObserveBackend){
   $expectedWrites=if($case -eq 'blocked'){5}else{15}
   $observedWrites=([regex]::Matches($text,'(?m)^DDR_COMMIT ')).Count
   if($observedWrites -ne $expectedWrites){throw "Unexpected DDR request count $observedWrites (expected $expectedWrites): $log"}
  }
  $qualification=if($DiagnosticVendorSource){'diagnostic VIP only'}elseif($ObserveBackend){'bus observation only'}else{'stock VIP strict'}
  Write-Output "$case : $terminal ($qualification)"
 }
} finally {Pop-Location}
