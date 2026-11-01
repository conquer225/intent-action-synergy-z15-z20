# Post-opt guard: a timing-clean design with an unreachable sidecar is invalid.
foreach stem {write_epoch_reg completed_sequence_reg ticks_reg} {
 set cells [get_cells -hier -quiet -filter "NAME =~ *video_observer*$stem* && REF_NAME =~ FD*"]
 puts "OBSERVER_RETAINED_REGISTERS $stem [llength $cells]"
 if {[llength $cells]<64} {error "Video observer $stem optimized away: check AXI crossbar cache and tap connectivity"}
}
puts OBSERVER_NETLIST_PRESENT
