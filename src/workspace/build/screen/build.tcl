source [file join [file dirname [info script]] create_project.tcl]
set report_dir [file join $root report screen]
file mkdir $report_dir
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed"}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation failed"}
open_run impl_1
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $report_dir timing.rpt]
report_utilization -file [file join $report_dir utilization.rpt]
report_drc -file [file join $report_dir drc.rpt]
report_cdc -details -file [file join $report_dir cdc.rpt]
report_clock_interaction -file [file join $report_dir clocks.rpt]
report_bus_skew -file [file join $report_dir bus_skew.rpt]
if {[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]] < 0} {error "Setup timing failed"}
if {[get_property SLACK [get_timing_paths -delay_type min -max_paths 1]] < 0} {error "Hold timing failed"}
file copy -force [file join $out z15_screen.runs impl_1 z15_screen_top.bit] [file join $report_dir z15_screen_top.bit]
write_checkpoint -force [file join $report_dir z15_screen_routed.dcp]
puts [exec python [file join $root tools screen_manifest.py] --record]
puts "BUILD_PASSED"
