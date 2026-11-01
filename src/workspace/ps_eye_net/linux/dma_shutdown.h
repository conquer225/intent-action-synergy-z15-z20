#ifndef Z15_DMA_SHUTDOWN_H
#define Z15_DMA_SHUTDOWN_H
#include "xil_types.h"
typedef struct {
    u32 (*read)(u32 address);
    void (*write)(u32 address,u32 value);
    u32 (*now)(void);
    void (*delay)(void);
} Z15DmaIo;
/* All implemented video channels must complete reset and report halted. */
int z15_dma_quiesce(const Z15DmaIo *io);
#endif
