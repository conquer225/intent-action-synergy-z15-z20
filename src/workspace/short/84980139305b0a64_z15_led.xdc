# ALIENTEK Z15 PL user LEDs, verified against the vendor flow_led example.
set_property -dict {PACKAGE_PIN E4 IOSTANDARD LVCMOS18} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN E3 IOSTANDARD LVCMOS18} [get_ports {led[1]}]
