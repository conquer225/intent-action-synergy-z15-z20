# Authorised offline synthesis/place/route/bit generation. No board programming.
if {$argc != 1} {error "Usage: implement_display.tcl CANDIDATE_PROJECT_DIR"}
set out [file normalize [lindex $argv 0]]
open_project [file join $out project hdmi_audio.xpr]
set bd [get_files system.bd]
generate_target all $bd
set_property SYNTH_CHECKPOINT_MODE None $bd
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%" || [string match "*ERROR*" [get_property STATUS [get_runs synth_1]]]} {error "Full synthesis did not complete"}
open_run synth_1
report_utilization -file [file join $out full_synth_utilization.rpt]
report_drc -file [file join $out full_synth_drc.rpt]
close_design
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {![string match "*route_design Complete*" [get_property STATUS [get_runs impl_1]]]} {error "Full implementation did not complete: [get_property STATUS [get_runs impl_1]]"}
open_run impl_1
report_clocks -file [file join $out clocks.rpt]
report_clock_interaction -file [file join $out clock_interaction.rpt]
report_cdc -details -file [file join $out cdc.rpt]
report_methodology -file [file join $out methodology.rpt]
report_bus_skew -file [file join $out bus_skew.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $out timing.rpt]
report_drc -file [file join $out drc.rpt]
report_io -file [file join $out io.rpt]
report_utilization -file [file join $out utilization.rpt]
write_checkpoint [file join $out routed.dcp]
set f [open [file join $out methodology.rpt] r]
set methodology [read $f]
close $f
if {[regexp -line {^\|[^|]+\|[ ]*(Critical Warning|Error)[ ]*\|} $methodology]} {
    error "Unresolved critical methodology findings; no bitstream generated"
}
set f [open [file join $out cdc.rpt] r]
set cdc [read $f]
close $f
if {[regexp -line {^CDC-[0-9]+[ ]+Critical[ ]+[1-9][0-9]*[ ]} $cdc]} {
    error "Unreviewed critical CDC findings; no bitstream generated"
}
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {![llength $setup] || ![llength $hold]} {error "Missing timing paths"}
if {[get_property SLACK $setup] < 0 || [get_property SLACK $hold] < 0} {error "Timing failed; no bitstream generated"}
set critical [get_drc_violations -filter {SEVERITY == "Error" || SEVERITY == "Critical Warning"}]
if {[llength $critical]} {error "Unresolved critical DRC; no bitstream generated: $critical"}
set candidate [file join $out candidate]
file mkdir $candidate
write_bitstream [file join $candidate guardianloop_display_audio.bit]
file copy [file join $out project hdmi_audio.gen sources_1 bd system hw_handoff system.hwh] [file join $candidate guardianloop_display_audio.hwh]
puts "DISPLAY_AUDIO_CANDIDATE_BUILT_NOT_LOADED"
close_project
