// SPDX-License-Identifier: MIT
#ifndef VISION_GPIO_SCOPE_H
#define VISION_GPIO_SCOPE_H
#include <stdint.h>
/* SCCB owns EMIO54/55 outputs, never the GPIO interrupt controller. The
 * retained standalone CfgInitialize masks every bank; Linux owns those masks.
 * Skip all interrupt-register writes in this camera-only MMIO adapter. */
static inline int vision_gpio_write_allowed(uintptr_t address) {
    if(address>=0xe000a000u && address<0xe000b000u){
        uintptr_t offset=address-0xe000a000u;
        if(offset>=0x200u && offset<0x300u){
            uintptr_t bank_offset=(offset-0x200u)%0x40u;
            if(bank_offset>=0x0cu && bank_offset<=0x24u)return 0;
        }
    }
    return 1;
}
#endif
