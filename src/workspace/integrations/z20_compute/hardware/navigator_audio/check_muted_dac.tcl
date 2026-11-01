# Inspect the synthesized default build before any physical audio test.
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../..]]
set dcp [file join $root build navigator_audio_hdmi project navigator_audio_hdmi.runs synth_1 navigator_audio_hdmi.dcp]
if {[llength $argv] > 0} {set dcp [lindex $argv 0]}
open_checkpoint $dcp
foreach port_name {aud_dacdat beep} {
    set port [get_ports $port_name]
    if {[llength $port] != 1} {error "$port_name port is missing"}
    set output_net [get_nets -of_objects $port]
    set output_buffers [get_cells -of_objects $output_net -filter {REF_NAME == OBUF}]
    if {[llength $output_buffers] != 1} {error "$port_name output buffer not found"}
    set input_net [get_nets -of_objects [get_pins [lindex $output_buffers 0]/I]]
    if {$input_net ne "<const0>"} {error "$port_name output is not tied low: $input_net"}
    puts "MUTED_OUTPUT_PASS: $port_name OBUF input is $input_net"
}
exit
