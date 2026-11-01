# Navigator HDMI TMDS pins from vendor example 23_hdmi_colorbar.
set_property -dict {PACKAGE_PIN J20 IOSTANDARD TMDS_33} [get_ports {tmds_data_p[2]}]
set_property -dict {PACKAGE_PIN K19 IOSTANDARD TMDS_33} [get_ports {tmds_data_p[1]}]
set_property -dict {PACKAGE_PIN G19 IOSTANDARD TMDS_33} [get_ports {tmds_data_p[0]}]
set_property -dict {PACKAGE_PIN J18 IOSTANDARD TMDS_33} [get_ports tmds_clk_p]
set_clock_groups -asynchronous -group [get_clocks aud_bclk_generated] -group [get_clocks clk_out1_clk_wiz_video]
