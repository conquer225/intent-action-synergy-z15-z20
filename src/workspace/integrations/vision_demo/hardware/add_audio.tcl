set out [file normalize $::env(GL_VISION_BD_OUTPUT)]
set audio_ip [file normalize $::env(GL_AUDIO_HLS_IP)]
open_project [file join $out project hdmi_audio.xpr]
set_property ip_repo_paths [concat [get_property ip_repo_paths [current_project]] [list $audio_ip]] [current_project]
update_ip_catalog
open_bd_design [get_files system.bd]
set_property CONFIG.NUM_MI 8 [get_bd_cells ps7_0_axi_periph]
create_bd_cell -type ip -vlnv xilinx.com:hls:audio_fft:1.0 audio_fft_0
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M07_AXI] [get_bd_intf_pins audio_fft_0/s_axi_control]
foreach pin {audio_fft_0/ap_clk ps7_0_axi_periph/M07_ACLK} {
 connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $pin]
}
foreach pin {audio_fft_0/ap_rst_n ps7_0_axi_periph/M07_ARESETN} {
 connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins $pin]
}
assign_bd_address -offset 0x43c50000 -range 0x10000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs audio_fft_0/s_axi_control/Reg]
validate_bd_design
save_bd_design
write_bd_tcl -force [file join $out signal_bd.tcl]
puts SIGNAL_AUDIO_BD_READY
close_project
