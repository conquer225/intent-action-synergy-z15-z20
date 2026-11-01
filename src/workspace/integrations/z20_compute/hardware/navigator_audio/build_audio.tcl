# Run with Vivado 2023.1: vivado -mode batch -source build_audio.tcl
# Generated project and bitstream stay under build/navigator_audio.
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../..]]
set out [file join $root build navigator_audio]
set vendor [file join $root build reference_sources suchang-ccc__alientek-zynq7020-examples ZYNQ_7020_FPGA 37_audio_loopback rtl]
set vendor_rtl {audio_config.v audio_receive.v audio_send.v i2c_dri.v i2c_reg_cfg.v slave_signal_gen.v}
foreach name $vendor_rtl {
    if {![file isfile [file join $vendor $name]]} {error "Missing pinned vendor audio source: $name"}
}
file mkdir $out
create_project navigator_audio_demo [file join $out project] -part xc7z020clg400-2 -force
set_property target_language Verilog [current_project]
set_property source_mgmt_mode None [current_project]
add_files -norecurse [list [file join $here navigator_audio_demo.v] [file join $here tone_1khz.v]]
foreach name $vendor_rtl {add_files -norecurse [file join $vendor $name]}
add_files -fileset constrs_1 [file join $here navigator_audio.xdc]
set_property top navigator_audio_demo [current_fileset]

# Vendor example 37 uses the same MMCM clock ratio: 50 MHz -> 12.288 MHz.
create_ip -name clk_wiz -vendor xilinx.com -library ip -version 6.0 -module_name clk_wiz_0
set_property -dict [list CONFIG.PRIM_IN_FREQ {50.000} CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {12.288} CONFIG.USE_RESET {true} CONFIG.USE_LOCKED {true}] [get_ips clk_wiz_0]
generate_target all [get_ips clk_wiz_0]

launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {error "Audio synthesis failed"}
set_property STEPS.WRITE_BITSTREAM.ARGS.BIN_FILE true [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Audio implementation failed"}
open_run impl_1
report_timing_summary -file [file join $out timing_summary.rpt]
report_utilization -file [file join $out utilization.rpt]
puts "NAVIGATOR_AUDIO_BITSTREAM=[get_property DIRECTORY [get_runs impl_1]]"
exit
