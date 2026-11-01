$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sim = Join-Path $root 'output/pl_ddr_lifecycle_20260928/sim'
$bin = 'D:/ruanjian/2025.2/Vivado/bin'
& 'D:/Users/lenovo/anaconda3/python.exe' "$PSScriptRoot/prepare_independent_memory.py"
if ($LASTEXITCODE) { throw 'harness generation failed' }
Push-Location $sim
try {
  & "$bin/xvlog.bat" --relax -L xilinx_vip -prj vlog.prj -log compile_verilog.log
  if ($LASTEXITCODE) { throw 'xvlog failed' }
  & "$bin/xvhdl.bat" --relax -prj vhdl.prj -log compile_vhdl.log
  if ($LASTEXITCODE) { throw 'xvhdl failed' }
  $libraries = 'xil_defaultlib axi_infrastructure_v1_1_0 axi_vip_v1_1_22 processing_system7_vip_v1_0_24 proc_sys_reset_v5_0_17 xlconstant_v1_1_10 axi_datamover_v5_1_37 axi_sg_v4_1_21 axi_dma_v7_1_37 axi_lite_ipif_v3_0_4 interrupt_control_v3_1_5 axi_gpio_v2_0_37 generic_baseblocks_v2_1_2 axi_register_slice_v2_1_36 fifo_generator_v13_2_14 axi_data_fifo_v2_1_36 axi_crossbar_v2_1_38 smartconnect_v1_0 axi_protocol_converter_v2_1_37 uvm xilinx_vip unisims_ver unimacro_ver secureip xpm'.Split(' ')
  $options = @('--debug','typical','--relax','--mt','2')
  foreach ($library in $libraries) { $options += @('-L', $library) }
  & "$bin/xelab.bat" @options --snapshot independent_memory xil_defaultlib.full_chain_reset_tb xil_defaultlib.glbl -log elaborate.log
  if ($LASTEXITCODE) { throw 'xelab failed' }
  foreach ($case in @('normal','transient_stall','blocked','corrupt_last_burst','corrupt_rx_guard')) {
    $options = @('independent_memory','-tclbatch','run.tcl','-log',"$case.log")
    if ($case -ne 'normal') { $options += @('-testplusarg',$case) }
    & "$bin/xsim.bat" @options
    if ($LASTEXITCODE) { throw "xsim invocation failed: $case" }
    $log = Get-Content -Raw "$case.log"
    if ($case -eq 'corrupt_last_burst') {
      if ($log -notmatch 'INDEPENDENT_MEMORY_MISMATCH frame=0 words=16 first_bad=64' -or $log -notmatch 'Fatal: DDR golden mismatch') { throw 'negative last-burst test did not detect corruption' }
    } elseif ($case -eq 'corrupt_rx_guard') {
      if ($log -notmatch 'Fatal: independent memory RX guard overwritten word=7') { throw 'negative RX guard test did not detect corruption' }
    } elseif ($log -match 'Fatal:|Error:') { throw "simulation failed: $case" }
    elseif ($case -eq 'blocked') {
      if ($log -notmatch 'FULL_BLOCKED_LOCKOUT_PASS.*backend_mismatches=0') { throw 'blocked lockout missing' }
    } elseif ($log -notmatch 'FULL_GUARDED_RECOVERY_PASS.*backend_mismatches=0' -or $log -notmatch 'INDEPENDENT_MEMORY_RETAINED_AFTER_PL_RESET words=80') { throw "strict recovery or memory retention missing: $case" }
    if ($case -eq 'normal' -or $case -eq 'transient_stall') {
      & 'D:/Users/lenovo/anaconda3/python.exe' "$PSScriptRoot/verify_hp0_axi_write_trace.py" "$case.log" 'vectors.txt'
      if ($LASTEXITCODE) { throw "independent AW/W/B shadow check failed: $case" }
    }
  }
} finally { Pop-Location }
