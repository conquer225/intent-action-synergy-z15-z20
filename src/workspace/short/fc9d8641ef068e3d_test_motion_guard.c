#include "motion_guard.h"
#include <assert.h>
#include <stdio.h>

static wc_direction simulated_output;

static void fake_motor(void *context, wc_direction direction)
{
    (void)context;
    simulated_output = direction;
}

static wc_guard fresh(void)
{
    wc_guard g;
    wc_init(&g, fake_motor, NULL, UINT64_C(1001), 0);
    assert(simulated_output == WC_STOP);
    return g;
}

static wc_ticket ticket(wc_guard *g, uint64_t now)
{
    wc_ticket t;
    assert(wc_issue_ticket(g, now, &t));
    return t;
}

static bool send(wc_guard *g, wc_ticket t, wc_direction d, uint64_t now)
{
    return wc_command(g, t.boot_id, t.sequence, d, now);
}

int main(void)
{
    wc_guard g;
    wc_ticket t, old;

    g = fresh();
    assert(!g.armed && !wc_issue_ticket(&g, 0, &t));
    assert(!wc_command(&g, 1001, 1, WC_FORWARD, 0));
    puts("PASS boot disabled");

    for (wc_direction d = WC_FORWARD; d <= WC_RIGHT; d++) {
        g = fresh();
        assert(wc_local_arm(&g, 0));
        t = ticket(&g, 0);
        assert(send(&g, t, d, 1));
        assert(simulated_output == d);
    }
    puts("PASS four simulated directions");

    g = fresh(); assert(wc_local_arm(&g, 0)); t = ticket(&g, 0);
    assert(send(&g, t, WC_FORWARD, 299));
    wc_tick(&g, 300);
    assert(!g.armed && simulated_output == WC_STOP);
    puts("PASS late arrival cannot extend issue deadline");

    g = fresh(); assert(wc_local_arm(&g, 0)); t = ticket(&g, 0);
    assert(!send(&g, t, WC_FORWARD, 300));
    assert(simulated_output == WC_STOP);
    puts("PASS expired ticket rejected at boundary");

    g = fresh(); assert(wc_local_arm(&g, 0)); old = ticket(&g, 0);
    t = ticket(&g, 1);
    assert(!send(&g, old, WC_FORWARD, 2));
    assert(!send(&g, t, WC_FORWARD, 3));
    assert(simulated_output == WC_STOP);
    puts("PASS superseded ticket stops and requires local rearm");

    g = fresh(); assert(wc_local_arm(&g, 0)); t = ticket(&g, 0);
    assert(send(&g, t, WC_FORWARD, 1));
    assert(!send(&g, t, WC_FORWARD, 2));
    assert(!g.armed && simulated_output == WC_STOP);
    puts("PASS duplicate command cannot renew movement");

    g = fresh(); assert(wc_local_arm(&g, 0)); t = ticket(&g, 0);
    assert(send(&g, t, WC_FORWARD, 1));
    assert(wc_command(&g, 0, 0, WC_STOP, 2));
    assert(!g.armed && simulated_output == WC_STOP);
    puts("PASS STOP wins without a valid ticket");

    g = fresh(); assert(wc_local_arm(&g, 0)); t = ticket(&g, 0);
    assert(send(&g, t, WC_FORWARD, 1));
    wc_estop(&g);
    assert(!wc_local_arm(&g, 2));
    wc_local_clear_estop(&g);
    assert(!g.armed && !wc_local_arm(&g, 3));
    assert(wc_local_arm(&g, 301));
    puts("PASS estop latch and explicit local clear");

    g = fresh(); assert(wc_local_arm(&g, 0)); t = ticket(&g, 0);
    assert(send(&g, t, WC_FORWARD, 1));
    t = ticket(&g, 100);
    assert(!send(&g, t, WC_BACKWARD, 100));
    assert(simulated_output == WC_STOP);
    t = ticket(&g, 200);
    assert(!send(&g, t, WC_BACKWARD, 200));
    wc_tick(&g, 400);
    assert(simulated_output == WC_STOP); /* No automatically queued reversal. */
    t = ticket(&g, 400);
    assert(send(&g, t, WC_BACKWARD, 400));
    puts("PASS direction change neutral dwell and fresh ticket required");

    g = fresh(); assert(wc_local_arm(&g, 0)); t = ticket(&g, 0);
    assert(send(&g, t, WC_FORWARD, 0));
    for (uint64_t ms = 200; ms <= 800; ms += 200) {
        t = ticket(&g, ms);
        assert(send(&g, t, WC_FORWARD, ms));
    }
    wc_tick(&g, 1000);
    assert(!g.armed && simulated_output == WC_STOP);
    assert(!wc_issue_ticket(&g, 1001, &t));
    puts("PASS renewals cannot bypass one-second bench burst cap");

    g = fresh(); assert(wc_local_arm(&g, 0)); t = ticket(&g, 0);
    assert(!wc_command(&g, 9999, t.sequence, WC_FORWARD, 1));
    puts("PASS previous boot token rejected");

    g = fresh(); assert(wc_local_arm(&g, 0)); t = ticket(&g, 0);
    assert(!send(&g, t, (wc_direction)99, 1));
    assert(simulated_output == WC_STOP);
    puts("PASS invalid direction fails stopped");

    g = fresh(); assert(wc_local_arm(&g, 20)); t = ticket(&g, 20);
    assert(send(&g, t, WC_LEFT, 21));
    wc_tick(&g, 19);
    assert(simulated_output == WC_STOP && g.estop_latched);
    puts("PASS clock regression latches fault");

    g = fresh();
    wc_tick(&g, UINT64_MAX);
    assert(!wc_local_arm(&g, UINT64_MAX));
    puts("PASS clock overflow fails stopped");

    g = fresh(); assert(wc_local_arm(&g, 0));
    g.sequence = UINT64_MAX;
    assert(!wc_issue_ticket(&g, 1, &t));
    assert(!g.armed);
    puts("PASS sequence overflow cannot wrap");

    wc_init(&g, NULL, NULL, 1001, 0);
    assert(!wc_local_arm(&g, 0));
    wc_init(&g, fake_motor, NULL, 0, 0);
    assert(!wc_local_arm(&g, 0));
    puts("PASS missing hardware binding or boot identity cannot arm");

    g = fresh(); assert(wc_manual_arm(&g, 0));
    for (uint64_t now = 0; now < 120000; now += 100) {
        assert(wc_issue_ticket(&g, now, &t));
        assert(send(&g, t, WC_FORWARD, now + 1));
        assert(simulated_output == WC_FORWARD && g.manual_mode);
    }
    wc_tick(&g, 120399);
    assert(simulated_output == WC_FORWARD);
    wc_tick(&g, 120400);
    assert(simulated_output == WC_STOP && !g.armed && !g.manual_mode);
    assert(!send(&g, t, WC_FORWARD, 120401));
    assert(!wc_issue_ticket(&g, 120402, &t));
    puts("PASS manual renewals run beyond two minutes, lease loss stops and never rearms");

    g = fresh(); assert(wc_manual_arm(&g, 0));
    wc_tick(&g, 500); assert(!g.armed && simulated_output == WC_STOP);
    assert(wc_manual_arm(&g, 501));
    assert(wc_issue_ticket(&g, 501, &t) && send(&g, t, WC_LEFT, 502));
    assert(wc_command(&g, 0, 0, WC_STOP, 503));
    assert(!g.manual_mode && !g.armed);
    assert(!wc_manual_arm(&g, 504));
    assert(wc_local_arm(&g, 803));
    assert(!g.manual_mode);
    assert(wc_issue_ticket(&g, 803, &t) && send(&g, t, WC_RIGHT, 804));
    wc_tick(&g, 1103); assert(!g.armed && simulated_output == WC_STOP);
    puts("PASS unused manual lease, STOP, neutral dwell and legacy bounded mode stay independent");

    g = fresh(); wc_estop(&g); assert(!wc_manual_arm(&g, 0));
    wc_local_clear_estop(&g); assert(!g.armed && !g.manual_mode);
    assert(wc_manual_arm(&g, 1));
    assert(wc_issue_ticket(&g, 1, &t));
    assert(send(&g, t, WC_FORWARD, 299));
    wc_tick(&g, 501); assert(!g.armed && simulated_output == WC_STOP);
    puts("PASS late manual commands cannot extend issue-time lease or clear ESTOP");
    puts("PASS 19 host-only receiver test groups; NO HARDWARE IO");
    return 0;
}
