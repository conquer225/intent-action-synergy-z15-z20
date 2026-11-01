#时序约束
create_clock -period 20.000 -name sys_clk  [get_ports sys_clk]

#IO管脚约束
set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports sys_clk]
set_property -dict {PACKAGE_PIN G2 IOSTANDARD LVCMOS18} [get_ports sys_rst_n]
set_property -dict {PACKAGE_PIN E4 IOSTANDARD LVCMOS18} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN E3 IOSTANDARD LVCMOS18} [get_ports {led[1]}]


