# Candidate bitstream from the fully routed isolated coexistence checkpoint.
# Does not open Hardware Manager, program the FPGA or touch the formal Overlay.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set source {D:/ican/codex_project/gli26c/route6/routed.dcp}
set out {D:/ican/codex_project/gli26c/bit1}
if {![file isfile $source] || [file exists $out]} {error "Missing routed DCP or output exists"}
open_checkpoint $source
puts "CHECKPOINT_PART=[get_property PART [current_design]] CHECKPOINT_NAME=[get_property NAME [current_design]]"
if {[get_property PART [current_design]] ne "xc7z015clg485-2" ||
    [get_property NAME [current_design]] ni {guardianloop_bd_wrapper checkpoint_routed}} {
    error "Wrong device or top"
}
foreach cell {guardianloop_bd_i/pf_filter guardianloop_bd_i/pf_dma
              guardianloop_bd_i/pf_control guardianloop_bd_i/axi_dma_0
              guardianloop_bd_i/guardianloop_eeg_de_accel_v0_0
              guardianloop_bd_i/guardianloop_eeg_quality_v0_0
              guardianloop_bd_i/guardianloop_hgb_accel_v0_0} {
    if {[llength [get_cells -quiet $cell]] != 1} {error "Missing coexistence cell: $cell"}
}
set clocks [get_clocks]
if {[llength $clocks] != 1 || [get_property PERIOD $clocks] != 20.0} {error "Wrong clock"}
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup] != 1 || [llength $hold] != 1 ||
    [get_property SLACK $setup] < 0.05 || [get_property SLACK $hold] < 0.0} {
    error "Timing guard failed: setup=[get_property SLACK $setup] hold=[get_property SLACK $hold]"
}
file mkdir $out
report_route_status -file [file join $out route_status.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -file [file join $out timing_summary.rpt]
report_drc -file [file join $out drc.rpt]
report_methodology -file [file join $out methodology.rpt]
set fh [open [file join $out route_status.rpt] r]
set route_report [read $fh]
close $fh
if {![regexp {# of nets with routing errors[^\n]*:[[:space:]]*0} $route_report]} {
    error "Routed DCP contains unrouted/error nets"
}
set fh [open [file join $out check_timing.rpt] r]
set check_report [read $fh]
close $fh
if {![string match "*checking no_clock (0)*" $check_report] ||
    ![string match "*checking unconstrained_internal_endpoints (0)*" $check_report]} {
    error "Unconstrained timing endpoints"
}
set fh [open [file join $out drc.rpt] r]
set drc_report [read $fh]
close $fh
if {[regexp {REQP-1839|REQP-1840|PLBUFGOPT|[|][^\n]*[|][[:space:]]*(Error|Critical Warning)[[:space:]]*[|]} $drc_report]} {
    error "Blocking DRC found"
}
set bit [file join $out guardianloop_bd_wrapper.bit]
write_bitstream $bit
if {![file isfile $bit] || [file size $bit] < 1024} {error "Missing/small bitstream"}
puts "INTEGRATED_COEXIST_CANDIDATE_BITSTREAM_READY path=$bit bytes=[file size $bit]"
close_design
