# Generate HDL sources only in the already isolated coexistence project.
# No synthesis, implementation, bitstream, hardware manager or board action.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 is required"}
set project {D:/ican/codex_project/gli26b/project/gl_filter_coexist_20260929.xpr}
if {![file isfile $project]} {error "Isolated coexistence project is absent"}
open_project $project
if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Wrong part"}
set bd_files [get_files -filter {FILE_TYPE == "Block Designs"}]
if {[llength $bd_files] != 1} {error "Expected exactly one block design"}
set bd [lindex $bd_files 0]
open_bd_design $bd
validate_bd_design
generate_target all $bd
set wrapper [make_wrapper -files $bd -top]
if {[llength $wrapper] != 1} {error "Expected one generated wrapper"}
add_files -norecurse $wrapper
set_property top guardianloop_bd_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "INTEGRATED_WRAPPER_READY: $wrapper"
puts "NO_SYNTHESIS_NO_IMPLEMENTATION_NO_BITSTREAM_NO_BOARD_ACTION"
close_project
