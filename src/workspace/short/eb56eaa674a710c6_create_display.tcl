if {$argc != 4} {error "Usage: create_display.tcl NEW_OUTPUT_DIR SOURCE_ROOT VENDOR_IP_ROOT SERIALIZER"}
lassign $argv out source_root vendor serializer
if {[file exists [file join $out project]]} {error "Refusing an existing project"}
source [file join $out legacy_contract.tcl]
create_project hdmi_audio [file join $out project] -part xc7z015clg485-2
set_property ip_repo_paths [list [file join $vendor ov5640_cap_data]] [current_project]
set_property XPM_LIBRARIES {XPM_FIFO XPM_CDC} [current_project]
update_ip_catalog
add_files [glob [file join $source_root rtl *.sv]]
set upstream [file join $source_root third_party hdmi src]
foreach name {packet_picker packet_assembler audio_clock_regeneration_packet audio_sample_packet audio_info_frame auxiliary_video_information_info_frame source_product_description_info_frame tmds_channel} {
    add_files [file join $upstream ${name}.sv]
}
add_files [list $serializer]
foreach name {display_status pcm_buffer audio_sample_tick hdmi_audio_tx} {
    # BD module references require a Verilog top. These flat boundary modules
    # use Verilog-compatible syntax; their packet/encoding children remain SV.
    set_property file_type Verilog [get_files ${name}.sv]
}
update_compile_order -fileset sources_1
create_bd_design system
set cfg_log [open [file join $out configuration_import.rpt] w]
dict for {name vlnv} $legacy_vlnv {
    if {$name eq "live_osd_0"} {
        set cell [create_bd_cell -type module -reference display_status $name]
    } else {
        set cell [create_bd_cell -type ip -vlnv $vlnv $name]
    }
    set properties [list_property $cell]
    set cfg [list]
    dict for {key value} [dict get $legacy_config $name] {
        if {($name eq "processing_system7_0" && ([regexp {^PCW_[MS]_AXI_.*_FREQMHZ$} $key] || $key eq "PCW_NUM_F2P_INTR_INPUTS")) ||
            ([string match "rst_ps7*" $name] && $key eq "C_EXT_RESET_HIGH")} {
            puts $cfg_log "INFERRED_FROM_CONNECTIONS $name/$key=$value"
            continue
        }
        if {[string match "axi_vdma_*" $name] && $key in {c_prmry_is_aclk_async c_s_axis_s2mm_tdata_width}} {
            puts $cfg_log "INFERRED_FROM_CONNECTIONS $name/$key=$value"
            continue
        }
        if {[lsearch -exact $properties CONFIG.$key]>=0} {
            lappend cfg CONFIG.$key $value
        } else { puts $cfg_log "GENERATED_OR_UNEXPOSED $name/$key=$value" }
    }
    if {[llength $cfg]} {set_property -dict $cfg $cell}
    puts $cfg_log "APPLIED $name [expr {[llength $cfg]/2}] properties"
}
close $cfg_log
set_property CONFIG.NUM_MI 5 [get_bd_cells ps7_0_axi_periph]
set_property -dict [list CONFIG.NUM_OUT_CLKS 3 CONFIG.CLKOUT2_USED true CONFIG.CLKOUT3_USED true \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ 75.000 CONFIG.CLKOUT2_REQUESTED_OUT_FREQ 375.000 \
    CONFIG.CLKOUT3_REQUESTED_OUT_FREQ 150.000 CONFIG.OVERRIDE_MMCM false] [get_bd_cells clk_wiz_0]
create_bd_cell -type module -reference hdmi_audio_tx hdmi_audio_tx_0
create_bd_cell -type module -reference audio_sample_tick audio_sample_tick_0
create_bd_cell -type module -reference pcm_buffer pcm_buffer_0
set_property CONFIG.USE_SAMPLE_ENABLE 1 [get_bd_cells pcm_buffer_0]
connect_legacy
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M04_AXI] [get_bd_intf_pins pcm_buffer_0/s_axi]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins ps7_0_axi_periph/M04_ACLK] [get_bd_pins pcm_buffer_0/s_axi_aclk]
connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins ps7_0_axi_periph/M04_ARESETN] [get_bd_pins pcm_buffer_0/s_axi_aresetn]
foreach {name clock} {rst_pixel clk_out1} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 $name
    connect_bd_net [get_bd_pins clk_wiz_0/$clock] [get_bd_pins $name/slowest_sync_clk]
    connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins $name/ext_reset_in]
    connect_bd_net [get_bd_pins clk_wiz_0/locked] [get_bd_pins $name/dcm_locked]
}
connect_bd_net [get_bd_pins rst_pixel/peripheral_reset] [get_bd_pins hdmi_audio_tx_0/reset]
connect_bd_net [get_bd_pins rst_pixel/peripheral_reset] [get_bd_pins audio_sample_tick_0/reset]
connect_bd_net [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins audio_sample_tick_0/clk_pixel] [get_bd_pins pcm_buffer_0/sample_clk]
connect_bd_net [get_bd_pins audio_sample_tick_0/sample_enable] [get_bd_pins pcm_buffer_0/sample_enable] [get_bd_pins hdmi_audio_tx_0/sample_enable]
connect_bd_net [get_bd_pins pcm_buffer_0/sample_left] [get_bd_pins hdmi_audio_tx_0/sample_left]
connect_bd_net [get_bd_pins pcm_buffer_0/sample_right] [get_bd_pins hdmi_audio_tx_0/sample_right]

foreach entry $legacy_addresses {
    lassign $entry source target offset size
    set space [get_bd_addr_spaces -of_objects [get_bd_intf_pins $source]]
    set segment [get_bd_addr_segs -quiet $target]
    if {![llength $segment] && [string match "live_osd_0/*" $target]} {set segment [get_bd_addr_segs live_osd_0/s_axi/*]}
    if {[llength $space]!=1 || [llength $segment]!=1} {error "Ambiguous legacy address: $entry space=$space segment=$segment"}
    assign_bd_address -offset $offset -range $size -target_address_space $space $segment
}
assign_bd_address -offset 0x43c20000 -range 0x10000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs pcm_buffer_0/s_axi/*]
validate_bd_design
save_bd_design
write_bd_tcl [file join $out reconstructed_bd.tcl]
foreach name [get_bd_cells] {report_property -all $name -file [file join $out [string trimleft $name /]_applied.rpt]}
make_wrapper -files [get_files system.bd] -top
add_files [glob [file join $out project hdmi_audio.gen sources_1 bd system hdl system_wrapper.v]]
set_property top system_wrapper [current_fileset]
add_files -fileset constrs_1 [file join $out pins.xdc]
update_compile_order -fileset sources_1
puts "DISPLAY_AUDIO_BD_READY"
close_project
