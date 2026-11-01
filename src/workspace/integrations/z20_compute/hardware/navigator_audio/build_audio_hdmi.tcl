# Audio plus HDMI peak bar, independent of the stereo/NPU image.
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../..]]
set out [file join $root build navigator_audio_hdmi]
set vendor_root [file join $root build reference_sources suchang-ccc__alientek-zynq7020-examples ZYNQ_7020_FPGA]
set audio_vendor [file join $vendor_root 37_audio_loopback rtl]
set video_vendor [file join $vendor_root 23_hdmi_colorbar rtl]
set audio_rtl {audio_config.v audio_receive.v audio_send.v i2c_dri.v i2c_reg_cfg.v slave_signal_gen.v}
set video_rtl {asyn_rst_syn.v dvi_encoder.v dvi_transmitter_top.v serializer_10_to_1.v video_driver.v}
foreach name $audio_rtl {if {![file isfile [file join $audio_vendor $name]]} {error "Missing audio source: $name"}}
foreach name $video_rtl {if {![file isfile [file join $video_vendor $name]]} {error "Missing video source: $name"}}
file mkdir $out
create_project navigator_audio_hdmi [file join $out project] -part xc7z020clg400-2 -force
set_property target_language Verilog [current_project]
set_property source_mgmt_mode None [current_project]
foreach name {navigator_audio_demo.v navigator_audio_hdmi.v tone_1khz.v audio_meter_cdc.v audio_level_display.v} {
    add_files -norecurse [file join $here $name]
}
foreach name $audio_rtl {add_files -norecurse [file join $audio_vendor $name]}
foreach name $video_rtl {add_files -norecurse [file join $video_vendor $name]}
add_files -fileset constrs_1 [list [file join $here navigator_audio.xdc] [file join $here navigator_audio_hdmi.xdc]]
set_property top navigator_audio_hdmi [current_fileset]
create_ip -name clk_wiz -vendor xilinx.com -library ip -version 6.0 -module_name clk_wiz_0
set_property -dict [list CONFIG.PRIM_IN_FREQ {50.000} CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {12.288} CONFIG.USE_RESET {true} CONFIG.USE_LOCKED {true}] [get_ips clk_wiz_0]
create_ip -name clk_wiz -vendor xilinx.com -library ip -version 6.0 -module_name clk_wiz_video
set_property -dict [list CONFIG.PRIM_IN_FREQ {50.000} CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {75.000} CONFIG.CLKOUT2_USED {true} CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {375.000} CONFIG.USE_RESET {true} CONFIG.USE_LOCKED {true}] [get_ips clk_wiz_video]
generate_target all [get_ips clk_wiz_0 clk_wiz_video]
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {error "Audio/HDMI synthesis failed"}
set_property STEPS.WRITE_BITSTREAM.ARGS.BIN_FILE true [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Audio/HDMI implementation failed"}
open_run impl_1
report_timing_summary -file [file join $out timing_summary.rpt]
report_utilization -file [file join $out utilization.rpt]
puts "NAVIGATOR_AUDIO_HDMI_BITSTREAM=[get_property DIRECTORY [get_runs impl_1]]"
exit
