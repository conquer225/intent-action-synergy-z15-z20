set script_dir [file normalize [file dirname [info script]]]
set build_dir [file normalize [file join $script_dir build]]
set output_dir [file normalize [file join $script_dir output]]

file mkdir $build_dir
file mkdir $output_dir

set project_name z15_led
set design_name design_1
set part_name xc7z015clg485-2

create_project -force $project_name $build_dir -part $part_name
set_property target_language Verilog [current_project]

create_bd_design $design_name

set ps7 [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:* processing_system7_0]
set_property -dict [list \
  CONFIG.PCW_USE_M_AXI_GP0 {1} \
  CONFIG.PCW_EN_CLK0_PORT {1} \
  CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100.000000} \
] $ps7
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/DDR]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/FIXED_IO]

set axi_ic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:* axi_interconnect_0]
set_property -dict [list CONFIG.NUM_MI {1}] $axi_ic

set axi_gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:* axi_gpio_0]
set_property -dict [list \
  CONFIG.C_GPIO_WIDTH {2} \
  CONFIG.C_ALL_OUTPUTS {1} \
  CONFIG.C_IS_DUAL {0} \
  CONFIG.C_INTERRUPT_PRESENT {0} \
] $axi_gpio

create_bd_port -dir O -from 1 -to 0 led
connect_bd_net [get_bd_pins axi_gpio_0/gpio_io_o] [get_bd_ports led]

set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:* proc_sys_reset_0]

connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins axi_interconnect_0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M00_AXI] [get_bd_intf_pins axi_gpio_0/S_AXI]

connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] \
  [get_bd_pins processing_system7_0/M_AXI_GP0_ACLK] \
  [get_bd_pins axi_interconnect_0/ACLK] \
  [get_bd_pins axi_interconnect_0/S00_ACLK] \
  [get_bd_pins axi_interconnect_0/M00_ACLK] \
  [get_bd_pins axi_gpio_0/s_axi_aclk] \
  [get_bd_pins proc_sys_reset_0/slowest_sync_clk]

connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins proc_sys_reset_0/ext_reset_in]
connect_bd_net [get_bd_pins proc_sys_reset_0/interconnect_aresetn] \
  [get_bd_pins axi_interconnect_0/ARESETN] \
  [get_bd_pins axi_interconnect_0/S00_ARESETN] \
  [get_bd_pins axi_interconnect_0/M00_ARESETN]
connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] [get_bd_pins axi_gpio_0/s_axi_aresetn]

assign_bd_address
set gpio_segment [get_bd_addr_segs processing_system7_0/Data/SEG_axi_gpio_0_Reg]
set_property offset 0x41200000 $gpio_segment
set_property range 64K $gpio_segment

validate_bd_design
save_bd_design

set bd_file [get_files [file join $build_dir $project_name.srcs sources_1 bd $design_name $design_name.bd]]
generate_target all $bd_file
make_wrapper -files $bd_file -top
add_files -norecurse [file join $build_dir $project_name.gen sources_1 bd $design_name hdl ${design_name}_wrapper.v]
add_files -fileset constrs_1 -norecurse [file join $script_dir z15_led.xdc]
update_compile_order -fileset sources_1

launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1

set run_status [get_property STATUS [get_runs impl_1]]
puts "IMPLEMENTATION_STATUS=$run_status"
if {![string match "write_bitstream Complete!*" $run_status]} {
  error "Implementation did not complete successfully: $run_status"
}

set bit_source [file join $build_dir $project_name.runs impl_1 ${design_name}_wrapper.bit]
if {![file exists $bit_source]} {
  error "Bitstream not found: $bit_source"
}
file copy -force $bit_source [file join $output_dir z15_led.bit]

set hwh_candidates [glob -nocomplain \
  [file join $build_dir $project_name.gen sources_1 bd $design_name hw_handoff *.hwh] \
  [file join $build_dir $project_name.srcs sources_1 bd $design_name hw_handoff *.hwh]]
if {[llength $hwh_candidates] == 0} {
  error "HWH metadata file was not generated"
}
file copy -force [lindex $hwh_candidates 0] [file join $output_dir z15_led.hwh]

set report_file [file join $output_dir build_summary.txt]
set fp [open $report_file w]
puts $fp "part=$part_name"
puts $fp "status=$run_status"
puts $fp "led0=E4 LVCMOS18"
puts $fp "led1=E3 LVCMOS18"
puts $fp "bit=[file join $output_dir z15_led.bit]"
puts $fp "hwh=[file join $output_dir z15_led.hwh]"
close $fp

puts "Z15_PYNQ_LED_OVERLAY_BUILD_OK"
exit
