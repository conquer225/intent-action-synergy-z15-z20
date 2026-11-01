set work [file normalize [file dirname [info script]]]
set output [file join $work vivado_ooc_v2]
file mkdir $output
read_verilog -sv [file join $work moment6_stream.sv]
read_xdc [file join $work clock_100mhz.xdc]
synth_design -mode out_of_context -top moment6_stream -part xc7z015clg485-2
report_utilization -file [file join $output synth_utilization.rpt]
report_timing_summary -file [file join $output synth_timing.rpt]
write_checkpoint -force [file join $output synth.dcp]
exit
