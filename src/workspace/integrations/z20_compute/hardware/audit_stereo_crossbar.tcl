set root [file normalize [file join [file dirname [info script]] ..]]
open_checkpoint $root/build/z20_video_npu/project/z20_video_npu.gen/sources_1/bd/system/ip/system_xbar_9/system_xbar_9.dcp
puts "CROSSBAR_MASTER_PORTS [llength [get_ports -quiet {m_axi_arvalid[*]}]]"
if {[llength [get_ports -quiet {m_axi_arvalid[*]}]]!=6} {error "Observer requires six crossbar master ports; stale five-port checkpoint"}
foreach port [get_ports -quiet {m_axi_arvalid[*]}] {puts "CROSSBAR_PORT $port"}
close_design
puts CROSSBAR_AUDIT_COMPLETE
exit
