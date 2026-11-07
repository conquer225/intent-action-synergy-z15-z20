# Vivado 2023.1. Source into an open BD, then call pl_accel::attach eeg|map <IP directory>.
namespace eval pl_accel {
proc attach {kind ipdir} {
    if {$kind ni {eeg map}} {error "Expected eeg or map"}
    set top [expr {$kind eq "eeg" ? "z15_fbcsp" : "z20_map"}]
    set part [expr {$kind eq "eeg" ? "xc7z015clg485-2" : "xc7z020clg400-2"}]
    set address [expr {$kind eq "eeg" ? 0x83c50000 : 0x83c40000}]
    if {[get_property PART [current_project]] ne $part} {error "Target part differs from $part"}
    if {![file isfile [file join $ipdir component.xml]]} {error "Expected exported HLS IP directory"}
    set ps [get_bd_cells -quiet -filter {VLNV =~ "xilinx.com:ip:processing_system7:*"}]
    if {[llength $ps] != 1} {error "Expected one processing_system7"}
    foreach property {PCW_USE_M_AXI_GP1 PCW_USE_S_AXI_HP2 PCW_EN_CLK2_PORT PCW_EN_RST2_PORT} {
        if {[get_property CONFIG.$property $ps] != 0} {error "Extension requires a free PS $property"}
    }
    if {[llength [get_bd_cells -quiet ${top}_0]]} {error "Extension already exists"}
    set before_ports [lsort [concat [get_bd_ports -quiet] [get_bd_intf_ports -quiet]]]
    set data [get_bd_addr_spaces $ps/Data]
    set before_addresses {}
    foreach seg [get_bd_addr_segs -of_objects $data] {
        set offset [get_property OFFSET $seg]
        set range [get_property RANGE $seg]
        if {$offset < $address+65536 && $offset+$range > $address} {error "Extension control address overlaps $seg"}
        dict set before_addresses $seg [list $offset $range]
    }
    set_property ip_repo_paths [lsort -unique [concat [get_property ip_repo_paths [current_project]] [list [file normalize $ipdir]]]] [current_project]
    update_ip_catalog
    set core [create_bd_cell -type ip -vlnv xilinx.com:hls:${top}:1.0 ${top}_0]
    set_property -dict [list CONFIG.PCW_USE_M_AXI_GP1 1 CONFIG.PCW_USE_S_AXI_HP2 1 \
        CONFIG.PCW_EN_CLK2_PORT 1 CONFIG.PCW_EN_RST2_PORT 1 \
        CONFIG.PCW_FPGA2_PERIPHERAL_FREQMHZ 100.000000] $ps
    set reset [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 pl_accel_reset]
    set one [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 pl_accel_one]
    set zero [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 pl_accel_zero]
    set_property CONFIG.CONST_VAL 0 $zero
    set ctrl [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 pl_accel_control]
    set masters [lsort [get_bd_intf_pins -of_objects $core -filter {MODE == "Master" && VLNV =~ "xilinx.com:interface:aximm_rtl:*"}]]
    if {[llength $masters] != ($kind eq "eeg" ? 2 : 3)} {error "Unexpected HLS memory port contract"}
    set memory [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 pl_accel_memory]
    set_property -dict [list CONFIG.NUM_SI [llength $masters] CONFIG.NUM_MI 1] $memory
    connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_GP1] [get_bd_intf_pins $ctrl/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins $ctrl/M00_AXI] [get_bd_intf_pins $core/s_axi_control]
    connect_bd_intf_net [get_bd_intf_pins $memory/M00_AXI] [get_bd_intf_pins $ps/S_AXI_HP2]
    set clockpins [list [get_bd_pins $ps/M_AXI_GP1_ACLK] [get_bd_pins $ps/S_AXI_HP2_ACLK] \
        [get_bd_pins $core/ap_clk] [get_bd_pins $reset/slowest_sync_clk]]
    set resetpins [list [get_bd_pins $core/ap_rst_n]]
    foreach interconnect [list $ctrl $memory] {
        foreach pin [get_bd_pins -of_objects $interconnect -filter {NAME =~ "*ACLK"}] {lappend clockpins $pin}
        foreach pin [get_bd_pins -of_objects $interconnect -filter {NAME =~ "*ARESETN"}] {lappend resetpins $pin}
    }
    connect_bd_net [get_bd_pins $ps/FCLK_CLK2] {*}$clockpins
    connect_bd_net [get_bd_pins $ps/FCLK_RESET2_N] [get_bd_pins $reset/ext_reset_in]
    connect_bd_net [get_bd_pins $one/dout] [get_bd_pins $reset/dcm_locked]
    connect_bd_net [get_bd_pins $zero/dout] [get_bd_pins $reset/aux_reset_in] [get_bd_pins $reset/mb_debug_sys_rst]
    connect_bd_net [get_bd_pins $reset/peripheral_aresetn] {*}$resetpins
    set i 0
    foreach master $masters {
        connect_bd_intf_net $master [get_bd_intf_pins $memory/[format S%02d_AXI $i]]
        incr i
    }
    assign_bd_address -offset $address -range 64K -target_address_space $data [get_bd_addr_segs $core/s_axi_control/Reg]
    foreach master $masters {
        set space [get_bd_addr_spaces -of_objects $master]
        if {[llength $space] != 1} {error "Expected one memory address space per HLS master"}
        assign_bd_address -offset 0 -range 1G -target_address_space $space [get_bd_addr_segs $ps/S_AXI_HP2/HP2_DDR_LOWOCM]
    }
    validate_bd_design
    if {[get_property CONFIG.C_EXT_RESET_HIGH $reset] != 0} {error "Expected PS active-low extension reset"}
    if {$before_ports ne [lsort [concat [get_bd_ports -quiet] [get_bd_intf_ports -quiet]]]} {error "Original external ports changed"}
    dict for {seg location} $before_addresses {
        if {$location ne [list [get_property OFFSET $seg] [get_property RANGE $seg]]} {error "Original address changed: $seg"}
    }
    puts "PL_ACCEL_ATTACHED kind=$kind part=$part clock_mhz=100 control=[format 0x%08x $address]"
    return $core
}
}
