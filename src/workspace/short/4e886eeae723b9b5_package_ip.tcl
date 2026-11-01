set script_dir [file normalize [file dirname [info script]]]
set ip_root [file normalize [file join $script_dir ..]]

create_project -in_memory guardianloop_regs_v0_pack -part xc7z015clg485-2
add_files -norecurse [list \
    [file join $ip_root hdl guardianloop_regs_v0_v1_0.v] \
    [file join $ip_root hdl guardianloop_regs_v0_v1_0_S_AXI.v]]
set_property top guardianloop_regs_v0_v1_0 [current_fileset]
update_compile_order -fileset sources_1

ipx::package_project -root_dir $ip_root -vendor guardianloop.org -library user -taxonomy /UserIP -set_current true
set core [ipx::current_core]
set_property name guardianloop_regs_v0 $core
set_property display_name {GuardianLoop Registers v0} $core
set_property description {AXI4-Lite v0 register block with SCRATCH, BUILD_ID, and STATUS registers.} $core
set_property version 1.0 $core

# Vivado infers these lower-case interface names from the RTL port names.
set axi_if [ipx::get_bus_interfaces s_axi -of_objects $core]
set protocol_param [ipx::get_bus_parameters PROTOCOL -of_objects $axi_if]
if {[llength $protocol_param] == 0} {
    set protocol_param [ipx::add_bus_parameter PROTOCOL $axi_if]
}
set_property value AXI4LITE $protocol_param
ipx::associate_bus_interfaces -busif s_axi -clock s_axi_aclk $core

ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::save_core $core
close_project
