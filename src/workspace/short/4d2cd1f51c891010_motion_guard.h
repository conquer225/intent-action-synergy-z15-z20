#ifndef MOTION_GUARD_H
#define MOTION_GUARD_H

#include <stdbool.h>
#include <stdint.h>

/* Unloaded bench prototype. No GPIO implementation or HTTP server included. */
#define WC_TICKET_MS UINT64_C(300)
#define WC_NEUTRAL_MS UINT64_C(300)
#define WC_MAX_BURST_MS UINT64_C(1000)
#define WC_MANUAL_LEASE_MS UINT64_C(500)

typedef enum {
    WC_STOP = 0, WC_FORWARD, WC_BACKWARD, WC_LEFT, WC_RIGHT
} wc_direction;

typedef void (*wc_motor_output)(void *context, wc_direction direction);

typedef struct {
    uint64_t boot_id;
    uint64_t sequence;
    uint64_t expires_ms;
} wc_ticket;

typedef struct {
    wc_motor_output output;
    void *context;
    uint64_t boot_id;
    uint64_t sequence;
    uint64_t last_ms;
    uint64_t ticket_expires_ms;
    uint64_t motion_expires_ms;
    uint64_t burst_expires_ms;
    uint64_t neutral_until_ms;
    wc_direction direction;
    bool armed;
    bool estop_latched;
    bool ticket_pending;
    bool manual_mode;
} wc_guard;

/* All functions must run serially in the same owner task, using boot-local ms. */
void wc_init(wc_guard *guard, wc_motor_output output, void *context,
             uint64_t unique_boot_id, uint64_t now_ms);
bool wc_local_arm(wc_guard *guard, uint64_t now_ms);
bool wc_manual_arm(wc_guard *guard, uint64_t now_ms);
void wc_disarm(wc_guard *guard);
void wc_estop(wc_guard *guard);
void wc_local_clear_estop(wc_guard *guard);
void wc_tick(wc_guard *guard, uint64_t now_ms);
bool wc_issue_ticket(wc_guard *guard, uint64_t now_ms, wc_ticket *ticket);
bool wc_command(wc_guard *guard, uint64_t boot_id, uint64_t sequence,
                wc_direction direction, uint64_t now_ms);

#endif
