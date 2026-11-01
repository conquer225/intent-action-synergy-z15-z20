set root [file normalize [file join [file dirname [info script]] ..]]
open_project $root/build/z20_video_npu/project/z20_video_npu.xpr
set_property source_mgmt_mode None [current_project]
set_property top system_wrapper [current_fileset]
open_run impl_1
if {![llength [get_cells system_i/video_observer]]} {error "Observer missing from implemented hierarchy"}
write_hw_platform -fixed -force -file $root/build/stereo_implementation/z20_stereo.xsa
puts STEREO_PLATFORM_EXPORT_COMPLETE
exit
