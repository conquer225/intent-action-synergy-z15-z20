if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 1} {error "Usage: inspect_explicit_run.tcl <isolated.xpr>"}
set xpr [file normalize [lindex $argv 0]]
if {![string match "*pl_protocol_explicit_20260928/project/pl_filter_candidate_dma.xpr" $xpr]} {error "Refusing non-isolated project"}
open_project -read_only $xpr
puts "PROJECT=[get_property DIRECTORY [current_project]] PART=[get_property PART [current_project]]"
set run [get_runs synth_1]
foreach prop {DIRECTORY STATUS PROGRESS NEEDS_REFRESH AUTO_INCREMENTAL_CHECKPOINT INCREMENTAL_CHECKPOINT} {
    puts "SYNTH_$prop=[get_property $prop $run]"
}
puts "IMPL_STATUS=[get_property STATUS [get_runs impl_1]]"
close_project
