# Compare exact-ratio sample clock semantics against the first routed checkpoint.
# This is read-only timing analysis: it neither changes RTL nor writes a bit.
if {$argc!=2} {error "Usage: audit_routed_clock.tcl ROUTED_DCP NEW_OUTPUT_DIR"}
lassign $argv dcp out
if {[file exists $out]} {error "Refusing existing audit output"}
file mkdir $out
open_checkpoint $dcp
set divreg [get_cells -hier -filter {NAME =~ */audio_sample_clock_0/inst/divided_reg}]
if {[llength $divreg]!=1} {error "Sample divider not uniquely found"}
create_generated_clock -name audio_48k -source [get_pins $divreg/C] -divide_by 3125 -duty_cycle 50.016 [get_pins $divreg/Q]
report_clocks -file [file join $out clocks.rpt]
report_clock_interaction -file [file join $out interaction.rpt]
report_methodology -file [file join $out methodology.rpt]
report_cdc -details -file [file join $out cdc.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $out timing.rpt]
puts "ROUTED_CLOCK_AUDIT_DONE_NO_BIT_WRITTEN"
close_design
