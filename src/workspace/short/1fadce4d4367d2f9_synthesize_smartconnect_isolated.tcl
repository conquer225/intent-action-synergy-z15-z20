# Full candidate synthesis and reports only. No implementation/bitstream/board.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set base "D:/ican/codex_project/eeg_apps_z15/output/pl_smartconnect_isolated_20260928"
set xpr [file normalize [file join $base project pl_filter_candidate_dma.xpr]]
set out [file normalize [file join $base synthesis_reports]]
if {[file exists $out]} {error "Preserve previous synthesis evidence: $out"}
open_project $xpr
if {[get_property NAME [current_project]] ne "pl_filter_candidate_dma" ||
    [get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Wrong project/device"}
set bd [file normalize [file join $base project pl_filter_candidate_dma.srcs sources_1 bd filter_candidate filter_candidate.bd]]
open_bd_design $bd
if {[llength [get_bd_cells -quiet pf_axi_sc]] != 1 ||
    [get_property CONFIG.NUM_SI [get_bd_cells pf_axi_sc]] ne "2" ||
    [get_property CONFIG.NUM_MI [get_bd_cells pf_axi_sc]] ne "1" ||
    [llength [get_bd_cells -quiet pf_memory]] != 0 ||
    [llength [get_bd_cells -quiet pf_write_pc]] != 0} {error "Unexpected memory AXI topology"}
foreach space {pf_dma/Data_MM2S pf_dma/Data_S2MM} {
    set segs [get_bd_addr_segs -quiet -of_objects [get_bd_addr_spaces $space]]
    if {[llength $segs] != 1 || ![string match "*HP0_DDR_LOWOCM" $segs]} {error "DDR mapping wrong for $space: $segs"}
}
validate_bd_design
set run [get_runs synth_1]
set expected_dir [file normalize [file join $base project pl_filter_candidate_dma.runs synth_1]]
if {[file normalize [get_property DIRECTORY $run]] ne $expected_dir} {error "Run directory escapes copy"}
set_property AUTO_INCREMENTAL_CHECKPOINT 0 $run
set_property INCREMENTAL_CHECKPOINT {} $run
reset_run synth_1
if {[get_property PROGRESS $run] ne "0%" ||
    [get_property AUTO_INCREMENTAL_CHECKPOINT $run] ne "0" ||
    [get_property INCREMENTAL_CHECKPOINT $run] ne ""} {error "Stale checkpoint not cleared"}
set_property synth_checkpoint_mode None [get_files $bd]
generate_target all [get_files $bd]
set wrappers [make_wrapper -files [get_files $bd] -top]
add_files -norecurse $wrappers
set_property top filter_candidate_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1
file mkdir $out
set_param general.maxThreads 4
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set status [get_property STATUS $run]
set f [open [file join $out run_status.txt] w]
puts $f $status
close $f
if {![string match "synth_design Complete*" $status]} {error "Synthesis failed: $status"}
open_run synth_1
if {[get_property PART [current_design]] ne "xc7z015clg485-2" ||
    [llength [get_cells -quiet filter_candidate_i/pf_axi_sc]] != 1} {error "Unexpected synthesized design"}
report_utilization -file [file join $out utilization.rpt]
report_clocks -file [file join $out clocks.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -file [file join $out timing_summary.rpt]
report_drc -file [file join $out drc.rpt]
report_methodology -file [file join $out methodology.rpt]
puts "SMARTCONNECT_SYNTHESIS_ONLY_COMPLETE part=[get_property PART [current_design]]"
close_project
