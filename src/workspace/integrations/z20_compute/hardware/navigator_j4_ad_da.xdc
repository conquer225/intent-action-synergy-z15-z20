# Navigator ATK-DF7010/7020P, XC7Z020CLG400-2, J4 AD/DA only.
# Pin mapping appears identically in vendor examples 44_top_ad_da_fft_lcd
# and 45_top_ad_da_fir_lcd at commit 8ef40ed5cb3c9ea1d5310018af7a4f0a79d1adb4.
# These are FPGA package pins; verify physical module orientation separately.
set_property -dict {PACKAGE_PIN Y9 IOSTANDARD LVCMOS33} [get_ports {da_data[0]}]
set_property -dict {PACKAGE_PIN Y8 IOSTANDARD LVCMOS33} [get_ports {da_data[1]}]
set_property -dict {PACKAGE_PIN W10 IOSTANDARD LVCMOS33} [get_ports {da_data[2]}]
set_property -dict {PACKAGE_PIN W9 IOSTANDARD LVCMOS33} [get_ports {da_data[3]}]
set_property -dict {PACKAGE_PIN V11 IOSTANDARD LVCMOS33} [get_ports {da_data[4]}]
set_property -dict {PACKAGE_PIN V10 IOSTANDARD LVCMOS33} [get_ports {da_data[5]}]
set_property -dict {PACKAGE_PIN Y13 IOSTANDARD LVCMOS33} [get_ports {da_data[6]}]
set_property -dict {PACKAGE_PIN Y12 IOSTANDARD LVCMOS33} [get_ports {da_data[7]}]
set_property -dict {PACKAGE_PIN Y11 IOSTANDARD LVCMOS33} [get_ports da_clk]
set_property -dict {PACKAGE_PIN W15 IOSTANDARD LVCMOS33} [get_ports {ad_data[0]}]
set_property -dict {PACKAGE_PIN V15 IOSTANDARD LVCMOS33} [get_ports {ad_data[1]}]
set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports {ad_data[2]}]
set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports {ad_data[3]}]
set_property -dict {PACKAGE_PIN W13 IOSTANDARD LVCMOS33} [get_ports {ad_data[4]}]
set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} [get_ports {ad_data[5]}]
set_property -dict {PACKAGE_PIN U15 IOSTANDARD LVCMOS33} [get_ports {ad_data[6]}]
set_property -dict {PACKAGE_PIN U14 IOSTANDARD LVCMOS33} [get_ports {ad_data[7]}]
set_property -dict {PACKAGE_PIN V13 IOSTANDARD LVCMOS33} [get_ports ad_clk]
set_property -dict {PACKAGE_PIN U13 IOSTANDARD LVCMOS33} [get_ports ad_otr]
