# Offline, out-of-context component synthesis only. No Hardware Manager commands.
if {$argc != 3} {error "Usage: synth_components.tcl SOURCE_ROOT OUTPUT_DIR VENDOR_SERIALIZER"}
lassign $argv source_root output_dir vendor_serializer
if {[file exists $output_dir]} {error "Refusing existing synthesis output: $output_dir"}
file mkdir $output_dir
set part xc7z015clg485-2
set upstream [file join $source_root third_party hdmi src]
set hdl [glob [file join $source_root rtl *.sv]]
foreach name {packet_picker packet_assembler audio_clock_regeneration_packet audio_sample_packet audio_info_frame auxiliary_video_information_info_frame source_product_description_info_frame tmds_channel} {
    lappend hdl [file join $upstream ${name}.sv]
}
lappend hdl $vendor_serializer
foreach top {pcm_buffer audio_sample_clock hdmi_audio_tx} {
    create_project $top [file join $output_dir $top] -part $part
    set_property XPM_LIBRARIES {XPM_FIFO} [current_project]
    read_verilog -sv $hdl
    synth_design -top $top -part $part -mode out_of_context
    report_utilization -file [file join $output_dir ${top}_utilization.rpt]
    report_drc -file [file join $output_dir ${top}_drc.rpt]
    write_checkpoint [file join $output_dir ${top}_synth.dcp]
    close_project
}
puts "AUDIO_COMPONENT_SYNTH_PASS"
