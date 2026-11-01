set root [file normalize [file join [file dirname [info script]] ../..]]
set out [file join $root local screen_vivado]
create_project z15_screen $out -part xc7z015clg485-2 -force
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_CDC XPM_MEMORY XPM_FIFO} [current_project]
add_files [glob [file join $root src screen *.sv]]
add_files [glob [file join $root src screen *.v]]
foreach name {reset_sync.sv sccb_master.sv camera_init.sv uart.sv frame_store.sv visual_mailbox.sv} {
 add_files [file join $root src eye $name]
}
add_files [glob [file join $root src third_party projectf *.v]]
add_files -fileset constrs_1 [file join $root board constraints z15_eye.xdc]
add_files -fileset constrs_1 [file join $root board constraints z15_eye_timing.xdc]
set_property USED_IN_SYNTHESIS false [get_files z15_eye_timing.xdc]
set_property top z15_screen_top [current_fileset]
set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY rebuilt [get_runs synth_1]
update_compile_order -fileset sources_1
puts "PROJECT_READY: [file join $out z15_screen.xpr]"
