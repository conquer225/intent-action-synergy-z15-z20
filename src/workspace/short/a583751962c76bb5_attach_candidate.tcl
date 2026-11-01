# Definitions only: source does not create/modify a project or launch a run.
# Invoke only inside an isolated candidate BD with free AXI endpoints.
# No guessed DDR/MIO, external pins, AXI addresses, or reset polarity.
namespace eval primary_filter_candidate {
    variable source_dir [file normalize [file dirname [info script]]]
}

proc primary_filter_candidate::attach {ps_name clock_pin resetn_pin control_master memory_slave coeff_file} {
    variable source_dir
    if {![string match "pl_filter_candidate*" [get_property NAME [current_project]]]} {
        error "Refusing non-candidate project; use a separately reviewed isolated copy"
    }
    if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {
        error "Expected existing GuardianLoop project part xc7z015clg485-2"
    }
    set ps [get_bd_cells $ps_name]
    if {[llength $ps] != 1 || [get_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ $ps] != 50.0} {
        error "Expected verified PS FCLK0=50 MHz"
    }
    if {$clock_pin ne "$ps_name/FCLK_CLK0"} {error "Use the verified FCLK0 pin"}
    set reset_pin [get_bd_pins $resetn_pin]
    if {[get_property CONFIG.POLARITY $reset_pin] ne "ACTIVE_LOW"} {
        error "Require a verified synchronous peripheral active-low reset"
    }
    foreach endpoint [list $control_master $memory_slave] {
        set pin [get_bd_intf_pins $endpoint]
        if {[llength $pin]!=1 || [llength [get_bd_intf_nets -quiet -of_objects $pin]]} {
            error "Endpoint must exist and be unconnected: $endpoint"
        }
    }
    if {[get_property MODE [get_bd_intf_pins $control_master]] ne "Master" ||
        [get_property MODE [get_bd_intf_pins $memory_slave]] ne "Slave"} {
        error "Expected control master and PS memory slave endpoints"
    }
    if {$memory_slave ne "$ps_name/S_AXI_HP0"} {error "Candidate uses verified PS HP0"}
    if {![file exists $coeff_file] || [file tail $coeff_file] ne "coeff.hex"} {
        error "Provide the passed Q31 coeff.hex artifact"
    }
    if {[llength [get_bd_cells -quiet {pf_dma pf_filter pf_control pf_lite pf_memory}]]} {
        error "Candidate cells already exist"
    }
    foreach name {primary_sos_core.sv primary_sos_axis.sv primary_filter_top.sv} {
        add_files -norecurse [file join $source_dir $name]
    }
    # BD module-reference requires a Verilog top; this wrapper is Verilog-2001 compatible.
    # Internal arithmetic modules remain SystemVerilog.
    set_property FILE_TYPE Verilog [get_files [file join $source_dir primary_filter_top.sv]]
    add_files -norecurse [file normalize $coeff_file]
    set_property FILE_TYPE {Memory Initialization Files} [get_files [file normalize $coeff_file]]
    update_compile_order -fileset sources_1
    set core [create_bd_cell -type module -reference primary_filter_top pf_filter]
    set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:* pf_dma]
    set_property -dict [list CONFIG.c_include_sg 0 CONFIG.c_include_mm2s 1 CONFIG.c_include_s2mm 1 \
        CONFIG.c_m_axi_mm2s_data_width 64 CONFIG.c_m_axi_s2mm_data_width 64 \
        CONFIG.c_m_axis_mm2s_tdata_width 64 CONFIG.c_s_axis_s2mm_tdata_width 64 \
        CONFIG.c_addr_width 32 CONFIG.c_sg_length_width 16] $dma
    set gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:* pf_control]
    set_property -dict [list CONFIG.C_IS_DUAL 1 CONFIG.C_GPIO_WIDTH 32 CONFIG.C_GPIO2_WIDTH 32 \
        CONFIG.C_ALL_OUTPUTS 1 CONFIG.C_ALL_INPUTS_2 1 CONFIG.C_DOUT_DEFAULT 0x00000001] $gpio
    set lite [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:* pf_lite]
    set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 2] $lite
    set hp [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:* pf_memory]
    set_property -dict [list CONFIG.NUM_SI 2 CONFIG.NUM_MI 1] $hp
    foreach {a b} [list $control_master pf_lite/S00_AXI pf_lite/M00_AXI pf_dma/S_AXI_LITE \
        pf_lite/M01_AXI pf_control/S_AXI pf_dma/M_AXI_MM2S pf_memory/S00_AXI \
        pf_dma/M_AXI_S2MM pf_memory/S01_AXI pf_memory/M00_AXI $memory_slave \
        pf_dma/M_AXIS_MM2S pf_filter/s_axis pf_filter/m_axis pf_dma/S_AXIS_S2MM] {
        connect_bd_intf_net [get_bd_intf_pins $a] [get_bd_intf_pins $b]
    }
    foreach {a b} {
        pf_control/gpio_io_o pf_filter/control_word
        pf_filter/status_word pf_control/gpio2_io_i
    } {
        connect_bd_net [get_bd_pins $a] [get_bd_pins $b]
    }
    foreach pin {
        pf_filter/aclk pf_dma/s_axi_lite_aclk pf_dma/m_axi_mm2s_aclk pf_dma/m_axi_s2mm_aclk
        pf_control/s_axi_aclk pf_lite/ACLK pf_lite/S00_ACLK pf_lite/M00_ACLK pf_lite/M01_ACLK
        pf_memory/ACLK pf_memory/S00_ACLK pf_memory/S01_ACLK pf_memory/M00_ACLK
    } {connect_bd_net [get_bd_pins $clock_pin] [get_bd_pins $pin]}
    foreach pin {
        pf_filter/aresetn pf_dma/axi_resetn pf_control/s_axi_aresetn pf_lite/ARESETN
        pf_lite/S00_ARESETN pf_lite/M00_ARESETN pf_lite/M01_ARESETN pf_memory/ARESETN
        pf_memory/S00_ARESETN pf_memory/S01_ARESETN pf_memory/M00_ARESETN
    } {connect_bd_net $reset_pin [get_bd_pins $pin]}
    # Caller supplies an already reviewed PS/clock/reset shell; do not alter MIO/DDR.
    # PS GP0/HP0 ACLK connections must be in that shell and pass BD validation.
    assign_bd_address
    validate_bd_design
    save_bd_design
    puts "Candidate BD validated only. No synthesis, implementation, bitstream or board action."
}
