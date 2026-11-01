# Vendor P2 routes PCLK to a non-CCIO pin; same exception as vendor camera design.
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets -of_objects [get_pins cam_buf/I]]
# Camera launches on falling PCLK, sampled on rising. Conservative board-level
# provisional envelope (sensor + level translator); requires hardware validation.
set_input_delay -clock cam_pclk -clock_fall -max 8.0 [get_ports {cam_data[*] cam_href cam_vsync}]
set_input_delay -clock cam_pclk -clock_fall -min 0.0 [get_ports {cam_data[*] cam_href cam_vsync}]
# XPM FIFO provides Gray-pointer CDC constraints. Only asynchronous reset/serial inputs
# and synchronizer first stages receive false paths; do not blanket-exempt camera data.
set_false_path -from [get_ports reset_n]
set_false_path -from [get_ports {uart_rx cam_sda}] -to [get_cells -hier -filter {ASYNC_REG == TRUE}]
set_false_path -to [get_pins -hier -regexp {ready_cam_reg\[0\]/D}]
set_false_path -to [get_pins -hier -filter {NAME =~ */pipe_reg*/PRE}]
# The 50 MHz / 25.2 MHz phase relationship gives an unnecessarily short direct
# transfer window. Handshake allows a full destination cycle for the held bus.
set_false_path -to [get_pins -hier -regexp {.*visual_i/(req_sync|ack_sync)_reg\[0\]/D}]
set_max_delay -datapath_only 30.0 -from [get_cells -hier -regexp {.*visual_i/held_reg.*}] -to [get_cells -hier -regexp {.*visual_i/dst_data_reg.*}]
