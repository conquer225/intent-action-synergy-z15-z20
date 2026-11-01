# Fresh, frozen SmartConnect candidate. Simulation/synthesis/route only.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 1 || [lsearch -exact {prepare synth route} [lindex $argv 0]] < 0} {
    error "Usage: rebuild_reset_closure.tcl prepare|synth|route"
}
set mode [lindex $argv 0]
set base "D:/ican/codex_project/eeg_apps_z15/output/pl_reset_closure_20260928"
set input [file join $base inputs]
set project [file join $base project]
set xpr [file join $project pl_filter_candidate_dma.xpr]

proc validate_candidate {} {
    if {[get_property PART [current_project]] ne "xc7z015clg485-2"} {error "Wrong device"}
    if {[get_property CONFIG.NUM_SI [get_bd_cells pf_axi_sc]] ne "2" ||
        [get_property CONFIG.NUM_MI [get_bd_cells pf_axi_sc]] ne "1"} {error "Expected 2x1 SmartConnect"}
    foreach old {pf_memory pf_read_pc pf_write_pc pf_read_sc pf_write_sc} {
        if {[llength [get_bd_cells -quiet $old]]} {error "Stale memory converter: $old"}
    }
    foreach {pin peer} {
        pf_dma/M_AXI_MM2S pf_axi_sc/S00_AXI
        pf_dma/M_AXI_S2MM pf_axi_sc/S01_AXI
        pf_axi_sc/M00_AXI processing_system7_0/S_AXI_HP0
    } {
        set a [get_bd_intf_nets -of_objects [get_bd_intf_pins $pin]]
        set b [get_bd_intf_nets -of_objects [get_bd_intf_pins $peer]]
        if {[llength $a] != 1 || $a ne $b} {error "Wrong AXI connection: $pin -> $peer"}
    }
    foreach {pin peer} {
        pf_axi_sc/aclk processing_system7_0/FCLK_CLK0
        pf_axi_sc/aresetn pf_shell_reset/peripheral_aresetn
    } {
        set a [get_bd_nets -of_objects [get_bd_pins $pin]]
        set b [get_bd_nets -of_objects [get_bd_pins $peer]]
        if {[llength $a] != 1 || $a ne $b} {error "Wrong clock/reset connection: $pin"}
    }
    foreach space {pf_dma/Data_MM2S pf_dma/Data_S2MM} {
        set segs [get_bd_addr_segs -quiet -of_objects [get_bd_addr_spaces $space]]
        if {[llength $segs] != 1 || ![string match "*HP0_DDR_LOWOCM" $segs] ||
            [get_property OFFSET $segs] != 0 ||
            [get_property RANGE $segs] ni {1G 0x40000000 1073741824}} {
            error "Unexpected HP0 DDR mapping for $space: $segs offset=[get_property OFFSET $segs] range=[get_property RANGE $segs]"
        }
    }
    validate_bd_design
}

proc reports {out routed} {
    report_utilization -file [file join $out utilization.rpt]
    report_clocks -file [file join $out clocks.rpt]
    check_timing -verbose -file [file join $out check_timing.rpt]
    report_timing_summary -delay_type min_max -check_timing_verbose -report_unconstrained -max_paths 10 -file [file join $out timing_summary.rpt]
    report_drc -file [file join $out drc.rpt]
    report_methodology -file [file join $out methodology.rpt]
    if {$routed} {
        report_route_status -file [file join $out route_status.rpt]
        report_utilization -hierarchical -hierarchical_depth 8 -file [file join $out utilization_hierarchical.rpt]
    }
}

