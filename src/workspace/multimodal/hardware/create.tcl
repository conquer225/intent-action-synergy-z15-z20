set root [file normalize [file join [file dirname [info script]] ..]]
set repo [file dirname $root]
set output [file join $root build vivado]
create_project intent_one $output -part xc7z015clg485-2 -force
set_property ip_repo_paths [list [file join $root hardware source ip_repo]] [current_project]
update_ip_catalog
import_files -norecurse [file join $root hardware source system.bd]
import_files -fileset constrs_1 -norecurse [file join $root hardware source pin.xdc]
add_files -fileset constrs_1 -norecurse [file join $root hardware source live_osd_cdc.xdc]
set_property USED_IN_SYNTHESIS false [get_files live_osd_cdc.xdc]
add_files -norecurse [file join $root hardware signal_core.sv]
add_files -norecurse [file join $root hardware signal_axis.v]
add_files -norecurse [file join $root hardware stimulus_core.sv]
add_files -norecurse [file join $root hardware key_inputs.v]
add_files -fileset constrs_1 -norecurse [file join $root hardware keys.xdc]
set_property USED_IN_SYNTHESIS false [get_files keys.xdc]
open_bd_design [get_files system.bd]
set ps [get_bd_cells processing_system7_0]
set_property -dict [list CONFIG.PCW_FPGA_FCLK2_ENABLE {1} CONFIG.PCW_EN_CLK2_PORT {1} CONFIG.PCW_FPGA2_PERIPHERAL_FREQMHZ {25}] $ps
set_property CONFIG.PRIM_SOURCE {No_buffer} [get_bd_cells clk_wiz_0]
source [file join $root hardware add_live_osd.tcl]
set_property CONFIG.NUM_MI {7} [get_bd_cells ps7_0_axi_periph]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 axi_gpio_keys
set_property -dict [list CONFIG.C_GPIO_WIDTH {2} CONFIG.C_ALL_INPUTS {1} CONFIG.C_IS_DUAL {0} CONFIG.C_INTERRUPT_PRESENT {0}] [get_bd_cells axi_gpio_keys]
create_bd_cell -type module -reference key_inputs key_inputs_0
create_bd_port -dir I -from 1 -to 0 pl_keys
connect_bd_net [get_bd_ports pl_keys] [get_bd_pins key_inputs_0/keys]
connect_bd_net [get_bd_pins key_inputs_0/value] [get_bd_pins axi_gpio_keys/gpio_io_i]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M06_AXI] [get_bd_intf_pins axi_gpio_keys/S_AXI]
foreach pin {axi_gpio_keys/s_axi_aclk key_inputs_0/aclk ps7_0_axi_periph/M06_ACLK} {
 connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $pin]
}
foreach pin {axi_gpio_keys/s_axi_aresetn key_inputs_0/aresetn ps7_0_axi_periph/M06_ARESETN} {
 connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins $pin]
}
assign_bd_address -offset 0x41210000 -range 0x10000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs axi_gpio_keys/S_AXI/Reg] -force
set_property CONFIG.NUM_SI {4} [get_bd_cells axi_mem_intercon]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_signal
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK2] [get_bd_pins rst_signal/slowest_sync_clk]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins rst_signal/ext_reset_in]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 signal_clock_locked
set_property CONFIG.CONST_VAL {1} [get_bd_cells signal_clock_locked]
connect_bd_net [get_bd_pins signal_clock_locked/dout] [get_bd_pins rst_signal/dcm_locked]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_signal
set_property -dict [list CONFIG.c_include_sg {0} CONFIG.c_include_mm2s_dre {1} CONFIG.c_include_s2mm_dre {1} CONFIG.c_sg_length_width {23}] [get_bd_cells axi_dma_signal]
create_bd_cell -type module -reference signal_axis signal_core_0
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M04_AXI] [get_bd_intf_pins axi_dma_signal/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M05_AXI] [get_bd_intf_pins signal_core_0/s_axi]
# One additional memory crossbar gathers DMA reads/writes into existing HP0.
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 signal_memory
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] [get_bd_cells signal_memory]
connect_bd_intf_net [get_bd_intf_pins axi_dma_signal/M_AXI_MM2S] [get_bd_intf_pins signal_memory/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_signal/M_AXI_S2MM] [get_bd_intf_pins signal_memory/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins signal_memory/M00_AXI] [get_bd_intf_pins axi_mem_intercon/S03_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_signal/M_AXIS_MM2S] [get_bd_intf_pins signal_core_0/s_axis]
connect_bd_intf_net [get_bd_intf_pins signal_core_0/m_axis] [get_bd_intf_pins axi_dma_signal/S_AXIS_S2MM]
foreach pin {axi_dma_signal/s_axi_lite_aclk axi_dma_signal/m_axi_mm2s_aclk axi_dma_signal/m_axi_s2mm_aclk signal_core_0/aclk signal_memory/ACLK signal_memory/S00_ACLK signal_memory/S01_ACLK signal_memory/M00_ACLK axi_mem_intercon/S03_ACLK ps7_0_axi_periph/M04_ACLK ps7_0_axi_periph/M05_ACLK} {
 connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK2] [get_bd_pins $pin]
}
foreach pin {axi_dma_signal/axi_resetn signal_core_0/aresetn signal_memory/ARESETN signal_memory/S00_ARESETN signal_memory/S01_ARESETN signal_memory/M00_ARESETN axi_mem_intercon/S03_ARESETN ps7_0_axi_periph/M04_ARESETN ps7_0_axi_periph/M05_ARESETN} {
 connect_bd_net [get_bd_pins rst_signal/peripheral_aresetn] [get_bd_pins $pin]
}
assign_bd_address -offset 0x40400000 -range 0x10000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs axi_dma_signal/S_AXI_LITE/Reg] -force
assign_bd_address -offset 0x43c20000 -range 0x10000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs -of_objects [get_bd_intf_pins signal_core_0/s_axi]] -force
assign_bd_address -target_address_space [get_bd_addr_spaces axi_dma_signal/Data_MM2S] [get_bd_addr_segs processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM]
assign_bd_address -target_address_space [get_bd_addr_spaces axi_dma_signal/Data_S2MM] [get_bd_addr_segs processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM]
validate_bd_design
save_bd_design
add_files -norecurse [make_wrapper -files [get_files system.bd] -top]
set_property top system_wrapper [current_fileset]
set_property synth_checkpoint_mode None [get_files system.bd]
generate_target all [get_files system.bd]
update_compile_order -fileset sources_1
set_param general.maxThreads 4
synth_design -top system_wrapper -part xc7z015clg485-2 -flatten_hierarchy rebuilt
write_checkpoint -force [file join $root build synthesized.dcp]
opt_design
place_design
phys_opt_design
route_design
write_checkpoint -force [file join $root build routed.dcp]
report_timing_summary -file [file join $root build timing.rpt]
report_utilization -file [file join $root build utilization.rpt]
report_cdc -file [file join $root build cdc.rpt]
if {[get_property SLACK [get_timing_paths -max_paths 1]] < 0 || [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]] < 0} {error "Timing failed; release refused"}
file mkdir [file join $root release]
write_bitstream -force [file join $root release intent_one.bit]
write_hw_platform -fixed -force -file [file join $root release intent_one.xsa]
file copy -force [lindex [glob [file join $output intent_one.gen sources_1 bd * hw_handoff system.hwh]] 0] [file join $root release intent_one.hwh]
close_project
