# Generate HDL only for the fresh isolated direct-SmartConnect coexistence BD.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set project {D:/ican/codex_project/gli26c/project/gl_filter_coexist_sc_20260929.xpr}
if {![file isfile $project]} {error "Missing isolated project"}
open_project $project
if {[get_property NAME [current_project]] ne "gl_filter_coexist_sc_20260929" ||
    [get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Wrong project or part"}
set bds [get_files -filter {FILE_TYPE == "Block Designs"}]
if {[llength $bds] != 1} {error "Expected one block design"}
set bd [lindex $bds 0]
open_bd_design $bd
validate_bd_design
generate_target all $bd
set wrapper [make_wrapper -files $bd -top]
if {[llength $wrapper] != 1} {error "Expected one wrapper"}
add_files -norecurse $wrapper
set_property top guardianloop_bd_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "INTEGRATED_SMARTCONNECT_WRAPPER_READY: $wrapper"
close_project
