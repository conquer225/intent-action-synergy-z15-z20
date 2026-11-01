# Isolated pipelined candidate synthesis ONLY. No bitstream or board commands.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required; no fallback"}
if {$argc != 2} {error "Usage: synthesize_candidate.tcl <isolated.xpr> <new-report-dir>"}
set project_file [file normalize [lindex $argv 0]]
set report_dir [file normalize [lindex $argv 1]]
if {[file exists $report_dir]} {error "Report directory exists; preserve prior evidence"}
if {[file tail [file dirname [file dirname $project_file]]] ne "pl_pipeline_build_v2025_2_20260927"} {
    error "Only the isolated copied project is authorized"
}
open_project $project_file
if {[get_property NAME [current_project]] ne "pl_filter_candidate_dma" ||
    [get_property PART [current_project]] ne "xc7z015clg485-2"} {
    error "Unexpected candidate project/device"
}
set bd [get_files */filter_candidate.bd]
if {[llength $bd]!=1} {error "Expected isolated filter_candidate BD"}
set run [get_runs synth_1]
set source [file normalize [file join [file dirname [info script]] primary_sos_core.sv]]
if {[llength [get_files -quiet $source]] != 1} {
    error "The copied project must use the isolated pipelined core"
}
reset_run synth_1
if {[get_property PROGRESS $run] ne "0%"} {error "Copied synthesis run was not reset"}
file mkdir $report_dir
set_param general.maxThreads 4
open_bd_design $bd
validate_bd_design
set rst [get_bd_cells pf_shell_reset]
foreach key {C_EXT_RESET_HIGH C_AUX_RESET_HIGH} {
    if {[get_property CONFIG.$key $rst] != 0} {error "Unexpected reset polarity: $key"}
}
foreach {pin constant value} {
    pf_shell_reset/aux_reset_in pf_shell_one 1
    pf_shell_reset/dcm_locked pf_shell_one 1
    pf_shell_reset/mb_debug_sys_rst pf_shell_zero 0
} {
    if {[get_property CONFIG.CONST_VAL [get_bd_cells $constant]] != $value ||
        [get_bd_nets -of_objects [get_bd_pins $pin]] ne
        [get_bd_nets -of_objects [get_bd_pins $constant/dout]]} {
        error "Unsafe reset tie-off: $pin"
    }
}
# Global synthesis includes DMA/interconnect/PS wrapper; avoids a filter-only resource claim.
set_property synth_checkpoint_mode None $bd
generate_target all $bd
set wrappers [make_wrapper -files $bd -top]
add_files -norecurse $wrappers
set_property top filter_candidate_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set run_status [get_property STATUS $run]
set f [open [file join $report_dir run_status.txt] w]
puts $f $run_status
close $f
if {![string match "synth_design Complete*" $run_status]} {error "Synthesis not complete: $run_status"}
open_run synth_1
report_utilization -file [file join $report_dir utilization.rpt]
report_utilization -hierarchical -hierarchical_depth 8 -file [file join $report_dir utilization_hierarchical.rpt]
report_clocks -file [file join $report_dir clocks.rpt]
check_timing -verbose -file [file join $report_dir check_timing.rpt]
report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -file [file join $report_dir timing_summary.rpt]
report_timing -delay_type max -max_paths 10 -path_type full_clock_expanded -file [file join $report_dir critical_paths.rpt]
report_drc -file [file join $report_dir drc.rpt]
set f [open [file join $report_dir timing_metrics.txt] w]
puts $f "tool_version=[version -short]"
puts $f "scope=post_synthesis_estimate_not_placed_or_routed"
puts $f "part=[get_property PART [current_project]]"
puts $f "clock_count=[llength [get_clocks]]"
foreach clk [get_clocks] {puts $f "clock=[get_property NAME $clk] period_ns=[get_property PERIOD $clk]"}
set paths [get_timing_paths -delay_type max -max_paths 10]
foreach path $paths {
    foreach prop {SLACK DATAPATH_DELAY STARTPOINT_PIN ENDPOINT_PIN LOGIC_LEVELS} {
        puts $f "$prop=[get_property $prop $path]"
    }
}
close $f
if {[llength [get_clocks]]==0 || [llength $paths]==0} {error "No constrained timing paths; timing result invalid"}
puts "PRIMARY_PIPELINE_SYNTHESIS_ONLY_COMPLETE"
close_project
exit
