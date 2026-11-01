#include "motion_guard.h"
#include <stddef.h>
#include <string.h>

static void set_output(wc_guard *guard, wc_direction direction)
{
    guard->direction = direction;
    if (guard->output != NULL) {
        guard->output(guard->context, direction);
    }
}

void wc_disarm(wc_guard *guard)
{
    if (guard->direction != WC_STOP) {
        guard->neutral_until_ms = guard->last_ms <= UINT64_MAX - WC_NEUTRAL_MS
            ? guard->last_ms + WC_NEUTRAL_MS : UINT64_MAX;
    }
    guard->armed = false;
    guard->manual_mode = false;
    guard->ticket_pending = false;
    guard->motion_expires_ms = 0;
    guard->burst_expires_ms = 0;
    set_output(guard, WC_STOP);
}

void wc_init(wc_guard *guard, wc_motor_output output, void *context,
             uint64_t unique_boot_id, uint64_t now_ms)
{
    memset(guard, 0, sizeof(*guard));
    guard->output = output;
    guard->context = context;
    guard->boot_id = unique_boot_id;
    guard->last_ms = now_ms;
    wc_disarm(guard);
}

void wc_tick(wc_guard *guard, uint64_t now_ms)
{
    if (now_ms < guard->last_ms || now_ms > UINT64_MAX - WC_MAX_BURST_MS) {
        wc_disarm(guard);
        /* A clock fault cannot be cleared by a network request. */
        guard->estop_latched = true;
        return;
    }
    guard->last_ms = now_ms;
    if (guard->ticket_pending && now_ms >= guard->ticket_expires_ms) {
        guard->ticket_pending = false;
    }
    if (guard->armed &&
        (((guard->direction != WC_STOP || guard->manual_mode) && now_ms >= guard->motion_expires_ms) ||
         (guard->burst_expires_ms != 0 && now_ms >= guard->burst_expires_ms))) {
        wc_disarm(guard);
    }
}

bool wc_local_arm(wc_guard *guard, uint64_t now_ms)
{
    wc_tick(guard, now_ms);
    if (guard->estop_latched || guard->boot_id == 0 || guard->output == NULL ||
        guard->armed || now_ms < guard->neutral_until_ms) {
        return false;
    }
    guard->ticket_pending = false;
    guard->burst_expires_ms = 0;
    guard->motion_expires_ms = 0;
    set_output(guard, WC_STOP);
    guard->armed = true;
    return true;
}

bool wc_manual_arm(wc_guard *guard, uint64_t now_ms)
{
    if (!wc_local_arm(guard, now_ms)) return false;
    guard->manual_mode = true;
    guard->motion_expires_ms = now_ms + WC_MANUAL_LEASE_MS;
    return true;
}

void wc_estop(wc_guard *guard)
{
    guard->estop_latched = true;
    wc_disarm(guard);
}

void wc_local_clear_estop(wc_guard *guard)
{
    wc_disarm(guard);
    guard->estop_latched = false;
}

bool wc_issue_ticket(wc_guard *guard, uint64_t now_ms, wc_ticket *ticket)
{
    wc_tick(guard, now_ms);
    if (!guard->armed || guard->estop_latched || ticket == NULL) {
        return false;
    }
    if (guard->sequence == UINT64_MAX) {
        wc_disarm(guard);
        return false;
    }
    guard->sequence++;
    guard->ticket_expires_ms = now_ms + WC_TICKET_MS;
    guard->ticket_pending = true;
    ticket->boot_id = guard->boot_id;
    ticket->sequence = guard->sequence;
    ticket->expires_ms = guard->ticket_expires_ms;
    return true;
}

bool wc_command(wc_guard *guard, uint64_t boot_id, uint64_t sequence,
                wc_direction direction, uint64_t now_ms)
{
    wc_tick(guard, now_ms);
    if (direction == WC_STOP) {
        wc_disarm(guard);
        return true;
    }
    if (direction < WC_FORWARD || direction > WC_RIGHT ||
        !guard->armed || guard->estop_latched || !guard->ticket_pending ||
        boot_id != guard->boot_id || sequence != guard->sequence ||
        now_ms >= guard->ticket_expires_ms) {
        wc_disarm(guard);
        return false;
    }
    guard->ticket_pending = false;
    if (guard->direction != WC_STOP && guard->direction != direction) {
        set_output(guard, WC_STOP);
        guard->neutral_until_ms = now_ms + WC_NEUTRAL_MS;
        guard->motion_expires_ms = 0;
        return false; /* Never queue a reversal to execute later. */
    }
    if (now_ms < guard->neutral_until_ms) {
        return false;
    }
    if (!guard->manual_mode && guard->burst_expires_ms == 0) {
        guard->burst_expires_ms = now_ms + WC_MAX_BURST_MS;
    }
    /* Deadline is based on receiver issue time, not late packet arrival time. */
    guard->motion_expires_ms = guard->ticket_expires_ms;
    if (guard->manual_mode) {
        guard->motion_expires_ms += WC_MANUAL_LEASE_MS - WC_TICKET_MS;
    } else if (guard->motion_expires_ms > guard->burst_expires_ms) {
        guard->motion_expires_ms = guard->burst_expires_ms;
    }
    set_output(guard, direction);
    return true;
}
