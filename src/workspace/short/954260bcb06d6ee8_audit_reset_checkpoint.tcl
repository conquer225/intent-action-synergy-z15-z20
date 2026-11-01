# Read-only synthesized-checkpoint inspection. No synthesis or implementation.
if {[version -short] ne "2025.2"} {error "Vivado 2025.2 required"}
if {$argc != 2} {error "Usage: audit_reset_checkpoint.tcl checkpoint new-output-directory"}
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} {error "Preserve previous audit output"}
file mkdir $out
open_checkpoint $checkpoint
if {[get_property PART [current_design]] ne "xc7z015clg485-2"} {error "Unexpected part"}
set f [open [file join $out netlist_reset.txt] w]
puts $f "Vivado [version -short]; checkpoint=$checkpoint"
foreach pattern {*empty_fwft_i_reg *pf_shell_reset*} {
    foreach cell [get_cells -hier -filter "NAME =~ $pattern"] {
        puts $f "CELL $cell REF=[get_property REF_NAME $cell]"
        foreach pin [get_pins -of_objects $cell -filter {DIRECTION == IN}] {
            set nets [get_nets -of_objects $pin]
            puts $f " PIN $pin NET=$nets DRIVER=[get_pins -leaf -of_objects $nets -filter {DIRECTION == OUT}]"
            if {[get_property REF_PIN_NAME $pin] in {CLR PRE R S}} {
                puts $f " RESET_STARTPOINTS=[all_fanin -flat -startpoints_only -to $pin]"
            }
        }
    }
}
foreach cell [get_cells -hier -filter {REF_NAME =~ RAMB*}] {
    puts $f "RAM $cell REF=[get_property REF_NAME $cell]"
    foreach pin [get_pins -of_objects $cell -filter {DIRECTION == IN}] {
        if {[regexp {/(CLK|EN|WE|RST)} $pin]} {
            puts $f " PIN $pin NET=[get_nets -of_objects $pin]"
        }
    }
}
close $f
puts "RESET_CHECKPOINT_AUDIT_COMPLETE"
close_design
exit
