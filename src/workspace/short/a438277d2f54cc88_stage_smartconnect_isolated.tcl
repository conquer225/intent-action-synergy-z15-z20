# Replace only the two explicit protocol converters in a copied candidate BD.
# No synthesis, implementation, bitstream generation, or board access here.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set xpr [file normalize "D:/ican/codex_project/eeg_apps_z15/output/pl_smartconnect_isolated_20260928/project/pl_filter_candidate_dma.xpr"]
if {![string match "*/pl_smartconnect_isolated_20260928/project/pl_filter_candidate_dma.xpr" $xpr]} {error "Unexpected project"}
open_project $xpr
if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Unexpected part"}
set bd [file join [file dirname $xpr] pl_filter_candidate_dma.srcs sources_1 bd filter_candidate filter_candidate.bd]
open_bd_design $bd
foreach {old name dma_pin memory_pin} {
    pf_read_pc pf_read_sc pf_dma/M_AXI_MM2S pf_memory/S00_AXI
    pf_write_pc pf_write_sc pf_dma/M_AXI_S2MM pf_memory/S01_AXI
} {
    if {![llength [get_bd_cells -quiet $old]] || [llength [get_bd_cells -quiet $name]]} {
        error "Unexpected converter state for $name"
    }
    set dma [get_bd_intf_pins $dma_pin]
    set memory [get_bd_intf_pins $memory_pin]
    set si [get_bd_intf_pins $old/S_AXI]
    set mi [get_bd_intf_pins $old/M_AXI]
    set upstream [get_bd_intf_nets -of_objects $dma]
    set downstream [get_bd_intf_nets -of_objects $memory]
    if {[llength $upstream] != 1 || [llength $downstream] != 1 ||
        [get_bd_intf_nets -of_objects $si] ne $upstream ||
        [get_bd_intf_nets -of_objects $mi] ne $downstream} {
        error "Unexpected AXI chain for $old"
    }
    delete_bd_objs [get_bd_cells $old]
    set sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:* $name]
    set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 1] $sc
    connect_bd_intf_net $dma [get_bd_intf_pins $name/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins $name/M00_AXI] $memory
    connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $name/aclk]
    connect_bd_net [get_bd_pins pf_shell_reset/peripheral_aresetn] [get_bd_pins $name/aresetn]
    puts "STAGED_SMARTCONNECT $name SI=$dma_pin MI=$memory_pin"
}
validate_bd_design
save_bd_design
foreach name {pf_read_sc pf_write_sc} {
    puts "VALIDATED_SMARTCONNECT $name SI=[get_property CONFIG.NUM_SI [get_bd_cells $name]] MI=[get_property CONFIG.NUM_MI [get_bd_cells $name]]"
}
puts "SMARTCONNECT_BD_VALIDATED_ONLY part=[get_property PART [current_project]]"
close_project
