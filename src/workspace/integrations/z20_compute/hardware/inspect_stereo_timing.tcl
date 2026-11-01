set root [file normalize [file join [file dirname [info script]] ..]]
open_checkpoint $root/build/z20_video_npu/project/z20_video_npu.runs/impl_1/system_wrapper_placed.dcp
report_timing -max_paths 5 -file $root/build/stereo_implementation/placed-critical-paths.rpt
puts STEREO_TIMING_INSPECTED
exit
