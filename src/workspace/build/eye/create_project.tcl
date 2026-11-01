set root [file normalize [file join [file dirname [info script]] ../..]]
set out [file join $root local eye_vivado]
create_project z15_eye $out -part xc7z015clg485-2 -force
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_CDC XPM_MEMORY XPM_FIFO} [current_project]
add_files [glob [file join $root src eye *.sv]]
add_files [glob [file join $root src eye *.v]]
add_files [glob [file join $root src third_party projectf *.v]]
add_files -fileset constrs_1 [file join $root board constraints z15_eye.xdc]
add_files -fileset constrs_1 [file join $root board constraints z15_eye_timing.xdc]
set_property USED_IN_SYNTHESIS false [get_files z15_eye_timing.xdc]
set_property top z15_eye_top [current_fileset]
set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY rebuilt [get_runs synth_1]
update_compile_order -fileset sources_1
puts "PROJECT_READY: [file join $out z15_eye.xpr]"
