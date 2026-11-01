set out [file normalize $::env(GL_VISION_BD_OUTPUT)]
set src [file normalize $::env(GL_VISION_SOURCE)]
open_project [file join $out project hdmi_audio.xpr]
add_files [list [file join $src hardware vision_stream_pixels.sv] [file join $src hardware vision_stream_histogram.sv] [file join $src hardware vision_stream_control.v] [file join $src hardware key_inputs.v]]
add_files -fileset constrs_1 [file join $src hardware keys.xdc]
set_property USED_IN_SYNTHESIS false [get_files keys.xdc]
update_compile_order -fileset sources_1
open_bd_design [get_files system.bd]
set_property CONFIG.NUM_MI 7 [get_bd_cells ps7_0_axi_periph]
create_bd_cell -type module -reference vision_stream_control vision_core_0
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 vision_keys_0
set_property -dict [list CONFIG.C_GPIO_WIDTH 2 CONFIG.C_ALL_INPUTS 1 CONFIG.C_IS_DUAL 0] [get_bd_cells vision_keys_0]
create_bd_cell -type module -reference key_inputs key_inputs_0
create_bd_port -dir I -from 1 -to 0 pl_keys
connect_bd_net [get_bd_ports pl_keys] [get_bd_pins key_inputs_0/keys]
connect_bd_net [get_bd_pins key_inputs_0/value] [get_bd_pins vision_keys_0/gpio_io_i]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M05_AXI] [get_bd_intf_pins vision_core_0/s_axi]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M06_AXI] [get_bd_intf_pins vision_keys_0/S_AXI]
foreach pin {vision_core_0/aclk vision_keys_0/s_axi_aclk key_inputs_0/aclk ps7_0_axi_periph/M05_ACLK ps7_0_axi_periph/M06_ACLK} {
  connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $pin]
}
foreach pin {vision_core_0/aresetn vision_keys_0/s_axi_aresetn key_inputs_0/aresetn ps7_0_axi_periph/M05_ARESETN ps7_0_axi_periph/M06_ARESETN} {
  connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins $pin]
}
connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins vision_core_0/pix_clk]
connect_bd_net [get_bd_pins ov5640_capture_data_0/cmos_frame_vsync] [get_bd_pins vision_core_0/cam_vsync]
connect_bd_net [get_bd_pins ov5640_capture_data_0/cmos_frame_clk] [get_bd_pins vision_core_0/cam_clk]
foreach {old new} {vid_data data vid_active_video de vid_hsync hsync vid_vsync vsync vid_hblank hblank vid_vblank vblank vid_field_id field} {
  set pin [get_bd_pins live_osd_0/in_$new]
  disconnect_bd_net [get_bd_nets -of_objects $pin] $pin
  connect_bd_net [get_bd_pins v_axi4s_vid_out_0/$old] [get_bd_pins vision_core_0/in_$new]
  connect_bd_net [get_bd_pins vision_core_0/out_$new] $pin
}
assign_bd_address -offset 0x43c30000 -range 0x10000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs vision_core_0/s_axi/*]
assign_bd_address -offset 0x43c40000 -range 0x10000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs vision_keys_0/S_AXI/Reg]
validate_bd_design
save_bd_design
write_bd_tcl -force [file join $out combined_bd.tcl]
puts VISION_STREAM_BD_READY
close_project
