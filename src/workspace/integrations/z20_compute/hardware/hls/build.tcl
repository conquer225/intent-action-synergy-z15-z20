# Run: vitis_hls -f build.tcl (output remains inside this new module).
set here [file dirname [file normalize [info script]]]
set out [file normalize [file join $here .. .. build hls]]
file mkdir $out
cd $out
open_project -reset mlp
set_top z20_mlp
add_files [file join $here mlp.cpp]
add_files -tb [file join $here test_mlp.cpp]
open_solution -reset solution -flow_target vivado
set_part {xc7z020clg484-2}
create_clock -period 10 -name default
csim_design
csynth_design
export_design -format ip_catalog
exit
