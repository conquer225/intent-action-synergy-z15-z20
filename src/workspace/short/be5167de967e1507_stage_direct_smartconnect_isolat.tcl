# Convert the failed 1x1-SmartConnect + legacy interconnect experiment into
# a supported endpoint-to-endpoint 2x1 SmartConnect inside the same copy.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set xpr [file normalize "D:/ican/codex_project/eeg_apps_z15/output/pl_smartconnect_isolated_20260928/project/pl_filter_candidate_dma.xpr"]
if {![string match "*/pl_smartconnect_isolated_20260928/project/pl_filter_candidate_dma.xpr" $xpr]} {error "Unexpected project"}
open_project $xpr
if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Unexpected part"}
open_bd_design [file join [file dirname $xpr] pl_filter_candidate_dma.srcs sources_1 bd filter_candidate filter_candidate.bd]
foreach name {pf_read_sc pf_write_sc pf_memory} {
    if {![llength [get_bd_cells -quiet $name]]} {error "Expected staged cell missing: $name"}
}
if {[llength [get_bd_cells -quiet pf_axi_sc]]} {error "Direct SmartConnect already staged"}
foreach name {pf_read_sc pf_write_sc pf_memory} {
    delete_bd_objs [get_bd_cells $name]
}
set sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:* pf_axi_sc]
set_property -dict [list CONFIG.NUM_SI 2 CONFIG.NUM_MI 1] $sc
connect_bd_intf_net [get_bd_intf_pins pf_dma/M_AXI_MM2S] [get_bd_intf_pins pf_axi_sc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins pf_dma/M_AXI_S2MM] [get_bd_intf_pins pf_axi_sc/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins pf_axi_sc/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP0]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins pf_axi_sc/aclk]
connect_bd_net [get_bd_pins pf_shell_reset/peripheral_aresetn] [get_bd_pins pf_axi_sc/aresetn]
assign_bd_address
validate_bd_design
set target [get_bd_addr_segs -quiet processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM]
if {[llength $target] != 1} {error "HP0 DDR segment missing"}
foreach space {pf_dma/Data_MM2S pf_dma/Data_S2MM} {
    set mappings [get_bd_addr_segs -quiet -of_objects [get_bd_addr_spaces $space]]
    if {[llength $mappings] == 0} {error "No DDR mapping for $space"}
    puts "DDR_MAPPING $space mappings=$mappings"
}
save_bd_design
puts "DIRECT_SMARTCONNECT_BD_VALIDATED_ONLY part=[get_property PART [current_project]]"
close_project
