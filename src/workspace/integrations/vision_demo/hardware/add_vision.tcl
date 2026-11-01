# Run after reconstructing the retained HDMI/audio BD; no board access.
set out [file normalize $::env(GL_VISION_BD_OUTPUT)]
set src [file normalize $::env(GL_VISION_SOURCE)]
set hls [file normalize $::env(GL_VISION_HLS_IP)]
set vendor [file normalize $::env(GL_VISION_VENDOR)]
open_project [file join $out project hdmi_audio.xpr]
set_property ip_repo_paths [list [file join $vendor ov5640_cap_data] $hls] [current_project]
update_ip_catalog
add_files [file join $src hardware key_inputs.v]
add_files -fileset constrs_1 [file join $src hardware keys.xdc]
set_property USED_IN_SYNTHESIS false [get_files keys.xdc]
open_bd_design [get_files system.bd]
set_property CONFIG.NUM_MI 7 [get_bd_cells ps7_0_axi_periph]
set_property CONFIG.NUM_SI 5 [get_bd_cells axi_mem_intercon]
create_bd_cell -type ip -vlnv xilinx.com:hls:vision_core:1.0 vision_core_0
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 vision_keys_0
set_property -dict [list CONFIG.C_GPIO_WIDTH 2 CONFIG.C_ALL_INPUTS 1 CONFIG.C_IS_DUAL 0] [get_bd_cells vision_keys_0]
create_bd_cell -type module -reference key_inputs key_inputs_0
create_bd_port -dir I -from 1 -to 0 pl_keys
connect_bd_net [get_bd_ports pl_keys] [get_bd_pins key_inputs_0/keys]
connect_bd_net [get_bd_pins key_inputs_0/value] [get_bd_pins vision_keys_0/gpio_io_i]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M05_AXI] [get_bd_intf_pins vision_core_0/s_axi_control]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M06_AXI] [get_bd_intf_pins vision_keys_0/S_AXI]
connect_bd_intf_net [get_bd_intf_pins vision_core_0/m_axi_memory] [get_bd_intf_pins axi_mem_intercon/S03_AXI]
connect_bd_intf_net [get_bd_intf_pins vision_core_0/m_axi_history_bus] [get_bd_intf_pins axi_mem_intercon/S04_AXI]
foreach pin {vision_core_0/ap_clk vision_keys_0/s_axi_aclk key_inputs_0/aclk ps7_0_axi_periph/M05_ACLK ps7_0_axi_periph/M06_ACLK axi_mem_intercon/S03_ACLK axi_mem_intercon/S04_ACLK} {
    connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $pin]
}
foreach pin {vision_core_0/ap_rst_n vision_keys_0/s_axi_aresetn key_inputs_0/aresetn ps7_0_axi_periph/M05_ARESETN ps7_0_axi_periph/M06_ARESETN axi_mem_intercon/S03_ARESETN axi_mem_intercon/S04_ARESETN} {
    connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins $pin]
}
assign_bd_address -offset 0x43c30000 -range 0x10000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs vision_core_0/s_axi_control/Reg]
assign_bd_address -offset 0x43c40000 -range 0x10000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs vision_keys_0/S_AXI/Reg]
foreach interface {m_axi_memory m_axi_history_bus} {
    assign_bd_address -target_address_space [get_bd_addr_spaces -of_objects [get_bd_intf_pins vision_core_0/$interface]] [get_bd_addr_segs processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM]
}
validate_bd_design
save_bd_design
write_bd_tcl -force [file join $out combined_bd.tcl]
puts VISION_COMBINED_BD_READY
close_project
