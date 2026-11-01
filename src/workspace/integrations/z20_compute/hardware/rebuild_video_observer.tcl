set root [file normalize [file join [file dirname [info script]] ..]]
open_project $root/build/z20_video_npu/project/z20_video_npu.xpr
open_bd_design [get_files system.bd]
reset_run system_video_observer_0_synth_1
reset_run synth_1
generate_target all [get_files system.bd]
launch_runs synth_1 -scripts_only
puts OBSERVER_REBUILD_READY
exit
