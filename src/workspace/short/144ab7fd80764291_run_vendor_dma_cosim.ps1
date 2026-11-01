param(
    [string]$SimulationDirectory
)
$ErrorActionPreference = 'Stop'

$candidate = Split-Path -Parent $PSScriptRoot
$project = Join-Path $candidate 'output/pl_pipeline_build_v2025_2_20260927/project'
$sim = if ($SimulationDirectory) { $SimulationDirectory } else {
    Join-Path $candidate 'output/pl_hp0_duplex_cosim_v2025_2_20260928/export/xsim'
}
$tool = 'D:/ruanjian/2025.2/Vivado/bin'
if (-not (Test-Path -LiteralPath (Join-Path $sim 'xsim.ini'))) {
    throw "First export XSim files with export_vendor_sim.tcl: $sim"
}

$ip = Join-Path $project 'pl_filter_candidate_dma.gen/sources_1/bd/filter_candidate/ip'
$writeConverter = Join-Path $ip 'filter_candidate_pf_memory_imp_auto_pc_1/sim/filter_candidate_pf_memory_imp_auto_pc_1.v'
$writeTb = Join-Path $PSScriptRoot 'vendor_dma_write_reset_tb.sv'
$writePeer = Join-Path $PSScriptRoot 'vendor_dma_write_peer.sv'
$hpTb = Join-Path $PSScriptRoot 'vendor_hp0_reset_tb.sv'
$libraries = @(
    'xil_defaultlib','axi_infrastructure_v1_1_0','axi_vip_v1_1_22',
    'processing_system7_vip_v1_0_24','proc_sys_reset_v5_0_17',
    'xlconstant_v1_1_10','axi_datamover_v5_1_37','axi_sg_v4_1_21',
    'axi_dma_v7_1_37','axi_lite_ipif_v3_0_4','interrupt_control_v3_1_5',
    'axi_gpio_v2_0_37','generic_baseblocks_v2_1_2',
    'axi_register_slice_v2_1_36','fifo_generator_v13_2_14',
    'axi_data_fifo_v2_1_36','axi_crossbar_v2_1_38',
    'axi_protocol_converter_v2_1_37','uvm','xilinx_vip',
    'unisims_ver','unimacro_ver','secureip','xpm'
)
$libArgs = foreach ($library in $libraries) { '-L'; $library }

function Invoke-Checked([string]$exe,[string[]]$toolArgs) {
    & $exe @toolArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "$exe failed with exit code $LASTEXITCODE" }
}

function Assert-Case([string]$snapshot,[string]$name,[string[]]$extraArgs,[string]$expected) {
    $log = "$name.log"
    Invoke-Checked (Join-Path $tool 'xsim.bat') (@($snapshot) + $extraArgs + @('-runall','-log',$log))
    $contents = Get-Content -LiteralPath $log -Raw
    if ($contents -notmatch [regex]::Escape($expected)) {
        throw "Missing expected result '$expected' in $log"
    }
    if ($expected -like '*_PASS' -and $contents -match 'Fatal:') {
        throw "Unexpected simulation fatal in passing case: $log"
    }
    if ($name -like 'duplex_*') {
        foreach ($marker in @('NORMAL_DUPLEX_PASS','BOTH_INFLIGHT_CONFIRMED')) {
            if ($contents -notmatch $marker) { throw "Missing duplex coverage '$marker': $log" }
        }
    }
    if ($name -eq 'duplex_soft_preserve' -and $contents -notmatch 'SOFT_DUPLEX_DRAIN_AND_HALT_CONFIRMED') {
        throw "Software reset did not prove drain/halt before restart: $log"
    }
    if ($name -eq 'duplex_drain_then_external' -and $contents -notmatch 'BOTH_DRAINED_BEFORE_EXTERNAL_RESET') {
        throw "External reset did not follow proven drain: $log"
    }
    if ($name -eq 'duplex_soft_blocked' -and $contents -match 'addr=0000[36]000|POST_RESET_DUPLEX_PASS') {
        throw "Blocked case incorrectly restarted: $log"
    }
    if ($expected -like 'Fatal:*' -and ([regex]::Matches($contents,'Fatal:').Count -ne 1 -or $contents -match 'POST_RESET_.*_PASS')) {
        throw "Expected failure case has an inconsistent terminal result: $log"
    }
    if ($contents -match '(?m)^Error:|^ERROR:') { throw "Unexpected simulator/VIP error: $log" }
    Write-Output "$name : $expected"
}

