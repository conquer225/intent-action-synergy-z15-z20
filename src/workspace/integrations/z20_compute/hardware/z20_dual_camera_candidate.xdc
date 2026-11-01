# Z20 CLG484 dual OV5640 / HDMI candidate constraints; NOT board validated.
# Camera mapping: Z20 Vitis guide V1.0, PDF pages 771-773, chapter 38.
# J22 connector mapping: Z20 base schematic V1.0, PDF page 9.
# HDMI differential mapping: base schematic page 2 (CN1) and core bank pins.
# Ports follow the chapter-38 BD wrapper. Do not import the all-peripheral XDC.
# Manual page 772 and both schematics give data2 C17=P, C18=N.
# The supplied all-peripheral Z20 ZYNQ_IO.xdc instead lists C18 for data2 P.
# Use the schematic polarity here and retain the discrepancy in board evidence.
# PCLK periods below are the manual's 72 MHz mode, NOT measured camera clocks.
# No blanket CLOCK_DEDICATED_ROUTE/FALSE or false-path exceptions are copied.
# Input delays, CDC paths, actual PCLK routing, VCCIO and output timing remain open.

create_clock -period 13.888 -name cam0_pclk [get_ports cam_pclk_0]
create_clock -period 13.888 -name cam1_pclk [get_ports cam_pclk_1]

set_property -dict {PACKAGE_PIN R20 IOSTANDARD LVCMOS33} [get_ports cam_rst_n_0]
set_property -dict {PACKAGE_PIN F21 IOSTANDARD LVCMOS33} [get_ports cam_pwdn_0]
set_property -dict {PACKAGE_PIN V22 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[0]}]
set_property -dict {PACKAGE_PIN U22 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[1]}]
set_property -dict {PACKAGE_PIN U9 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[2]}]
set_property -dict {PACKAGE_PIN T22 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[3]}]
set_property -dict {PACKAGE_PIN U10 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[4]}]
set_property -dict {PACKAGE_PIN AB12 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[5]}]
set_property -dict {PACKAGE_PIN AB11 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[6]}]
set_property -dict {PACKAGE_PIN AA12 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[7]}]
set_property -dict {PACKAGE_PIN R21 IOSTANDARD LVCMOS33} [get_ports cam_href_0]
set_property -dict {PACKAGE_PIN AA11 IOSTANDARD LVCMOS33} [get_ports cam_pclk_0]
set_property -dict {PACKAGE_PIN T16 IOSTANDARD LVCMOS33} [get_ports cam_vsync_0]
set_property -dict {PACKAGE_PIN M21 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[0]}]
set_property -dict {PACKAGE_PIN W22 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[1]}]

set_property -dict {PACKAGE_PIN D21 IOSTANDARD LVCMOS33} [get_ports cam_rst_n_1]
set_property -dict {PACKAGE_PIN A21 IOSTANDARD LVCMOS33} [get_ports cam_pwdn_1]
set_property -dict {PACKAGE_PIN B22 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[0]}]
set_property -dict {PACKAGE_PIN G19 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[1]}]
set_property -dict {PACKAGE_PIN D22 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[2]}]
set_property -dict {PACKAGE_PIN F19 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[3]}]
set_property -dict {PACKAGE_PIN C22 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[4]}]
set_property -dict {PACKAGE_PIN G17 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[5]}]
set_property -dict {PACKAGE_PIN D20 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[6]}]
set_property -dict {PACKAGE_PIN F17 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[7]}]
set_property -dict {PACKAGE_PIN E21 IOSTANDARD LVCMOS33} [get_ports cam_href_1]
set_property -dict {PACKAGE_PIN C20 IOSTANDARD LVCMOS33} [get_ports cam_pclk_1]
set_property -dict {PACKAGE_PIN F22 IOSTANDARD LVCMOS33} [get_ports cam_vsync_1]
set_property -dict {PACKAGE_PIN A22 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[2]}]
set_property -dict {PACKAGE_PIN B21 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[3]}]

set_property PULLUP true [get_ports {emio_sccb_tri_io[0]}]
set_property PULLUP true [get_ports {emio_sccb_tri_io[1]}]
set_property PULLUP true [get_ports {emio_sccb_tri_io[2]}]
set_property PULLUP true [get_ports {emio_sccb_tri_io[3]}]

set_property -dict {PACKAGE_PIN B19 IOSTANDARD TMDS_33} [get_ports TMDS_tmds_clk_p]
set_property -dict {PACKAGE_PIN B20 IOSTANDARD TMDS_33} [get_ports TMDS_tmds_clk_n]
set_property -dict {PACKAGE_PIN H19 IOSTANDARD TMDS_33} [get_ports {TMDS_tmds_data_p[0]}]
set_property -dict {PACKAGE_PIN H20 IOSTANDARD TMDS_33} [get_ports {TMDS_tmds_data_n[0]}]
set_property -dict {PACKAGE_PIN B16 IOSTANDARD TMDS_33} [get_ports {TMDS_tmds_data_p[1]}]
set_property -dict {PACKAGE_PIN B17 IOSTANDARD TMDS_33} [get_ports {TMDS_tmds_data_n[1]}]
set_property -dict {PACKAGE_PIN C17 IOSTANDARD TMDS_33} [get_ports {TMDS_tmds_data_p[2]}]
set_property -dict {PACKAGE_PIN C18 IOSTANDARD TMDS_33} [get_ports {TMDS_tmds_data_n[2]}]
