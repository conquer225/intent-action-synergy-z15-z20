open_project {D:/fpga/z15_multimodal/integrations/z20_compute/build/navigator/project/navigator_video_npu.xpr}
set_property source_mgmt_mode None [current_project]
open_run impl_1
source {D:/fpga/z15_multimodal/integrations/z20_compute/hardware/check_video_observer_presence.tcl}
if {[get_property PART [current_design]] ne "xc7z020clg400-2"} {error "Wrong physical target"}
report_timing_summary -report_unconstrained -file {D:/fpga/z15_multimodal/integrations/z20_compute/build/navigator/timing.rpt}
report_drc -file {D:/fpga/z15_multimodal/integrations/z20_compute/build/navigator/drc.rpt}
report_utilization -file {D:/fpga/z15_multimodal/integrations/z20_compute/build/navigator/utilization.rpt}
write_hw_platform -fixed -include_bit -force -file {D:/fpga/z15_multimodal/integrations/z20_compute/build/navigator/navigator_stereo_npu.xsa}
puts NAVIGATOR_EXPORT_COMPLETE
exit
