#----------------------摄像头接口的时钟---------------------------
#48M
create_clock -period 20.833 -name cam_pclk [get_ports cam_pclk]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets cam_pclk_IBUF]
#----------------------摄像头接口---------------------------
set_property -dict {PACKAGE_PIN J7 IOSTANDARD LVCMOS18} [get_ports {cam_data[0]}]
set_property -dict {PACKAGE_PIN P3 IOSTANDARD LVCMOS18} [get_ports {cam_data[1]}]
set_property -dict {PACKAGE_PIN J6 IOSTANDARD LVCMOS18} [get_ports {cam_data[2]}]
set_property -dict {PACKAGE_PIN P2 IOSTANDARD LVCMOS18} [get_ports {cam_data[3]}]
set_property -dict {PACKAGE_PIN U1 IOSTANDARD LVCMOS18} [get_ports {cam_data[4]}]
set_property -dict {PACKAGE_PIN M2 IOSTANDARD LVCMOS18} [get_ports {cam_data[5]}]
set_property -dict {PACKAGE_PIN L7 IOSTANDARD LVCMOS18} [get_ports {cam_data[6]}]
set_property -dict {PACKAGE_PIN M1 IOSTANDARD LVCMOS18} [get_ports {cam_data[7]}]
set_property -dict {PACKAGE_PIN R8 IOSTANDARD LVCMOS18} [get_ports cam_href]
set_property -dict {PACKAGE_PIN U2 IOSTANDARD LVCMOS18} [get_ports cam_pclk]
set_property -dict {PACKAGE_PIN K7 IOSTANDARD LVCMOS18} [get_ports cam_pwdn]
set_property -dict {PACKAGE_PIN F4 IOSTANDARD LVCMOS18} [get_ports cam_rst_n]
set_property -dict {PACKAGE_PIN H8 IOSTANDARD LVCMOS18} [get_ports cam_vsync]
#cam_scl:
set_property -dict {PACKAGE_PIN AA12 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[0]}]
#cam_sda:
set_property -dict {PACKAGE_PIN AB12 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[1]}]
set_property PULLUP true [get_ports {emio_sccb_tri_io[1]}]

#----------------------hdmi_out接口---------------------------
set_property -dict {PACKAGE_PIN U19  IOSTANDARD TMDS_33} [get_ports {TMDS_0_tmds_data_p[2]}]
set_property -dict {PACKAGE_PIN AB21 IOSTANDARD TMDS_33} [get_ports {TMDS_0_tmds_data_p[1]}]
set_property -dict {PACKAGE_PIN AB16 IOSTANDARD TMDS_33} [get_ports {TMDS_0_tmds_data_p[0]}]
set_property -dict {PACKAGE_PIN AA16 IOSTANDARD TMDS_33} [get_ports  TMDS_0_tmds_clk_p]

