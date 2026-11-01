set root [file normalize [file join [file dirname [info script]] ..]]
set out $root/build/stereo_implementation
open_checkpoint $out/system_wrapper_routed.dcp
report_clocks -file $out/clocks-before.rpt
source $root/hardware/fix_stereo_clock.tcl
report_clocks -file $out/clocks.rpt
report_timing_summary -report_unconstrained -file $out/timing.rpt
report_methodology -file $out/methodology.rpt
set f [open $out/methodology.rpt];set rules [read $f];close $f
if {[regexp {TIMING-(4|27)#[0-9]} $rules]} {error "Invalid clock tree remains"}
foreach type {max min} {
 set path [get_timing_paths -delay_type $type -max_paths 1]
 if {![llength $path] || [get_property SLACK $path]<0} {error "Corrected clock timing failed: $type"}
}
report_drc -file $out/drc.rpt
if {[llength [get_drc_violations -filter {SEVERITY == Error}]]} {error "DRC errors"}
source $root/hardware/check_video_observer_presence.tcl
write_checkpoint -force $out/system_wrapper_routed.dcp
write_bitstream -force $out/system_wrapper.bit
puts STEREO_CLOCK_TREE_VALIDATED
exit
