set work [file normalize [file dirname [info script]]]
set output [file join $work vivado_ooc_v2]
open_checkpoint [file join $output synth.dcp]
opt_design
place_design
phys_opt_design
route_design
report_utilization -file [file join $output routed_utilization.rpt]
report_timing_summary -file [file join $output routed_timing.rpt]
report_drc -file [file join $output routed_drc.rpt]
write_checkpoint -force [file join $output routed.dcp]
exit
