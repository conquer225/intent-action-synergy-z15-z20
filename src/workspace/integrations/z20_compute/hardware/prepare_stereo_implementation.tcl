set root [file normalize [file join [file dirname [info script]] ..]]
open_project $root/build/z20_video_npu/project/z20_video_npu.xpr
set clocks $root/hardware/z20_camera_clock_provisional.xdc
if {![llength [get_files -quiet $clocks]]} {add_files -fileset constrs_1 $clocks}
set_property USED_IN_SYNTHESIS false [get_files $clocks]
set_property STEPS.OPT_DESIGN.TCL.PRE $root/hardware/fix_stereo_clock.tcl [get_runs impl_1]
set_property STEPS.OPT_DESIGN.TCL.POST $root/hardware/check_video_observer_presence.tcl [get_runs impl_1]
reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -scripts_only
puts STEREO_IMPLEMENTATION_READY
exit
