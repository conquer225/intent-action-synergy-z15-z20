# Vivado/XSim export from the isolated direct-SmartConnect BD only.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
set base "D:/ican/codex_project/eeg_apps_z15/output/pl_smartconnect_isolated_20260928"
set xpr [file normalize [file join $base project pl_filter_candidate_dma.xpr]]
set out [file normalize [file join $base export]]
if {[file exists $out]} {error "Preserve prior simulation export: $out"}
open_project $xpr
if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Unexpected part"}
set bd [file normalize [file join $base project pl_filter_candidate_dma.srcs sources_1 bd filter_candidate filter_candidate.bd]]
open_bd_design $bd
if {[llength [get_bd_cells -quiet pf_axi_sc]] != 1 ||
    [llength [get_bd_cells -quiet pf_memory]] != 0} {error "Unexpected AXI topology"}
validate_bd_design
generate_target simulation [get_files $bd]
set here [file dirname [info script]]
set tb [file normalize [file join $here full_chain_reset_tb.sv]]
add_files -fileset sim_1 $tb
set_property top full_chain_reset_tb [get_filesets sim_1]
update_compile_order -fileset sim_1
file mkdir $out
export_simulation -simulator xsim -directory $out -force
set golden [file normalize [file join $here .. output pl_primary_filter_q31_20260927]]
foreach name {vectors.txt coeff.hex} {file copy -force [file join $golden $name] [file join $out xsim $name]}
puts "SMARTCONNECT_FULL_CHAIN_EXPORT_ONLY part=[get_property PART [current_project]]"
close_project
