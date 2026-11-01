if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 2} {error "Usage: export_full_chain_sim.tcl <isolated.xpr> <new-output>"}
set root [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} {error "Preserve previous evidence; output already exists"}
open_project $root
if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Wrong candidate part"}
set here [file dirname [info script]]
set core [file normalize [file join $here primary_sos_core.sv]]
if {[llength [get_files -quiet $core]]!=1} {error "Expected pipelined candidate filter core"}
set bd [file normalize [file join [file dirname $root] pl_filter_candidate_dma.srcs sources_1 bd filter_candidate filter_candidate.bd]]
if {[llength [get_files -quiet $bd]]!=1} {error "Expected candidate block design"}
generate_target simulation [get_files $bd]
set tb [file normalize [file join $here full_chain_reset_tb.sv]]
add_files -fileset sim_1 $tb
set_property top full_chain_reset_tb [get_filesets sim_1]
update_compile_order -fileset sim_1
file mkdir $out
export_simulation -simulator xsim -directory $out -force
set golden [file normalize [file join $here .. output pl_primary_filter_q31_20260927]]
foreach name {vectors.txt coeff.hex} {file copy -force [file join $golden $name] [file join $out xsim $name]}
puts "FULL_CHAIN_EXPORT_ONLY tool=[version -short] part=[get_property PART [current_project]]"
close_project
