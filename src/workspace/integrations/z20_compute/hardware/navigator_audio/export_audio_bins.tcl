# Emit Linux FPGA Manager .bin files from the routed standalone checkpoints.
set_param general.maxThreads 1
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../..]]
foreach {target basename} {navigator_audio navigator_audio_demo navigator_audio_hdmi navigator_audio_hdmi} {
    set out [file join $root build $target]
    open_checkpoint [file join $out direct_routed.dcp]
    write_bitstream -bin_file -force [file join $out $basename.bit]
    puts "AUDIO_BIN=[file join $out $basename.bin]"
    close_design
}
exit
