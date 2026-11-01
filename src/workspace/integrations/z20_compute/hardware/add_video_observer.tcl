# Run from integration root with prepared Vivado 2023.1 executable.
set root [file normalize [file join [file dirname [info script]] ..]]
set ipdir $root/build/video_observer_ip
create_project observer_pack $root/build/observer_pack -part xc7z020clg484-2 -force
set_property source_mgmt_mode None [current_project]
add_files [list $root/hardware/rtl/z20_video_epoch.sv $root/hardware/rtl/z20_video_observer.sv]
set_property top z20_video_observer [current_fileset]
update_compile_order -fileset sources_1
ipx::package_project -root_dir $ipdir -vendor z20.local -library user -taxonomy /UserIP -import_files -set_current true -force
set core [ipx::current_core]
set_property name z20_video_observer $core
set_property version 1.3 $core
ipx::infer_bus_interfaces xilinx.com:interface:aximm_rtl:1.0 $core
set bus [ipx::get_bus_interfaces s_axi -of_objects $core]
if {[llength $bus]!=1} {error "Missing inferred AXI interface"}
set_property interface_mode slave $bus
set protocol [ipx::get_bus_parameters PROTOCOL -of_objects $bus]
if {[llength $protocol]==0} {set protocol [ipx::add_bus_parameter PROTOCOL $bus]}
set_property value AXI4LITE $protocol
set mm [ipx::add_memory_map s_axi $core]
set block [ipx::add_address_block regs $mm]
set_property range 256 $block
set_property width 32 $block
set_property usage register $block
set_property slave_memory_map_ref s_axi $bus
ipx::associate_bus_interfaces -busif s_axi -clock aclk $core
ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::save_core $core
close_project
open_project $root/build/z20_video_npu/project/z20_video_npu.xpr
set_property ip_repo_paths [lsort -unique [concat [get_property ip_repo_paths [current_project]] [list $ipdir]]] [current_project]
update_ip_catalog
open_bd_design [get_files system.bd]
if {![llength [get_bd_cells -quiet video_observer]]} {
create_bd_cell -type ip -vlnv z20.local:user:z20_video_observer:1.3 video_observer
set_property CONFIG.NUM_MI 6 [get_bd_cells ps7_0_axi_periph]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M05_AXI] [get_bd_intf_pins video_observer/s_axi]
set memclk [get_bd_nets -of_objects [get_bd_pins axi_vdma_0/m_axi_s2mm_aclk]]
connect_bd_net -net $memclk [get_bd_pins video_observer/aclk] [get_bd_pins ps7_0_axi_periph/M05_ACLK]
set memrst [get_bd_nets -of_objects [get_bd_pins rst_ps7_0_150M/peripheral_aresetn]]
connect_bd_net -net $memrst [get_bd_pins video_observer/aresetn] [get_bd_pins ps7_0_axi_periph/M05_ARESETN]
}
upgrade_bd_cells [get_bd_cells video_observer]
foreach cam {0 1} {
 foreach signal {awaddr awlen awsize awvalid awready bvalid bready bresp} {
  set source [get_bd_pins axi_vdma_${cam}/m_axi_s2mm_${signal}]
  set peer [get_bd_pins axi_mem_intercon/S0${cam}_AXI_${signal}]
  set net [get_bd_nets -of_objects $source]
  if {[llength $net]} {
   foreach sink [list $peer [get_bd_pins video_observer/cam${cam}_${signal}]] {
    set existing [get_bd_nets -quiet -of_objects $sink]
    if {![llength $existing]} {connect_bd_net -net $net $sink}
    if {[llength $existing] && $existing ne $net} {error "Unexpected tap net on $sink"}
   }
  } else {
   connect_bd_net $source $peer [get_bd_pins video_observer/cam${cam}_${signal}]
  }
 }
}
if {![llength [get_bd_addr_segs -quiet processing_system7_0/Data/SEG_video_observer_regs]]} {
 assign_bd_address -offset 0x43C20000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs video_observer/s_axi/regs]
}
validate_bd_design
save_bd_design
write_bd_tcl -force $root/build/z20_video_npu/system_with_observer.tcl
generate_target all [get_files system.bd]
update_compile_order -fileset sources_1
create_ip_run [get_files system.bd]
reset_run [get_runs system_video_observer_0_synth_1]
reset_run synth_1
launch_runs synth_1 -scripts_only
puts OBSERVER_INTEGRATION_READY
exit
