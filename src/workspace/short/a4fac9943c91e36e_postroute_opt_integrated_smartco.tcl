# One isolated post-route physical-optimization attempt; no bitstream.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set source {D:/ican/codex_project/gli26c/route1/routed.dcp}
set out {D:/ican/codex_project/gli26c/route3}
if {![file isfile $source] || [file exists $out]} {error "Missing routed DCP or output already exists"}
open_checkpoint $source
if {[get_property PART [current_design]] ne "xc7z015clg485-2"} {error "Wrong device"}
foreach cell {guardianloop_bd_i/pf_filter guardianloop_bd_i/pf_dma
              guardianloop_bd_i/axi_dma_0 guardianloop_bd_i/guardianloop_hgb_accel_v0_0} {
    if {[llength [get_cells -quiet $cell]] != 1} {error "Missing coexistence cell: $cell"}
}
set clocks [get_clocks]
if {[llength $clocks] != 1 || [get_property PERIOD $clocks] != 20.0} {error "Wrong clock"}
file mkdir $out
set_param general.maxThreads 4
phys_opt_design -routing_opt
route_design
write_checkpoint [file join $out routed.dcp]
report_route_status -file [file join $out route_status.rpt]
report_utilization -file [file join $out utilization.rpt]
report_clocks -file [file join $out clocks.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -file [file join $out timing_summary.rpt]
report_timing -delay_type max -max_paths 10 -path_type full_clock_expanded -file [file join $out critical_paths.rpt]
report_drc -file [file join $out drc.rpt]
report_methodology -file [file join $out methodology.rpt]
puts "POSTROUTE_OPT_INTEGRATED_SMARTCONNECT_COMPLETE"
close_design
