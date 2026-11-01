# Historical negative probe only: Vivado 2025.2 rejects set_property on
# pf_memory/*/auto_pc with BD 41-738 (managed appcore). It stages nothing.
# Kept to reproduce that limitation; do not use it as a DRC remedy.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 1} {error "Usage: stage_unprotected_converter.tcl <isolated-project.xpr>"}
set xpr [file normalize [lindex $argv 0]]
if {![string match "*pl_protocol_unprotected_isolated_20260928/project/pl_filter_candidate_dma.xpr" $xpr]} {
    error "Refusing non-isolated project: $xpr"
}
open_project $xpr
if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Unexpected part"}
set bd [file normalize [file join [file dirname $xpr] pl_filter_candidate_dma.srcs sources_1 bd filter_candidate filter_candidate.bd]]
open_bd_design $bd
foreach name {pf_memory/s00_couplers/auto_pc pf_memory/s01_couplers/auto_pc} {
    set cell [get_bd_cells -quiet $name]
    if {[llength $cell] != 1} {error "Converter not accessible in isolated BD: $name"}
    set before [get_property CONFIG.TRANSLATION_MODE $cell]
    if {$before ne "2"} {error "Unexpected initial translation mode $name=$before"}
    set_property CONFIG.TRANSLATION_MODE 0 $cell
    puts "STAGED_CONVERTER $name old=$before new=[get_property CONFIG.TRANSLATION_MODE $cell]"
}
validate_bd_design
save_bd_design
puts "ISOLATED_BD_VALIDATED_ONLY part=[get_property PART [current_project]]"
close_project
