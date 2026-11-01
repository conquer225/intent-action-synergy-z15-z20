# Post-route physical optimization only; no RTL, XDC, bitstream or board changes.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 2} {error "Usage: optimize_routed_candidate.tcl routed.dcp new-output-dir"}
set dcp [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} {error "Output exists; preserve prior evidence"}
file mkdir $out
set_param general.maxThreads 1
open_checkpoint $dcp
if {[get_property PART [current_design]] ne "xc7z015clg485-2" ||
    [llength [get_cells -quiet filter_candidate_i/pf_filter]] != 1} {
    error "Unexpected candidate device/hierarchy"
}
set clocks [get_clocks]
if {[llength $clocks] != 1 || [get_property PERIOD $clocks] != 20.0} {
    error "Expected inherited 50 MHz clock; never recreate a missing constraint"
}
report_timing_summary -delay_type min_max -file [file join $out before_timing.rpt]
report_route_status -file [file join $out before_route.rpt]
phys_opt_design -directive Explore
write_checkpoint [file join $out post_physopt.dcp]
report_route_status -file [file join $out post_physopt_route.rpt]
set route_file [open [file join $out post_physopt_route.rpt] r]
set route_text [read $route_file]
close $route_file
if {![regexp {# of routable nets\.+\s*:\s*(\d+)} $route_text -> routable] ||
    ![regexp {# of fully routed nets\.+\s*:\s*(\d+)} $route_text -> routed] ||
    ![regexp {# of nets with routing errors\.+\s*:\s*(\d+)} $route_text -> errors]} {
    error "Cannot establish post-physical-optimization routing completeness"
}
if {$routable != $routed || $errors != 0} {
    route_design
} else {
    puts "POST_PHYSOPT_ALREADY_FULLY_ROUTED: no additional route_design required"
}
write_checkpoint [file join $out routed.dcp]
report_route_status -file [file join $out route_status.rpt]
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -hierarchical_depth 8 -file [file join $out utilization_hierarchical.rpt]
report_clocks -file [file join $out clocks.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -significant_digits 6 -file [file join $out timing_summary.rpt]
report_timing -delay_type max -max_paths 10 -path_type full_clock_expanded -significant_digits 6 -file [file join $out critical_paths.rpt]
report_drc -file [file join $out drc.rpt]
report_methodology -file [file join $out methodology.rpt]
set f [open [file join $out timing_metrics.txt] w]
puts $f "tool_version=[version -short]"
puts $f "scope=post_route_physical_optimization_not_hardware_measurement"
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
puts "PRIMARY_FILTER_POST_ROUTE_OPT_COMPLETE"
close_design
exit
