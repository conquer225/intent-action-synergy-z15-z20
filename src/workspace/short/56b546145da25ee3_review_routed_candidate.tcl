# Read-only checkpoint audit; no implementation, bit generation or board access.
if {$argc != 2} {error "Usage: review_routed_candidate.tcl ROUTED_DCP NEW_REPORT"}
open_checkpoint [lindex $argv 0]
set camera_net [get_nets cam_pclk_IBUF]
if {[llength $camera_net] != 1} {error "Expected exactly one vendor camera clock net"}
set route [get_property CLOCK_DEDICATED_ROUTE $camera_net]
if {$route ne "FALSE" && $route ne "0"} {error "Vendor camera route constraint was not applied: $route"}
set f [open [lindex $argv 1] {WRONLY CREAT EXCL}]
puts $f "part=[get_property PART [current_design]]"
puts $f "camera_clock_dedicated_route=$route"
puts $f "scope=checkpoint review only; no board access"
close $f
puts "ROUTED_CAMERA_CONSTRAINT_VERIFIED"
close_design
