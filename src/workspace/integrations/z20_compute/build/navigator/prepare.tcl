set_param general.maxThreads 2
create_project navigator_video_npu {D:/fpga/z15_multimodal/integrations/z20_compute/build/navigator/project} -part xc7z020clg400-2 -force
set_property ip_repo_paths [list {D:/fpga/z15_multimodal/integrations/z20_compute/build/reference_sources/suchang-ccc__alientek-zynq7020-examples/ZYNQ_Vitis_7020/38_dual_ov5640_hdmi/ip_repo} {D:/fpga/z15_multimodal/integrations/z20_compute/build/hls/mlp/solution/impl/ip} {D:/fpga/z15_multimodal/integrations/z20_compute/build/video_observer_ip}] [current_project]
update_ip_catalog
source {D:/fpga/z15_multimodal/integrations/z20_compute/build/navigator/system.tcl}

if {[get_property PART [current_project]] ne "xc7z020clg400-2"} {error "Wrong Navigator part"}
set ps [get_bd_cells processing_system7_0]
if {[get_property CONFIG.PCW_PACKAGE_NAME $ps] ne "clg400"} {error "Wrong PS package"}
save_bd_design
generate_target all [get_files system.bd]
set wrapper [make_wrapper -files [get_files system.bd] -top]
add_files -norecurse $wrapper
set_property top system_wrapper [current_fileset]
add_files -fileset constrs_1 {D:/fpga/z15_multimodal/integrations/z20_compute/build/navigator/navigator_camera.xdc}
set_property STEPS.OPT_DESIGN.TCL.PRE {D:/fpga/z15_multimodal/integrations/z20_compute/hardware/fix_stereo_clock.tcl} [get_runs impl_1]
set_property STEPS.OPT_DESIGN.TCL.POST {D:/fpga/z15_multimodal/integrations/z20_compute/hardware/check_video_observer_presence.tcl} [get_runs impl_1]
create_ip_run [get_files system.bd]
launch_runs synth_1 -scripts_only
puts NAVIGATOR_PROJECT_READY
exit