Push-Location -LiteralPath $sim
try {
    Invoke-Checked (Join-Path $tool 'xvlog.bat') @('--incr','--relax','--sv','--work','xil_defaultlib',$writeConverter,$writePeer,$writeTb,$hpTb)
    Invoke-Checked (Join-Path $tool 'xvlog.bat') @('--incr','--relax','-prj','vlog.prj')
    Invoke-Checked (Join-Path $tool 'xvhdl.bat') @('--incr','--relax','-prj','vhdl.prj')
    foreach ($top in @('vendor_dma_reset_tb','vendor_dma_write_reset_tb','vendor_hp0_reset_tb')) {
        Invoke-Checked (Join-Path $tool 'xelab.bat') (@('--incr','--debug','typical','--relax','--mt','2') + $libArgs + @('--snapshot',$top,"xil_defaultlib.$top",'xil_defaultlib.glbl','-log',"elaborate_$top.log"))
    }
    # XSim returns zero even on Verilog $fatal, so inspect the specific log text.
    Assert-Case 'vendor_hp0_reset_tb' 'hp0_fclk_preserve' @() 'HP0_VIP_PENDING_SURVIVES_FCLK_RESET_PASS'
    Assert-Case 'vendor_dma_reset_tb' 'read_external_preserve' @() 'Fatal: stream mismatch beat=0'
    Assert-Case 'vendor_dma_reset_tb' 'read_external_then_soft_reset' @('-testplusarg','software_quiesce') 'Fatal: stream mismatch beat=0'
    Assert-Case 'vendor_dma_reset_tb' 'read_external_flush' @('-testplusarg','flush_memory_on_reset') 'POST_RESET_READ_PASS'
    Assert-Case 'vendor_dma_reset_tb' 'read_soft_preserve' @('-testplusarg','soft_reset_inflight') 'POST_RESET_READ_PASS'
    Assert-Case 'vendor_dma_write_reset_tb' 'write_external_preserve' @() 'Fatal: bad WSTRB/WLAST'
    Assert-Case 'vendor_dma_write_reset_tb' 'write_external_flush' @('-testplusarg','flush_memory_on_reset') 'POST_RESET_WRITE_PASS'
    Assert-Case 'vendor_dma_write_reset_tb' 'write_soft_preserve' @('-testplusarg','soft_reset_inflight') 'POST_RESET_WRITE_PASS'
    Assert-Case 'vendor_dma_reset_tb' 'duplex_external_preserve' @('-testplusarg','duplex') 'Fatal: stream mismatch beat=0'
    Assert-Case 'vendor_dma_reset_tb' 'duplex_external_write_preserve' @('-testplusarg','duplex','-testplusarg','write_restart_first') 'Fatal: duplex bad WSTRB/WLAST'
    Assert-Case 'vendor_dma_reset_tb' 'duplex_external_flush' @('-testplusarg','duplex','-testplusarg','flush_memory_on_reset') 'POST_RESET_DUPLEX_PASS'
    Assert-Case 'vendor_dma_reset_tb' 'duplex_soft_preserve' @('-testplusarg','duplex','-testplusarg','soft_reset_inflight') 'POST_RESET_DUPLEX_PASS'
    Assert-Case 'vendor_dma_reset_tb' 'duplex_drain_then_external' @('-testplusarg','duplex','-testplusarg','drain_before_reset') 'POST_RESET_DUPLEX_PASS'
    Assert-Case 'vendor_dma_reset_tb' 'duplex_soft_blocked' @('-testplusarg','duplex','-testplusarg','soft_reset_inflight','-testplusarg','never_release') 'BLOCKED_DRAIN_NO_RESTART_PASS'
} finally {
    Pop-Location
}
