#ifndef WC_COMMAND_WIRE_H
#define WC_COMMAND_WIRE_H

#include <stddef.h>
#include "motion_guard.h"

typedef struct {
    uint64_t boot_id;
    uint64_t sequence;
    wc_direction direction;
} wc_wire_command;

/* Exact ASCII: 16 hex digits, space, 16 hex digits, space, direction word. */
bool wc_decode_command(const char *data, size_t size, wc_wire_command *command);

#endif
