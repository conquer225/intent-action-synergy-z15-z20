if {$argc != 2} {error "Usage: inspect_ip_contract.tcl NEW_OUTPUT_DIR VENDOR_IP_ROOT"}
lassign $argv out vendor
if {[file exists $out]} {error "Refusing existing project"}
create_project contract $out -part xc7z015clg485-2
set_property ip_repo_paths [list $vendor] [current_project]
update_ip_catalog
create_bd_design system
foreach {name vlnv} {
    processing_system7_0 xilinx.com:ip:processing_system7:5.5
    axi_vdma_0 xilinx.com:ip:axi_vdma:6.3
    v_tc_0 xilinx.com:ip:v_tc:6.2
    v_axi4s_vid_out_0 xilinx.com:ip:v_axi4s_vid_out:4.0
    v_vid_snapshot xilinx.com:ip:v_vid_in_axi4s:5.0
    ov5640_capture_data_0 alientek.com:user:ov5640_capture_data:1.0
} {
    set cell [create_bd_cell -type ip -vlnv $vlnv $name]
    report_property -all $cell -file [file join $out ${name}_properties.rpt]
}
foreach pin {U19 AB21 AB16 AA16} {
    report_property -all [get_package_pins $pin] -file [file join $out pin_${pin}.rpt]
}
save_bd_design
puts "IP_CONTRACT_INSPECTION_DONE"
close_project
