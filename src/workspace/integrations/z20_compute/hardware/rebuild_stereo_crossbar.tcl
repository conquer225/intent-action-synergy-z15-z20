set root [file normalize [file join [file dirname [info script]] ..]]
open_project $root/build/z20_video_npu/project/z20_video_npu.xpr
reset_run system_xbar_9_synth_1
reset_run synth_1
launch_runs synth_1 -scripts_only
puts CROSSBAR_REBUILD_READY
exit
