# Inspect saved isolated BD without launching any design run.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 1} {error "Usage: audit_explicit_converters.tcl <isolated-project.xpr>"}
set xpr [file normalize [lindex $argv 0]]
if {![string match "*pl_protocol_explicit_20260928/project/pl_filter_candidate_dma.xpr" $xpr]} {
    error "Refusing non-isolated project: $xpr"
}
open_project $xpr
if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Unexpected part"}
open_bd_design [file join [file dirname $xpr] pl_filter_candidate_dma.srcs sources_1 bd filter_candidate filter_candidate.bd]
set dma [get_bd_cells pf_dma]
foreach property {CONFIG.c_mm2s_burst_size CONFIG.c_s2mm_burst_size} {
    set beats [get_property $property $dma]
    if {$beats ne "16"} {error "Unprotected converter precondition broken: $property=$beats"}
    puts "DMA_BURST_LIMIT $property=$beats"
}
foreach property {CONFIG.c_m_axi_mm2s_data_width CONFIG.c_m_axi_s2mm_data_width} {
    set width [get_property $property $dma]
    if {$width ne "64"} {error "Unexpected AXI width: $property=$width"}
    puts "DMA_AXI_WIDTH $property=$width"
}
foreach name {pf_read_pc pf_write_pc pf_memory/s00_couplers/auto_pc pf_memory/s01_couplers/auto_pc pf_memory/m00_couplers/auto_pc} {
    set cell [get_bd_cells -quiet $name]
    if {[llength $cell] == 0} {
        puts "CONVERTER_ABSENT $name"
    } else {
        if {$name in {pf_read_pc pf_write_pc} &&
            ([get_property CONFIG.TRANSLATION_MODE $cell] ne "0" ||
             [get_property CONFIG.SI_PROTOCOL $cell] ne "AXI4" ||
             [get_property CONFIG.MI_PROTOCOL $cell] ne "AXI3")} {
            error "Explicit converter configuration invalid: $name"
        }
        if {[string match "pf_memory/*" $name]} {error "Automatic converter still present: $name"}
        puts "CONVERTER_PRESENT $name translation=[get_property CONFIG.TRANSLATION_MODE $cell] si=[get_property CONFIG.SI_PROTOCOL $cell] mi=[get_property CONFIG.MI_PROTOCOL $cell]"
    }
}
close_project
