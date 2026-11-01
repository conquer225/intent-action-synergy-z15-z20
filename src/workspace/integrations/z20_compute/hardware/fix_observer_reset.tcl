set root [file normalize [file join [file dirname [info script]] ..]]
open_project $root/build/z20_video_npu/project/z20_video_npu.xpr
open_bd_design [get_files system.bd]
foreach pin {video_observer/aresetn ps7_0_axi_periph/M05_ARESETN} {
 set p [get_bd_pins $pin]
 disconnect_bd_net [get_bd_nets -of_objects $p] $p
 connect_bd_net [get_bd_pins rst_ps7_0_150M/peripheral_aresetn] $p
}
validate_bd_design
save_bd_design
write_bd_tcl -force $root/build/z20_video_npu/system_with_observer.tcl
generate_target all [get_files system.bd]
reset_run synth_1
launch_runs synth_1 -scripts_only
puts OBSERVER_RESET_READY
exit
