#ifndef WC_BACKUP_GPIO_PATTERN_H
#define WC_BACKUP_GPIO_PATTERN_H

#include "motion_guard.h"

/* Extracted from backup fd27dc4f; not a verified physical wiring/stop configuration. */
static inline uint32_t wc_backup_gpio_mask(wc_direction direction)
{
    switch (direction) {
    case WC_FORWARD: return (UINT32_C(1) << 12) | (UINT32_C(1) << 13);
    case WC_BACKWARD: return (UINT32_C(1) << 10) | (UINT32_C(1) << 11);
    case WC_LEFT: return (UINT32_C(1) << 10) | (UINT32_C(1) << 13);
    case WC_RIGHT: return (UINT32_C(1) << 11) | (UINT32_C(1) << 12);
    default: return 0;
    }
}

#endif
