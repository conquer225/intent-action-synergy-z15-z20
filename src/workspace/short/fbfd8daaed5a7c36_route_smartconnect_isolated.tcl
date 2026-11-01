# Place/route/report the isolated SmartConnect candidate. Never write bitstream.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set base "D:/ican/codex_project/eeg_apps_z15/output/pl_smartconnect_isolated_20260928"
set xpr [file normalize [file join $base project pl_filter_candidate_dma.xpr]]
set out [file normalize [file join $base route]]
if {[file exists $out]} {error "Preserve previous route evidence: $out"}
open_project -read_only $xpr
if {[get_property NAME [current_project]] ne "pl_filter_candidate_dma" ||
    [get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Wrong project/device"}
set run [get_runs synth_1]
if {![string match "synth_design Complete*" [get_property STATUS $run]] ||
    [get_property NEEDS_REFRESH $run]} {error "No current completed synthesis"}
open_run synth_1
if {[get_property PART [current_design]] ne "xc7z015clg485-2" ||
    [llength [get_cells -quiet filter_candidate_i/pf_axi_sc]] != 1 ||
    [llength [get_cells -quiet filter_candidate_i/pf_filter]] != 1 ||
    [llength [get_cells -quiet filter_candidate_i/pf_dma]] != 1} {error "Unexpected netlist"}
set clocks [get_clocks]
if {[llength $clocks] != 1 || [get_property PERIOD $clocks] != 20.0} {error "Expected one 50 MHz clock"}
file mkdir $out
set_param general.maxThreads 2
opt_design
place_design
phys_opt_design
route_design
write_checkpoint [file join $out routed.dcp]
report_route_status -file [file join $out route_status.rpt]
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -hierarchical_depth 8 -file [file join $out utilization_hierarchical.rpt]
report_clocks -file [file join $out clocks.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -file [file join $out timing_summary.rpt]
report_drc -file [file join $out drc.rpt]
report_methodology -file [file join $out methodology.rpt]
puts "SMARTCONNECT_ROUTE_ONLY_COMPLETE part=[get_property PART [current_design]]"
close_project
