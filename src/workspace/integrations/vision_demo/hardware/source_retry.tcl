# Bound transient Windows source-open failures. Never retry a partially
# executed parent script or suppress a Tcl evaluation error.
rename ::source ::vision_native_source
proc ::source {args} {
    set requested [file normalize [lindex $args end]]
    for {set attempt 0} {$attempt < 4} {incr attempt} {
        set code [catch {uplevel 1 [list ::vision_native_source {*}$args]} result options]
        if {!$code} {return $result}
        if {![regexp {^couldn't read file "([^"]+)":} $result ignored failed] ||
            [file normalize $failed] ne $requested || ![file isfile $requested] || $attempt==3} {
            return -options $options $result
        }
        puts "VISION_SOURCE_OPEN_RETRY $attempt $requested"
        after 100
    }
}
