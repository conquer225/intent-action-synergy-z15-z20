#include "video_boot.h"
int z20_video_start(const z20_video_ops *ops, void *context, unsigned base)
{
    unsigned i;
    if (!ops || !ops->camera || !ops->dma || !ops->display || !base || base%64
            || base>0x40000000u-8294400u) return -100;
    for (i=0; i<2; ++i)
        if (ops->camera(context, i, 640, 720)) return -1-(int)i;
    for (i=0; i<3; ++i)
        if (ops->dma(context, i, base+(i==1?1920:0), i==2?3840:1920, 3840, 720))
            return -10-(int)i;
    return ops->display(context)?-20:0;
}
