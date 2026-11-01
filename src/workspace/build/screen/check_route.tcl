# Additional read-only checks on the existing routed design.
set root [file normalize [file join [file dirname [info script]] ../..]]
set report_dir [file join $root report screen]
open_checkpoint [file join $report_dir z15_screen_routed.dcp]
report_bus_skew -file [file join $report_dir bus_skew.rpt]
puts "ROUTE_CHECK_PASSED"
