# Extend the maintained vendor BD without editing the external original project.
add_files -norecurse [glob [file join $root hardware source rtl *.v] [file join $root hardware source rtl *.sv]]
update_compile_order -fileset sources_1
create_bd_cell -type module -reference live_osd live_osd_0
set_property -dict [list CONFIG.WIDTH {1280} CONFIG.HEIGHT {720} CONFIG.PIXEL_HZ {75000000}] [get_bd_cells live_osd_0]
set_property CONFIG.NUM_MI {4} [get_bd_cells ps7_0_axi_periph]
set_property CONFIG.NUM_SI {3} [get_bd_cells axi_mem_intercon]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 axi_vdma_1
set_property -dict [list CONFIG.c_include_mm2s {0} CONFIG.c_include_s2mm {1} \
    CONFIG.c_num_fstores {2} \
    CONFIG.c_s2mm_linebuffer_depth {2048} CONFIG.c_s2mm_max_burst_length {64} \
    CONFIG.c_include_internal_genlock {0} CONFIG.c_s2mm_genlock_mode {0}] [get_bd_cells axi_vdma_1]
create_bd_cell -type ip -vlnv xilinx.com:ip:v_vid_in_axi4s:5.0 v_vid_snapshot
set_property CONFIG.C_HAS_ASYNC_CLK {1} [get_bd_cells v_vid_snapshot]
delete_bd_objs [get_bd_intf_nets -of_objects [get_bd_intf_pins ov5640_capture_data_0/cmos_rgb]]
foreach {source target} {cmos_frame_data vid_data cmos_active_video vid_active_video cmos_frame_vsync vid_vsync} {
    connect_bd_net [get_bd_pins ov5640_capture_data_0/$source] [get_bd_pins v_vid_in_axi4s_0/$target] [get_bd_pins v_vid_snapshot/$target]
}
connect_bd_intf_net [get_bd_intf_pins v_vid_snapshot/video_out] [get_bd_intf_pins axi_vdma_1/S_AXIS_S2MM]
connect_bd_intf_net [get_bd_intf_pins axi_vdma_1/M_AXI_S2MM] [get_bd_intf_pins axi_mem_intercon/S02_AXI]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M02_AXI] [get_bd_intf_pins axi_vdma_1/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M03_AXI] [get_bd_intf_pins live_osd_0/s_axi]
# Dynamic genlock prevents writer/reader ownership collisions under unequal rates.
set_property -dict [list CONFIG.c_num_fstores {3} CONFIG.c_include_internal_genlock {1} \
    CONFIG.c_s2mm_genlock_mode {2} CONFIG.c_mm2s_genlock_mode {3}] [get_bd_cells axi_vdma_0]
foreach pin {axi_vdma_1/s_axi_lite_aclk axi_vdma_1/m_axi_s2mm_aclk axi_vdma_1/s_axis_s2mm_aclk v_vid_snapshot/aclk axi_mem_intercon/S02_ACLK ps7_0_axi_periph/M02_ACLK ps7_0_axi_periph/M03_ACLK live_osd_0/aclk} {
    connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $pin]
}
foreach pin {axi_vdma_1/axi_resetn axi_mem_intercon/S02_ARESETN ps7_0_axi_periph/M02_ARESETN ps7_0_axi_periph/M03_ARESETN live_osd_0/aresetn} {
    connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins $pin]
}
connect_bd_net [get_bd_pins clk_wiz_0/locked] [get_bd_pins v_vid_snapshot/aresetn]
connect_bd_net [get_bd_pins util_vector_logic_0/Res] [get_bd_pins v_vid_snapshot/vid_io_in_reset]
connect_bd_net [get_bd_pins ov5640_capture_data_0/cmos_frame_ce] [get_bd_pins v_vid_snapshot/vid_io_in_ce]
connect_bd_net [get_bd_pins ov5640_capture_data_0/cmos_frame_clk] [get_bd_pins v_vid_snapshot/vid_io_in_clk]
connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins live_osd_0/pix_clk]
# Replace the bundled video interface with explicit aligned native signals.
delete_bd_objs [get_bd_intf_nets -of_objects [get_bd_intf_pins DVI_Transmitter_0/Video_In]]
foreach {source target} {vid_data in_data vid_active_video in_de vid_hsync in_hsync vid_vsync in_vsync vid_hblank in_hblank vid_vblank in_vblank vid_field_id in_field} {
    connect_bd_net [get_bd_pins v_axi4s_vid_out_0/$source] [get_bd_pins live_osd_0/$target]
}
foreach {source target} {out_data video_din out_de video_de out_hsync video_hsync out_vsync video_vsync} {
    connect_bd_net [get_bd_pins live_osd_0/$source] [get_bd_pins DVI_Transmitter_0/$target]
}
connect_bd_net [get_bd_pins ov5640_capture_data_0/cmos_frame_vsync] [get_bd_pins live_osd_0/cam_vsync]
assign_bd_address -offset 0x43010000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs axi_vdma_1/S_AXI_LITE/Reg] -force
assign_bd_address -offset 0x43C00000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs -of_objects [get_bd_intf_pins live_osd_0/s_axi]] -force
assign_bd_address -target_address_space [get_bd_addr_spaces axi_vdma_1/Data_S2MM] [get_bd_addr_segs processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM]
