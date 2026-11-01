open_project {D:/fpga/z15_multimodal/integrations/z20_compute/build/navigator/project/navigator_video_npu.xpr}
set_property source_mgmt_mode None [current_project]
reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -scripts_only
puts NAVIGATOR_IMPL_PREPARED
exit
