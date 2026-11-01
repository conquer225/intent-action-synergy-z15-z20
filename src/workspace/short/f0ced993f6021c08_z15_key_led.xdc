# Verified against ALIENTEK XC7Z015/11_key_led official constraints.
set_property -dict {PACKAGE_PIN H5 IOSTANDARD LVCMOS18} [get_ports {key[0]}]
set_property -dict {PACKAGE_PIN H6 IOSTANDARD LVCMOS18} [get_ports {key[1]}]
set_property -dict {PACKAGE_PIN E4 IOSTANDARD LVCMOS18} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN E3 IOSTANDARD LVCMOS18} [get_ports {led[1]}]