if {$mode eq "prepare"} {
    if {[file exists $project] || [file exists [file join $base export]]} {error "Preserve previous run: fresh project required"}
    create_project pl_filter_candidate_dma $project -part xc7z015clg485-2
    set_property target_language Verilog [current_project]
    set_property simulator_language Mixed [current_project]
    set_property ip_repo_paths {} [current_project]
    foreach name {primary_sos_core.sv primary_sos_axis.sv primary_filter_top.sv coeff.hex} {
        add_files -norecurse [file join $input $name]
    }
    # Module-reference tops must be Verilog; this top uses no SV-only syntax.
    set_property FILE_TYPE Verilog [get_files [file join $input primary_filter_top.sv]]
    update_compile_order -fileset sources_1
    import_files -norecurse [file join $input filter_candidate.bd]
    set bd [lindex [get_files -filter {FILE_TYPE == "Block Designs"}] 0]
    open_bd_design $bd
    validate_candidate
    set_property synth_checkpoint_mode None [get_files $bd]
    save_bd_design
    generate_target all [get_files $bd]
    add_files -norecurse [make_wrapper -files [get_files $bd] -top]
    set_property top filter_candidate_wrapper [get_filesets sources_1]
    add_files -fileset sim_1 [file join $input full_chain_reset_tb.sv]
    set_property top full_chain_reset_tb [get_filesets sim_1]
    update_compile_order -fileset sources_1
    update_compile_order -fileset sim_1
    file mkdir [file join $base export]
    export_simulation -simulator xsim -directory [file join $base export] -force
    foreach name {vectors.txt coeff.hex} {
        file copy [file join $input $name] [file join $base export xsim $name]
    }
    puts "RESET_CLOSURE_PREPARE_COMPLETE frozen_sources=$input"
} elseif {$mode eq "synth"} {
    set out [file join $base synthesis_reports]
    if {[file exists $out]} {error "Preserve prior synthesis reports"}
    open_project $xpr
    set_property FILE_TYPE Verilog [get_files [file join $input primary_filter_top.sv]]
    update_compile_order -fileset sources_1
    set bd [lindex [get_files -filter {FILE_TYPE == "Block Designs"}] 0]
    open_bd_design $bd
    validate_candidate
    set run [get_runs synth_1]
    if {[get_property PROGRESS $run] ne "0%"} {error "Expected fresh synthesis"}
    if {[file normalize [get_property DIRECTORY $run]] ne [file normalize [file join $project pl_filter_candidate_dma.runs synth_1]]} {error "Run outside isolated project"}
    set_property AUTO_INCREMENTAL_CHECKPOINT 0 $run
    set_property INCREMENTAL_CHECKPOINT {} $run
    file mkdir $out
    set_param general.maxThreads 4
    launch_runs synth_1 -jobs 2
    wait_on_run synth_1
    set status [get_property STATUS $run]
    set f [open [file join $out run_status.txt] w]; puts $f $status; close $f
    if {![string match "synth_design Complete*" $status]} {error "Synthesis failed: $status"}
    open_run synth_1
    reports $out 0
    puts "RESET_CLOSURE_SYNTH_COMPLETE"
} else {
    set out [file join $base route]
    if {[file exists $out]} {error "Preserve prior implementation reports"}
    open_project -read_only $xpr
    set run [get_runs synth_1]
    if {![string match "synth_design Complete*" [get_property STATUS $run]] || [get_property NEEDS_REFRESH $run]} {error "Synthesis missing or stale"}
    open_run synth_1
    if {[get_property PART [current_design]] ne "xc7z015clg485-2" ||
        [llength [get_cells -quiet filter_candidate_i/pf_axi_sc]] != 1 ||
        [llength [get_cells -quiet filter_candidate_i/pf_filter]] != 1 ||
        [llength [get_cells -quiet filter_candidate_i/pf_dma]] != 1} {error "Unexpected netlist"}
    set clocks [get_clocks]
    if {[llength $clocks] != 1 || [get_property PERIOD $clocks] != 20.0} {error "Expected one 50 MHz clock"}
    file mkdir $out
    set_param general.maxThreads 2
    opt_design
    place_design
    phys_opt_design
    route_design
    write_checkpoint [file join $out routed.dcp]
    reports $out 1
    puts "RESET_CLOSURE_ROUTE_COMPLETE"
}
close_project
