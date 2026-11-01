# Integration constraint correction, executed after link_design and before opt.
# Vendor Clock Wizard is driven by PS FCLK0; its standalone pin-source clock
# must not redefine the existing internal clock tree. Replace its primary
# definition with a divide-by-one generated clock, preserving the PS parent.
set ps_source [get_pins -regexp {system_i/processing_system7_0/inst/PS7_i/FCLKCLK\[0\]}]
if {[llength $ps_source]!=1} {error "Missing PS FCLK0 source"}
create_generated_clock -name system_i/clk_wiz_0/inst/clk_in1 -source $ps_source -divide_by 1 [get_pins system_i/clk_wiz_0/inst/clk_in1]
set actual_parent [get_property MASTER_CLOCK [get_clocks system_i/clk_wiz_0/inst/clk_in1]]
if {$actual_parent ne "clk_fpga_0"} {error "Clock Wizard does not derive from PS FCLK0: $actual_parent"}
