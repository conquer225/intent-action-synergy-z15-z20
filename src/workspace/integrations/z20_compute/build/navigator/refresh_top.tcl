open_project {D:/fpga/z15_multimodal/integrations/z20_compute/build/navigator/project/navigator_video_npu.xpr}
set_property source_mgmt_mode None [current_project]
set wrapper [get_files *system_wrapper.v]
puts "WRAPPER=$wrapper"
set_property USED_IN_SYNTHESIS true $wrapper
set_property USED_IN_IMPLEMENTATION true $wrapper
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
reset_run synth_1
launch_runs synth_1 -scripts_only
puts NAVIGATOR_TOP_REFRESHED
exit
