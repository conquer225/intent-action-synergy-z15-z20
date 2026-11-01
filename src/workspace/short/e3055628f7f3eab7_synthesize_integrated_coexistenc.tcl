# Vivado 2025.2: synthesize only the isolated Z15 coexistence candidate.
# No implementation, bitstream, Hardware Manager or board access.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set xpr {D:/ican/codex_project/gli26b/project/gl_filter_coexist_20260929.xpr}
set out {D:/ican/codex_project/gli26b/synth1}
if {![file isfile $xpr] || [file exists $out]} {error "Missing isolated project or output already exists"}
open_project $xpr
if {[get_property NAME [current_project]] ne "gl_filter_coexist_20260929" ||
    [get_property PART [current_project]] ne "xc7z015clg485-2" ||
    [get_property top [current_fileset]] ne "guardianloop_bd_wrapper"} {
    error "Unexpected project, device or top"
}
set bd_files [get_files -filter {FILE_TYPE == "Block Designs"}]
if {[llength $bd_files] != 1} {error "Expected one coexistence BD"}
set bd [lindex $bd_files 0]
open_bd_design $bd
foreach cell {processing_system7_0 axi_dma_0 guardianloop_eeg_de_accel_v0_0
              guardianloop_eeg_quality_v0_0 guardianloop_hgb_accel_v0_0
              pf_dma pf_filter pf_control pf_read_pc pf_write_pc} {
    if {[llength [get_bd_cells -quiet $cell]] != 1} {error "Missing coexistence cell: $cell"}
}
if {[get_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells processing_system7_0]] != 50.0} {
    error "Expected PS FCLK0 at 50 MHz"
}
validate_bd_design
set run [get_runs synth_1]
if {[get_property PROGRESS $run] ne "0%"} {error "Synthesis was already started; preserve prior run"}
file mkdir $out
set_property synth_checkpoint_mode None $bd
set_param general.maxThreads 4
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set status [get_property STATUS $run]
set fh [open [file join $out run_status.txt] w]
puts $fh $status
close $fh
if {![string match "synth_design Complete*" $status]} {error "Synthesis failed: $status"}
open_run synth_1
if {[get_property PART [current_design]] ne "xc7z015clg485-2"} {error "Wrong synthesized part"}
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -hierarchical_depth 8 -file [file join $out utilization_hierarchical.rpt]
report_clocks -file [file join $out clocks.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -file [file join $out timing_summary.rpt]
report_timing -delay_type max -max_paths 10 -path_type full_clock_expanded -file [file join $out critical_paths.rpt]
report_drc -file [file join $out drc.rpt]
set fh [open [file join $out metrics.txt] w]
puts $fh "tool=[version -short] part=[get_property PART [current_design]] scope=post_synthesis_only"
foreach clock [get_clocks] {
    puts $fh "clock=[get_property NAME $clock] period_ns=[get_property PERIOD $clock]"
}
foreach path [get_timing_paths -delay_type max -max_paths 10] {
    puts $fh "slack=[get_property SLACK $path] start=[get_property STARTPOINT_PIN $path] end=[get_property ENDPOINT_PIN $path]"
}
close $fh
if {[llength [get_clocks]] == 0 || [llength [get_timing_paths -max_paths 1]] == 0} {
    error "Synthesis lacks constrained timing paths"
}
puts "INTEGRATED_COEXIST_SYNTHESIS_COMPLETE_ONLY"
close_project
