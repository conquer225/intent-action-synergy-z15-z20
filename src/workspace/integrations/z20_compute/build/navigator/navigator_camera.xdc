#----------------------摄像头接口的时钟---------------------------
#72M
create_clock -period 13.888 -name cam0_pclk [get_ports cam_pclk_0]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets cam_pclk_0_IBUF]

create_clock -period 13.888 -name cam1_pclk [get_ports cam_pclk_1]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets cam_pclk_1_IBUF]

set_property PACKAGE_PIN J20 [get_ports {TMDS_tmds_data_p[2]}]
set_property PACKAGE_PIN K19 [get_ports {TMDS_tmds_data_p[1]}]
set_property PACKAGE_PIN G19 [get_ports {TMDS_tmds_data_p[0]}]
set_property PACKAGE_PIN J18 [get_ports TMDS_tmds_clk_p]

#----------------------摄像头接口1---------------------------
set_property -dict {PACKAGE_PIN N18 IOSTANDARD LVCMOS33} [get_ports cam_rst_n_0]
set_property -dict {PACKAGE_PIN P16 IOSTANDARD LVCMOS33} [get_ports cam_pwdn_0]
set_property -dict {PACKAGE_PIN P19 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[0]}]
set_property -dict {PACKAGE_PIN N17 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[1]}]
set_property -dict {PACKAGE_PIN P18 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[2]}]
set_property -dict {PACKAGE_PIN V20 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[3]}]
set_property -dict {PACKAGE_PIN W20 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[4]}]
set_property -dict {PACKAGE_PIN R17 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[5]}]
set_property -dict {PACKAGE_PIN R16 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[6]}]
set_property -dict {PACKAGE_PIN W19 IOSTANDARD LVCMOS33} [get_ports {cam_data_0[7]}]
set_property -dict {PACKAGE_PIN U20 IOSTANDARD LVCMOS33} [get_ports cam_href_0]
set_property -dict {PACKAGE_PIN W18 IOSTANDARD LVCMOS33} [get_ports cam_pclk_0]
set_property -dict {PACKAGE_PIN M19 IOSTANDARD LVCMOS33} [get_ports cam_vsync_0]
#cam_scl:
set_property -dict {PACKAGE_PIN M20 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[0]}]
#cam_sda:
set_property -dict {PACKAGE_PIN T20 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[1]}]
#pull up
set_property PULLUP true [get_ports {emio_sccb_tri_io[0]}]
set_property PULLUP true [get_ports {emio_sccb_tri_io[1]}]

#----------------------摄像头接口2---------------------------
set_property -dict {PACKAGE_PIN V18 IOSTANDARD LVCMOS33} [get_ports cam_rst_n_1]
set_property -dict {PACKAGE_PIN P15 IOSTANDARD LVCMOS33} [get_ports cam_pwdn_1]
set_property -dict {PACKAGE_PIN V17 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[0]}]
set_property -dict {PACKAGE_PIN U17 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[1]}]
set_property -dict {PACKAGE_PIN T16 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[2]}]
set_property -dict {PACKAGE_PIN Y16 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[3]}]
set_property -dict {PACKAGE_PIN Y17 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[4]}]
set_property -dict {PACKAGE_PIN T15 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[5]}]
set_property -dict {PACKAGE_PIN T14 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[6]}]
set_property -dict {PACKAGE_PIN W16 IOSTANDARD LVCMOS33} [get_ports {cam_data_1[7]}]
set_property -dict {PACKAGE_PIN R18 IOSTANDARD LVCMOS33} [get_ports cam_href_1]
set_property -dict {PACKAGE_PIN V16 IOSTANDARD LVCMOS33} [get_ports cam_pclk_1]
set_property -dict {PACKAGE_PIN Y19 IOSTANDARD LVCMOS33} [get_ports cam_vsync_1]
#cam_scl:
set_property -dict {PACKAGE_PIN Y18 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[2]}]
#cam_sda:
set_property -dict {PACKAGE_PIN T17 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[3]}]
#pull up
set_property PULLUP true [get_ports {emio_sccb_tri_io[2]}]
set_property PULLUP true [get_ports {emio_sccb_tri_io[3]}]

set_property IOSTANDARD TMDS_33 [get_ports TMDS_*]
