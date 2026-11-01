# Read-only inspection of the remaining LUTAR-1 in the routed isolated DCP.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set checkpoint [file normalize "D:/ican/codex_project/eeg_apps_z15/output/pl_protocol_explicit_20260928/route/routed.dcp"]
if {![string match "*/pl_protocol_explicit_20260928/route/routed.dcp" $checkpoint]} {
    error "Refusing non-isolated checkpoint: $checkpoint"
}
open_checkpoint $checkpoint
set matches [get_cells -hier -quiet -filter {NAME =~ *pf_write_pc* && NAME =~ *curr_fwft_state* && NAME =~ *_i_2}]
if {[llength $matches] != 1} {error "Expected one warning LUT, got [llength $matches]"}
set lut [lindex $matches 0]
puts "WARNING_LUT=$lut REF=[get_property REF_NAME $lut] INIT=[get_property INIT $lut]"
foreach pin [lsort [get_pins -of_objects $lut -filter {DIRECTION == IN}]] {
    set net [get_nets -quiet -of_objects $pin]
    set sources [get_pins -quiet -of_objects $net -filter {DIRECTION == OUT}]
    puts "FANIN pin=$pin net=$net sources=$sources"
    foreach source $sources {
        set cell [get_cells -quiet -of_objects $source]
        puts "SOURCE cell=$cell ref=[get_property REF_NAME $cell]"
    }
}
set out [get_pins -quiet "$lut/O"]
set net [get_nets -quiet -of_objects $out]
puts "OUTPUT net=$net sinks=[llength [get_pins -quiet -of_objects $net -filter {DIRECTION == IN}]]"
foreach sink [lsort [get_pins -quiet -of_objects $net -filter {DIRECTION == IN}]] {
    puts "SINK pin=$sink"
}
close_design
