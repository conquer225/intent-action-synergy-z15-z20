# Read-only project probe. BD edits are intentionally not saved.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 1} {error "Usage: probe_explicit_converter.tcl <isolated-project.xpr>"}
set xpr [file normalize [lindex $argv 0]]
if {![string match "*pl_protocol_unprotected_isolated_20260928/project/pl_filter_candidate_dma.xpr" $xpr]} {
    error "Refusing non-isolated project: $xpr"
}
open_project $xpr
open_bd_design [file join [file dirname $xpr] pl_filter_candidate_dma.srcs sources_1 bd filter_candidate filter_candidate.bd]
set pc [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_protocol_converter:* pf_probe_pc]
puts "PC_PROPERTIES [list_property $pc]"
puts "PC_PINS [get_bd_pins -of_objects $pc]"
puts "PC_INTERFACES [get_bd_intf_pins -of_objects $pc]"
foreach property {CONFIG.SI_PROTOCOL CONFIG.MI_PROTOCOL CONFIG.DATA_WIDTH CONFIG.TRANSLATION_MODE} {
    puts "PC_DEFAULT $property=[get_property $property $pc]"
}
close_project
