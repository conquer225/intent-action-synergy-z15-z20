set root [file normalize [file join [file dirname [info script]] ..]]
set dir $root/build/z20_video_npu/project/z20_video_npu.runs/system_video_observer_0_synth_1
create_project -in_memory -part xc7z020clg484-2
read_verilog -sv [list $root/hardware/rtl/z20_video_epoch.sv $root/hardware/rtl/z20_video_observer.sv $root/build/z20_video_npu/project/z20_video_npu.gen/sources_1/bd/system/ip/system_video_observer_0/synth/system_video_observer_0.sv]
set_param general.maxThreads 1
set_param synth.elaboration.rodinMoreOptions {rt::set_parameter enableParallelHelperSpawn false}
synth_design -top system_video_observer_0 -part xc7z020clg484-2 -mode out_of_context
create_clock -name aclk -period 7 [get_ports aclk]
write_checkpoint -force $dir/system_video_observer_0.dcp
write_checkpoint -force $root/build/z20_video_npu/project/z20_video_npu.gen/sources_1/bd/system/ip/system_video_observer_0/system_video_observer_0.dcp
report_utilization -file $root/build/observer-build/independent-utilization.rpt
puts OBSERVER_INDEPENDENT_SYNTHESIS_COMPLETE
close_project
exit
