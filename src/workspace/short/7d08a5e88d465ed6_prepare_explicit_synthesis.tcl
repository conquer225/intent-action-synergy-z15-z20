# Authorized isolated synthesis preparation only. Never modify the source project.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 1} {error "Usage: prepare_explicit_synthesis.tcl <isolated.xpr>"}
set xpr [file normalize [lindex $argv 0]]
if {![string match "*pl_protocol_explicit_20260928/project/pl_filter_candidate_dma.xpr" $xpr]} {
    error "Refusing non-isolated project: $xpr"
}
open_project $xpr
if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Wrong part"}
set bd [file join [file dirname $xpr] pl_filter_candidate_dma.srcs sources_1 bd filter_candidate filter_candidate.bd]
open_bd_design $bd
foreach name {pf_read_pc pf_write_pc} {
    set cell [get_bd_cells -quiet $name]
    if {[llength $cell] != 1 || [get_property CONFIG.TRANSLATION_MODE $cell] ne "0"} {
        error "Not the explicit-converter candidate: $name"
    }
}
foreach name {pf_memory/s00_couplers/auto_pc pf_memory/s01_couplers/auto_pc} {
    if {[llength [get_bd_cells -quiet $name]]} {error "Original memory converter still present: $name"}
}
set run [get_runs synth_1]
set expected_dir [file normalize [file join [file dirname $xpr] pl_filter_candidate_dma.runs synth_1]]
if {[file normalize [get_property DIRECTORY $run]] ne $expected_dir ||
    [get_property STATUS $run] ne "Out-of-date" ||
    [get_property NEEDS_REFRESH $run] ne "1"} {
    error "Unexpected synthesis run state/directory; refusing reset"
}
set_property AUTO_INCREMENTAL_CHECKPOINT 0 $run
set_property INCREMENTAL_CHECKPOINT {} $run
reset_run synth_1
if {[get_property PROGRESS $run] ne "0%" ||
    [get_property AUTO_INCREMENTAL_CHECKPOINT $run] ne "0" ||
    [get_property INCREMENTAL_CHECKPOINT $run] ne ""} {
    error "Stale incremental result not fully disabled"
}
puts "EXPLICIT_STALE_RUN_RESET_ONLY directory=$expected_dir progress=[get_property PROGRESS $run]"
close_project
