# Build only an isolated BD candidate. Never open, save or update the source project.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 is required"}
set source_bd {D:/ican/ican_fpga_project/GuardianLoop_Z15_2025_1/GuardianLoop_Z15_2025_1.srcs/sources_1/bd/guardianloop_bd/guardianloop_bd.bd}
set ip_repo {D:/ican/ican_fpga_project/GuardianLoop_Z15_2025_1/ip_repo}
set base {D:/ican/codex_project/gli26b}
set project [file join $base project]
set filter_src {D:/ican/codex_project/eeg_apps_z15/pl_filter_candidate}
set coeff {D:/ican/codex_project/eeg_apps_z15/output/pl_filter_v2025_2_20260927/coeff.hex}

if {![file isfile $source_bd] || ![file isdirectory $ip_repo] || ![file isfile $coeff]} {
    error "Missing audited source BD, IP repository or fixed-point coefficients"
}
if {[file exists $project]} {error "Refusing to overwrite an existing integrated project"}
create_project gl_filter_coexist_20260929 $project -part xc7z015clg485-2
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property ip_repo_paths [list $ip_repo] [current_project]
update_ip_catalog
foreach name {primary_sos_core.sv primary_sos_axis.sv primary_filter_top.sv} {
    add_files -norecurse [file join $filter_src $name]
}
set_property FILE_TYPE Verilog [get_files [file join $filter_src primary_filter_top.sv]]
add_files -norecurse $coeff
set_property FILE_TYPE {Memory Initialization Files} [get_files $coeff]
import_files -norecurse $source_bd
update_compile_order -fileset sources_1
set bd_files [get_files -filter {FILE_TYPE == "Block Designs"}]
if {[llength $bd_files] != 1} {error "Expected exactly one imported production BD: $bd_files"}
open_bd_design [lindex $bd_files 0]

if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Wrong FPGA part"}
set expected {processing_system7_0 rst_ps7_0_50M axi_smc_0 axi_smc_mem_0 axi_dma_0 guardianloop_regs_v0_0 guardianloop_eeg_quality_v0_0 guardianloop_eeg_de_accel_v0_0 guardianloop_hgb_accel_v0_0}
foreach cell $expected {
    if {[llength [get_bd_cells -quiet $cell]] != 1} {error "Production cell missing: $cell"}
}
foreach cell {pf_filter pf_dma pf_control pf_read_pc pf_write_pc} {
    if {[llength [get_bd_cells -quiet $cell]]} {error "Filter cell already exists: $cell"}
}
if {[get_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells processing_system7_0]] != 50.0} {
    error "Production FCLK0 is not 50 MHz"
}
if {[get_property CONFIG.NUM_MI [get_bd_cells axi_smc_0]] != 5 ||
    [get_property CONFIG.NUM_SI [get_bd_cells axi_smc_mem_0]] != 1} {
    error "Production AXI interconnect topology changed"
}
foreach {a b} {
    axi_dma_0/M_AXIS_MM2S guardianloop_eeg_de_accel_v0_0/s_axis
    axi_dma_0/M_AXI_MM2S axi_smc_mem_0/S00_AXI
    axi_smc_mem_0/M00_AXI processing_system7_0/S_AXI_HP0
} {
    set left [get_bd_intf_nets -of_objects [get_bd_intf_pins $a]]
    set right [get_bd_intf_nets -of_objects [get_bd_intf_pins $b]]
    if {[llength $left] != 1 || $left ne $right} {error "Production connection changed: $a -> $b"}
}

# The formal MM2S->DE->quality path remains untouched. The new filter has its
# own bidirectional DMA so ARM can read filtered samples for all tasks.
set_property CONFIG.NUM_MI 7 [get_bd_cells axi_smc_0]
set_property CONFIG.NUM_SI 3 [get_bd_cells axi_smc_mem_0]
create_bd_cell -type module -reference primary_filter_top pf_filter
set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:* pf_dma]
set_property -dict [list CONFIG.c_include_sg 0 CONFIG.c_include_mm2s 1 CONFIG.c_include_s2mm 1 \
    CONFIG.c_m_axi_mm2s_data_width 64 CONFIG.c_m_axi_s2mm_data_width 64 \
    CONFIG.c_m_axis_mm2s_tdata_width 64 CONFIG.c_s_axis_s2mm_tdata_width 64 \
    CONFIG.c_addr_width 32 CONFIG.c_sg_length_width 16] $dma
set gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:* pf_control]
set_property -dict [list CONFIG.C_IS_DUAL 1 CONFIG.C_GPIO_WIDTH 32 CONFIG.C_GPIO2_WIDTH 32 \
    CONFIG.C_ALL_OUTPUTS 1 CONFIG.C_ALL_INPUTS_2 1 CONFIG.C_DOUT_DEFAULT 0x00000001] $gpio
foreach name {pf_read_pc pf_write_pc} {
    set converter [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_protocol_converter:* $name]
    set_property -dict [list CONFIG.SI_PROTOCOL AXI4 CONFIG.MI_PROTOCOL AXI3 CONFIG.DATA_WIDTH 64] $converter
}
foreach {a b} {
    axi_smc_0/M05_AXI pf_dma/S_AXI_LITE
    axi_smc_0/M06_AXI pf_control/S_AXI
    pf_dma/M_AXI_MM2S pf_read_pc/S_AXI
    pf_dma/M_AXI_S2MM pf_write_pc/S_AXI
    pf_read_pc/M_AXI axi_smc_mem_0/S01_AXI
    pf_write_pc/M_AXI axi_smc_mem_0/S02_AXI
    pf_dma/M_AXIS_MM2S pf_filter/s_axis
    pf_filter/m_axis pf_dma/S_AXIS_S2MM
} {
    connect_bd_intf_net [get_bd_intf_pins $a] [get_bd_intf_pins $b]
}
connect_bd_net [get_bd_pins pf_control/gpio_io_o] [get_bd_pins pf_filter/control_word]
connect_bd_net [get_bd_pins pf_filter/status_word] [get_bd_pins pf_control/gpio2_io_i]
set clock [get_bd_pins processing_system7_0/FCLK_CLK0]
set resetn [get_bd_pins rst_ps7_0_50M/peripheral_aresetn]
if {[get_property CONFIG.POLARITY $resetn] ne "ACTIVE_LOW"} {error "Unexpected reset polarity"}
foreach pin {
    pf_filter/aclk pf_dma/s_axi_lite_aclk pf_dma/m_axi_mm2s_aclk pf_dma/m_axi_s2mm_aclk
    pf_control/s_axi_aclk pf_read_pc/aclk pf_write_pc/aclk
} {connect_bd_net $clock [get_bd_pins $pin]}
foreach pin {
    pf_filter/aresetn pf_dma/axi_resetn pf_control/s_axi_aresetn
    pf_read_pc/aresetn pf_write_pc/aresetn
} {connect_bd_net $resetn [get_bd_pins $pin]}

assign_bd_address
validate_bd_design
save_bd_design
puts "INTEGRATED_BD_VALIDATED_ONLY: [get_property NAME [current_project]]"
puts "NO_SYNTHESIS_NO_IMPLEMENTATION_NO_BITSTREAM_NO_BOARD_ACTION"
close_project
