set script_dir [file normalize [file dirname [info script]]]
set build_dir [file normalize [file join $script_dir build]]
set output_dir [file normalize [file join $script_dir output]]
file mkdir $build_dir
file mkdir $output_dir

set project_name z15_dma_add1
set design_name design_1
set part_name xc7z015clg485-2
create_project -force $project_name $build_dir -part $part_name
set_property target_language Verilog [current_project]
add_files -norecurse [file join $script_dir axis_add1.v]
update_compile_order -fileset sources_1
create_bd_design $design_name

set ps7 [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:* processing_system7_0]
set_property -dict [list \
  CONFIG.PCW_USE_M_AXI_GP0 {1} \
  CONFIG.PCW_USE_S_AXI_HP0 {1} \
  CONFIG.PCW_UIPARAM_DDR_MEMORY_TYPE {DDR 3 (Low Voltage)} \
  CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41K256M16 RE-125} \
  CONFIG.PCW_DDR_RAM_HIGHADDR {0x3FFFFFFF} \
  CONFIG.PCW_EN_CLK0_PORT {1} \
  CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100.000000} \
] $ps7
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/DDR]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/FIXED_IO]

set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:* axi_dma_0]
set_property -dict [list \
  CONFIG.c_include_sg {0} \
  CONFIG.c_include_mm2s {1} \
  CONFIG.c_include_s2mm {1} \
  CONFIG.c_m_axi_mm2s_data_width {32} \
  CONFIG.c_m_axi_s2mm_data_width {32} \
  CONFIG.c_m_axis_mm2s_tdata_width {32} \
  CONFIG.c_s_axis_s2mm_tdata_width {32} \
  CONFIG.c_sg_length_width {23} \
] $dma
set add1 [create_bd_cell -type module -reference axis_add1 axis_add1_0]
set lite_ic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:* axi_interconnect_0]
set_property -dict [list CONFIG.NUM_MI {1}] $lite_ic
set hp_ic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:* axi_interconnect_1]
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] $hp_ic
set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:* proc_sys_reset_0]

connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins axi_interconnect_0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M00_AXI] [get_bd_intf_pins axi_dma_0/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_MM2S] [get_bd_intf_pins axi_interconnect_1/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_S2MM] [get_bd_intf_pins axi_interconnect_1/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_1/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP0]

# The only changed PL datapath: MM2S -> +1 -> S2MM. Preserve TKEEP/TLAST and handshake.
foreach {source target} {
  axi_dma_0/m_axis_mm2s_tdata  axis_add1_0/s_axis_tdata
  axi_dma_0/m_axis_mm2s_tkeep  axis_add1_0/s_axis_tkeep
  axi_dma_0/m_axis_mm2s_tlast  axis_add1_0/s_axis_tlast
  axi_dma_0/m_axis_mm2s_tvalid axis_add1_0/s_axis_tvalid
  axis_add1_0/s_axis_tready    axi_dma_0/m_axis_mm2s_tready
  axis_add1_0/m_axis_tdata     axi_dma_0/s_axis_s2mm_tdata
  axis_add1_0/m_axis_tkeep     axi_dma_0/s_axis_s2mm_tkeep
  axis_add1_0/m_axis_tlast     axi_dma_0/s_axis_s2mm_tlast
  axis_add1_0/m_axis_tvalid    axi_dma_0/s_axis_s2mm_tvalid
  axi_dma_0/s_axis_s2mm_tready axis_add1_0/m_axis_tready
} {
  connect_bd_net [get_bd_pins $source] [get_bd_pins $target]
}

connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] \
  [get_bd_pins processing_system7_0/M_AXI_GP0_ACLK] \
  [get_bd_pins processing_system7_0/S_AXI_HP0_ACLK] \
  [get_bd_pins axi_interconnect_0/ACLK] \
  [get_bd_pins axi_interconnect_0/S00_ACLK] \
  [get_bd_pins axi_interconnect_0/M00_ACLK] \
  [get_bd_pins axi_interconnect_1/ACLK] \
  [get_bd_pins axi_interconnect_1/S00_ACLK] \
  [get_bd_pins axi_interconnect_1/S01_ACLK] \
  [get_bd_pins axi_interconnect_1/M00_ACLK] \
  [get_bd_pins axi_dma_0/s_axi_lite_aclk] \
  [get_bd_pins axi_dma_0/m_axi_mm2s_aclk] \
  [get_bd_pins axi_dma_0/m_axi_s2mm_aclk] \
  [get_bd_pins proc_sys_reset_0/slowest_sync_clk]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins proc_sys_reset_0/ext_reset_in]
connect_bd_net [get_bd_pins proc_sys_reset_0/interconnect_aresetn] \
  [get_bd_pins axi_interconnect_0/ARESETN] \
  [get_bd_pins axi_interconnect_0/S00_ARESETN] \
  [get_bd_pins axi_interconnect_0/M00_ARESETN] \
  [get_bd_pins axi_interconnect_1/ARESETN] \
  [get_bd_pins axi_interconnect_1/S00_ARESETN] \
  [get_bd_pins axi_interconnect_1/S01_ARESETN] \
  [get_bd_pins axi_interconnect_1/M00_ARESETN]
connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] [get_bd_pins axi_dma_0/axi_resetn]

assign_bd_address
set dma_ctrl [get_bd_addr_segs processing_system7_0/Data/SEG_axi_dma_0_Reg]
set_property offset 0x40400000 $dma_ctrl
set_property range 64K $dma_ctrl
validate_bd_design
save_bd_design

set bd_file [get_files [file join $build_dir $project_name.srcs sources_1 bd $design_name $design_name.bd]]
generate_target all $bd_file
make_wrapper -files $bd_file -top
add_files -norecurse [file join $build_dir $project_name.gen sources_1 bd $design_name hdl ${design_name}_wrapper.v]
update_compile_order -fileset sources_1
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
set run_status [get_property STATUS [get_runs impl_1]]
puts "IMPLEMENTATION_STATUS=$run_status"
if {![string match "write_bitstream Complete!*" $run_status]} {
  error "Implementation did not complete successfully: $run_status"
}
set bit_source [file join $build_dir $project_name.runs impl_1 ${design_name}_wrapper.bit]
file copy -force $bit_source [file join $output_dir z15_dma_add1.bit]
set hwh_candidates [glob -nocomplain [file join $build_dir $project_name.gen sources_1 bd $design_name hw_handoff *.hwh]]
if {[llength $hwh_candidates] == 0} {error "HWH metadata file was not generated"}
file copy -force [lindex $hwh_candidates 0] [file join $output_dir z15_dma_add1.hwh]
puts "Z15_PYNQ_DMA_ADD1_BUILD_OK"
exit
