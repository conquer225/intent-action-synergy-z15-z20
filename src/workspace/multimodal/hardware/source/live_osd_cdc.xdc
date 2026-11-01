# Held payload launches with request_toggle. The destination samples it only
# after two request synchronizer stages AND the next pixel edge at VSYNC.
# Earliest capture is >=2 pixel periods (26.666 ns); require data <=20 ns.
# Ack returns only after capture; no held bit changes until that acknowledgement.
set osd_hold_regs [get_cells -hier -regexp {.*live_osd_0/inst/held_data_reg.*}]
set osd_receiver_regs [get_cells -hier -filter {IS_SEQUENTIAL && NAME =~ */live_osd_0/inst/renderer/*}]
set_max_delay -datapath_only 20.000 -from $osd_hold_regs -to $osd_receiver_regs
set osd_sync_first_d [get_pins -of_objects [get_cells -hier -regexp {.*live_osd_0/inst/(req_sync_reg|ack_sync_reg|cam_sync_reg)\[0\]}] -filter {REF_PIN_NAME == D}]
set_false_path -to $osd_sync_first_d
# Registered Gray code: bound skew below the source period; synchronize at 100 MHz.
set osd_gray_regs [get_cells -hier -regexp {.*live_osd_0/inst/display_gray_reg.*}]
set osd_gray_meta_regs [get_cells -hier -regexp {.*live_osd_0/inst/display_gray_meta_reg.*}]
set_max_delay -datapath_only 13.333 -from $osd_gray_regs -to $osd_gray_meta_regs
set_bus_skew 10.000 -from $osd_gray_regs -to $osd_gray_meta_regs
# Reset asserts asynchronously; the two-stage chain releases synchronously.
set osd_reset_clr [get_pins -of_objects [get_cells -hier -regexp {.*live_osd_0/inst/pix_reset_sync_reg.*}] -filter {REF_PIN_NAME == CLR}]
set_false_path -to $osd_reset_clr
# Pixel-side statistics are held until the next mailbox apply. Software reads
# after busy clears and two AXI cycles have passed; bound settling within 20 ns.
set stim_held [get_cells -hier -regexp {.*live_osd_0/inst/stimulus_held_reg.*}]
set stim_meta [get_cells -hier -regexp {.*live_osd_0/inst/stimulus_meta_reg.*}]
set_max_delay -datapath_only 20.000 -from $stim_held -to $stim_meta
