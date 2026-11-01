# Recovery path for this Windows host's failed Vivado child launcher.
# Requires completed OOC and top synthesis checkpoints from build_audio.tcl.
set_param general.maxThreads 1
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../..]]
set out [file join $root build navigator_audio]
set runs [file join $out project navigator_audio_demo.runs]
open_checkpoint [file join $runs synth_1 navigator_audio_demo.dcp]
read_checkpoint -cell u_audio/u_clk_wiz [file join $runs clk_wiz_0_synth_1 clk_wiz_0.dcp]
read_xdc [file join $here navigator_audio.xdc]
set blackboxes [get_cells -hier -filter {IS_BLACKBOX == 1}]
puts "AUDIO_BLACKBOX_COUNT=[llength $blackboxes]"
if {[llength $blackboxes] != 0} {error "Unresolved IP: $blackboxes"}
opt_design
place_design
route_design
report_timing_summary -file [file join $out direct_timing_summary.rpt]
report_utilization -file [file join $out direct_utilization.rpt]
write_checkpoint -force [file join $out direct_routed.dcp]
write_bitstream -bin_file -force [file join $out navigator_audio_demo.bit]
puts "AUDIO_BITSTREAM=[file join $out navigator_audio_demo.bit]"
exit
