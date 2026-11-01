set source_root [file normalize $::env(GL_VISION_SOURCE)]
set out [file normalize $::env(GL_VISION_OUTPUT)]
cd $out
open_project audio_hls
set_top audio_fft
add_files [file join $source_root hls audio_fft.cpp]
add_files [file join $source_root hls audio_twiddle.h]
add_files -tb [file join $source_root hls test_audio.cpp]
open_solution solution -flow_target vivado
set_part xc7z015clg485-2
create_clock -period 10 -name default
csim_design
csynth_design
export_design -format ip_catalog -rtl verilog
exit
