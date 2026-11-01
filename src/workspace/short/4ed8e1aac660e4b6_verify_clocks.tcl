# Validate a candidate clock tree locally; no PS clock settings or board state change.
if {$argc != 1} {error "Usage: verify_clocks.tcl NEW_OUTPUT_DIR"}
set output_dir [file normalize [lindex $argv 0]]
if {[file exists $output_dir]} {error "Refusing existing clock output"}
create_project audio_clocks $output_dir -part xc7z015clg485-2
create_ip -name clk_wiz -vendor xilinx.com -library ip -version 6.0 -module_name audio_clocks
set clock_ip [get_ips audio_clocks]
set_property -dict [list CONFIG.PRIM_IN_FREQ {100.000} CONFIG.PRIM_SOURCE {No_buffer} \
    CONFIG.NUM_OUT_CLKS {3} CONFIG.CLKOUT2_USED {true} CONFIG.CLKOUT3_USED {true} \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {75.000} CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {375.000} \
    CONFIG.CLKOUT3_REQUESTED_OUT_FREQ {150.000} CONFIG.RESET_TYPE {ACTIVE_HIGH}] $clock_ip
set mult [get_property CONFIG.MMCM_CLKFBOUT_MULT_F $clock_ip]
set div [get_property CONFIG.MMCM_DIVCLK_DIVIDE $clock_ip]
set d0 [get_property CONFIG.MMCM_CLKOUT0_DIVIDE_F $clock_ip]
set d1 [get_property CONFIG.MMCM_CLKOUT1_DIVIDE $clock_ip]
set d2 [get_property CONFIG.MMCM_CLKOUT2_DIVIDE $clock_ip]
set f0 [expr {100.0*$mult/$div/$d0}]
set f1 [expr {100.0*$mult/$div/$d1}]
set f2 [expr {100.0*$mult/$div/$d2}]
if {$f0 != 75.0 || $f1 != 375.0 || $f2 != 150.0} {error "Clock synthesis did not meet exact frequencies: $f0/$f1/$f2"}
generate_target all $clock_ip
report_property $clock_ip -file [file join $output_dir clock_properties.rpt]
set fd [open [file join $output_dir result.json] w]
puts $fd [format {{"passed":true,"scope":"candidate MMCM IP generation only; no board change","input_mhz":100,"pixel_mhz":%s,"serializer_mhz":%s,"audio_divider_input_mhz":%s,"feedback_multiplier":%s,"input_divider":%s,"output_dividers":[%s,%s,%s]}} $f0 $f1 $f2 $mult $div $d0 $d1 $d2]
close $fd
puts "AUDIO_CLOCK_PLAN_PASS pixel=$f0 serial=$f1 sample_source=$f2"
close_project
