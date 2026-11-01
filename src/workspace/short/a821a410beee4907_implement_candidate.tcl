# Authorized implementation validation only. No bitstream or hardware commands.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 2} {error "Usage: implement_candidate.tcl synthesized.dcp new-output-dir"}
set dcp [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} {error "Output already exists; preserve evidence"}
file mkdir $out
set_param general.maxThreads 4
# The synthesis DCP alone omits project-applied implementation XDC (PS clock).
# Open the saved project read-only so open_run applies its original IP constraints.
set project_dir [file dirname [file dirname [file dirname $dcp]]]
open_project -read_only [file join $project_dir pl_filter_candidate_dma.xpr]
if {[get_property NAME [current_project]] ne "pl_filter_candidate_dma" ||
    [get_property STATUS [get_runs synth_1]] ne "synth_design Complete!" ||
    [get_property NEEDS_REFRESH [get_runs synth_1]]} {
    error "Expected completed, current candidate synthesis"
}
open_run synth_1
if {[get_property PART [current_design]] ne "xc7z015clg485-2" ||
    [llength [get_cells -quiet filter_candidate_i/pf_filter]] != 1 ||
    [llength [get_cells -quiet filter_candidate_i/pf_dma]] != 1} {
    error "Unexpected design/device"
}
set clocks [get_clocks]
if {[llength $clocks] != 1 || [get_property PERIOD $clocks] != 20.0} {
    error "Expected one 50 MHz clock"
}
opt_design
place_design
phys_opt_design
route_design
write_checkpoint [file join $out routed.dcp]
report_route_status -file [file join $out route_status.rpt]
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -hierarchical_depth 8 -file [file join $out utilization_hierarchical.rpt]
report_clocks -file [file join $out clocks.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -file [file join $out timing_summary.rpt]
report_timing -delay_type max -max_paths 10 -path_type full_clock_expanded -file [file join $out critical_paths.rpt]
report_drc -file [file join $out drc.rpt]
report_methodology -file [file join $out methodology.rpt]
set f [open [file join $out timing_metrics.txt] w]
puts $f "tool_version=[version -short]"
puts $f "scope=post_route_not_hardware_measurement"
puts $f "part=[get_property PART [current_design]]"
foreach mode {max min} {
    puts $f "delay_type=$mode"
    foreach path [get_timing_paths -delay_type $mode -max_paths 10] {
        foreach prop {SLACK DATAPATH_DELAY STARTPOINT_PIN ENDPOINT_PIN LOGIC_LEVELS} {
            puts $f "$prop=[get_property $prop $path]"
        }
    }
}
close $f
puts "PRIMARY_FILTER_ROUTE_ONLY_COMPLETE"
close_project
exit
