set root [file normalize [file join [file dirname [info script]] ..]]
open_checkpoint $root/build/stereo_implementation/system_wrapper_routed.dcp
report_utilization -hierarchical -hierarchical_depth 5 -file $root/build/stereo_implementation/hierarchical.rpt
foreach pattern {*video_observer* *video_observer*epoch* *video_observer*ticks* *ps7_0_axi_periph*xbar*} {
 puts "AUDIT_CELLS $pattern [llength [get_cells -hier -quiet $pattern]]"
}
close_design
open_project $root/build/z20_video_npu/project/z20_video_npu.xpr
puts "AUDIT_TOP [get_property TOP [current_fileset]]"
foreach f [get_files *system_wrapper.v] {puts "AUDIT_WRAPPER $f [get_property IS_ENABLED $f] [get_property USED_IN $f]"}
puts AUDIT_COMPLETE
exit
