# Isolated BD topology experiment only. No synthesis/implementation/bitstream.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 1} {error "Usage: stage_explicit_converters.tcl <isolated-project.xpr>"}
set xpr [file normalize [lindex $argv 0]]
if {![string match "*pl_protocol_explicit_20260928/project/pl_filter_candidate_dma.xpr" $xpr]} {
    error "Refusing non-isolated project: $xpr"
}
open_project $xpr
if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Unexpected part"}
set bd [file join [file dirname $xpr] pl_filter_candidate_dma.srcs sources_1 bd filter_candidate filter_candidate.bd]
open_bd_design $bd
foreach {dma_pin memory_pin mode name} {
    pf_dma/M_AXI_MM2S pf_memory/S00_AXI READ_ONLY pf_read_pc
    pf_dma/M_AXI_S2MM pf_memory/S01_AXI WRITE_ONLY pf_write_pc
} {
    if {[llength [get_bd_cells -quiet $name]]} {error "Already staged: $name"}
    set first [get_bd_intf_pins $dma_pin]
    set second [get_bd_intf_pins $memory_pin]
    set net [get_bd_intf_nets -of_objects $first]
    if {[llength $net] != 1 || [get_bd_intf_nets -of_objects $second] ne $net ||
        [llength [get_bd_intf_pins -of_objects $net]] != 2} {
        error "Unexpected existing interface net for $name"
    }
    delete_bd_objs $net
    set pc [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_protocol_converter:* $name]
    set_property -dict [list CONFIG.SI_PROTOCOL AXI4 CONFIG.MI_PROTOCOL AXI3 \
        CONFIG.READ_WRITE_MODE $mode CONFIG.DATA_WIDTH 64 CONFIG.TRANSLATION_MODE 0] $pc
    connect_bd_intf_net $first [get_bd_intf_pins $name/S_AXI]
    connect_bd_intf_net [get_bd_intf_pins $name/M_AXI] $second
    connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $name/aclk]
    connect_bd_net [get_bd_pins pf_shell_reset/peripheral_aresetn] [get_bd_pins $name/aresetn]
    puts "EXPLICIT_PC $name mode=$mode translation=[get_property CONFIG.TRANSLATION_MODE $pc]"
}
validate_bd_design
save_bd_design
foreach name {pf_read_pc pf_write_pc} {
    puts "VALIDATED_PC $name si=[get_property CONFIG.SI_PROTOCOL [get_bd_cells $name]] mi=[get_property CONFIG.MI_PROTOCOL [get_bd_cells $name]] translation=[get_property CONFIG.TRANSLATION_MODE [get_bd_cells $name]]"
}
puts "EXPLICIT_BD_VALIDATED_ONLY part=[get_property PART [current_project]]"
close_project
