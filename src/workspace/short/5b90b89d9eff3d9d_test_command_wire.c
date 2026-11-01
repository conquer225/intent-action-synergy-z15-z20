#include "command_wire.h"
#include "backup_gpio_pattern.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static wc_direction simulated_output;
static void fake_output(void *unused, wc_direction direction)
{
    (void)unused;
    simulated_output = direction;
}

static bool decode(const char *text, wc_wire_command *command)
{
    return wc_decode_command(text, strlen(text), command);
}

int main(void)
{
    wc_wire_command c;
    const char *words[] = {"stop", "forward", "backward", "left", "right"};
    char text[64];
    for (unsigned i = 0; i < 5; i++) {
        snprintf(text, sizeof(text), "00000000000003e9 0000000000000001 %s", words[i]);
        assert(decode(text, &c));
        assert(c.boot_id == 1001 && c.sequence == 1 && c.direction == (wc_direction)i);
    }
    puts("PASS five exact command words");
    assert(decode("FFFFFFFFFFFFFFFF FFFFFFFFFFFFFFFF right", &c));
    assert(c.boot_id == UINT64_MAX && c.sequence == UINT64_MAX);
    puts("PASS full-width identifiers without floating-point conversion");
    assert(decode("0000000000000000 0000000000000000 stop", &c));
    assert(!decode("0000000000000000 0000000000000001 forward", &c));
    assert(!decode("0000000000000001 0000000000000000 left", &c));
    puts("PASS STOP accepts no ticket; movement requires nonzero identifiers");
    const char *invalid[] = {
        "-000000000000001 0000000000000001 forward",
        "000000000000000g 0000000000000001 forward",
        "0000000000000001 0000000000000001 forwards",
        "0000000000000001 0000000000000001 STOP",
        "0000000000000001 0000000000000001 right\n",
        "0000000000000001 0000000000000001 right extra",
        "0000000000000001\t0000000000000001 right",
        "{}", "", "0000000000000001 0000000000000001 unknown"
    };
    for (unsigned i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++) {
        c.direction = WC_FORWARD;
        assert(!decode(invalid[i], &c) && c.direction == WC_STOP);
    }
    puts("PASS malformed bodies clear the parsed direction");
    assert(!wc_decode_command(NULL, 40, &c));
    assert(!wc_decode_command(text, 40, NULL));
    puts("PASS missing buffers rejected");
    const uint32_t masks[] = {0, 0x3000, 0x0c00, 0x2400, 0x1800};
    for (unsigned i = 0; i < 5; i++) {
        uint32_t mask = wc_backup_gpio_mask((wc_direction)i);
        assert(mask == masks[i]);
        assert((mask & 0x2800) != 0x2800 && (mask & 0x1400) != 0x1400);
    }
    assert(wc_backup_gpio_mask((wc_direction)99) == 0);
    puts("PASS backup-only GPIO masks and paired-input exclusion");
    wc_guard g;
    wc_ticket t;
    wc_init(&g, fake_output, NULL, 1001, 0);
    assert(wc_local_arm(&g, 0) && wc_issue_ticket(&g, 0, &t));
    assert(decode("00000000000003e9 0000000000000001 right", &c));
    assert(wc_command(&g, c.boot_id, c.sequence, c.direction, 1));
    assert(simulated_output == WC_RIGHT);
    wc_tick(&g, 300);
    assert(simulated_output == WC_STOP && !g.armed);
    assert(!wc_command(&g, c.boot_id, c.sequence, c.direction, 301));
    puts("PASS decoded command expires and cannot restart automatically");
    puts("PASS 7 host-only wire/pattern groups; NO HARDWARE IO");
    return 0;
}
