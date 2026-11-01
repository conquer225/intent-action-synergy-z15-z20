# Generate a candidate bitstream from the audited routed checkpoint only.
# Usage: vivado -mode batch -source generate_isolated_bitstream.tcl -tclargs ROUTED_DCP OUTPUT_DIRECTORY
# This script never opens a hardware target or modifies the source project.
if {[llength $argv] != 2} {error "Expected ROUTED_DCP OUTPUT_DIRECTORY"}
set dcp [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {![file isfile $dcp]} {error "Routed checkpoint not found: $dcp"}
if {[file exists $out]} {error "Output directory must be fresh: $out"}
file mkdir $out

open_checkpoint $dcp
if {[get_property PART [current_design]] ne "xc7z015clg485-2"} {
    error "Unexpected device in routed checkpoint"
}
puts "CHECKPOINT_DESIGN_NAME=[get_property NAME [current_design]]"
foreach cell {filter_candidate_i/pf_axi_sc filter_candidate_i/pf_filter filter_candidate_i/pf_dma} {
    if {[llength [get_cells -quiet $cell]] != 1} {error "Missing expected cell: $cell"}
}
set clocks [get_clocks]
if {[llength $clocks] != 1 || [get_property PERIOD $clocks] != 20.0} {
    error "Expected one 50 MHz clock"
}

report_route_status -file [file join $out route_status.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -file [file join $out timing_summary.rpt]
report_drc -file [file join $out drc.rpt]
report_methodology -file [file join $out methodology.rpt]

set bit [file join $out filter_candidate_wrapper.bit]
write_bitstream $bit
if {![file isfile $bit] || [file size $bit] < 1024} {error "Bitstream missing or unexpectedly small"}
puts "ISOLATED_BITSTREAM_COMPLETE path=$bit bytes=[file size $bit]"
close_design
