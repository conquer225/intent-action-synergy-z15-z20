set root [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
open_project $root
puts "VIVADO_VERSION=[version -short]"
if {[version -short] ne "2025.2"} { error "This isolated co-simulation requires Vivado 2025.2" }
set tb [file normalize [file join [file dirname [info script]] vendor_dma_reset_tb.sv]]
set tb_write [file normalize [file join [file dirname [info script]] vendor_dma_write_reset_tb.sv]]
set write_peer [file normalize [file join [file dirname [info script]] vendor_dma_write_peer.sv]]
set generated [file normalize [file join [file dirname $root] pl_filter_candidate_dma.gen sources_1 bd filter_candidate ip]]
set dma [file join $generated filter_candidate_pf_dma_0 sim filter_candidate_pf_dma_0.vhd]
set converter_read [file join $generated filter_candidate_pf_memory_imp_auto_pc_0 sim filter_candidate_pf_memory_imp_auto_pc_0.v]
set converter_write [file join $generated filter_candidate_pf_memory_imp_auto_pc_1 sim filter_candidate_pf_memory_imp_auto_pc_1.v]
foreach source [list $tb $tb_write $write_peer $dma $converter_read $converter_write] {
    add_files -fileset sim_1 $source
}
update_compile_order -fileset sim_1
set_property top vendor_dma_reset_tb [get_filesets sim_1]
puts "SIM_TOP=[get_property top [get_filesets sim_1]]"
file mkdir $out
export_simulation -simulator xsim -directory $out -force
puts "SIM_EXPORT_DONE=$out"
close_project
