# Alternative physical implementation of the same synthesized coexistence netlist.
# Preserve route1/route3/route4 evidence. No bitstream or board action.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set source {D:/ican/codex_project/gli26c/project/gl_filter_coexist_sc_20260929.xpr}
set out {D:/ican/codex_project/gli26c/route6}
if {![file isfile $source] || [file exists $out]} {error "Missing isolated project or output exists"}
open_project -read_only $source
if {[get_property NAME [current_project]] ne "gl_filter_coexist_sc_20260929" ||
    [get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Wrong project or part"}
set run [get_runs synth_1]
if {![string match "synth_design Complete*" [get_property STATUS $run]] ||
    [get_property NEEDS_REFRESH $run]} {error "Missing current synthesis"}
open_run synth_1
if {[get_property PART [current_design]] ne "xc7z015clg485-2"} {error "Wrong device"}
foreach cell {guardianloop_bd_i/pf_filter guardianloop_bd_i/pf_dma
              guardianloop_bd_i/pf_control guardianloop_bd_i/axi_dma_0
              guardianloop_bd_i/guardianloop_hgb_accel_v0_0} {
    if {[llength [get_cells -quiet $cell]] != 1} {error "Missing coexistence cell: $cell"}
}
set clocks [get_clocks]
if {[llength $clocks] != 1 || [get_property PERIOD $clocks] != 20.0} {error "Wrong clock"}
file mkdir $out
set_param general.maxThreads 4
opt_design
place_design -directive Explore
phys_opt_design -directive AggressiveExplore
route_design -directive Explore
write_checkpoint [file join $out routed.dcp]
report_route_status -file [file join $out route_status.rpt]
report_utilization -file [file join $out utilization.rpt]
report_clocks -file [file join $out clocks.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -file [file join $out timing_summary.rpt]
report_timing -delay_type max -max_paths 10 -path_type full_clock_expanded -file [file join $out critical_paths.rpt]
report_drc -file [file join $out drc.rpt]
report_methodology -file [file join $out methodology.rpt]
puts "EXPLORE_INTEGRATED_SMARTCONNECT_ROUTE_COMPLETE"
close_project
