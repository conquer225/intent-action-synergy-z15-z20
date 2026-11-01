/* Bounded nearest-neighbour BGR fit; no PL/MMIO and no colour arithmetic. */
#include <stdint.h>

int fit_bgr(const uint8_t *source, int sw, int sh, uint8_t *dest,
            int dw, int dh, int stride) {
    if (!source || !dest || sw<1 || sh<1 || sw>1280 || sh>720 ||
        dw<1 || dh<1 || dw>1280 || dh>720 || stride<dw*3) return 0;
    int offsets[1280];
    for (int x=0;x<dw;x++) offsets[x]=(x*sw/dw)*3;
    for (int y=0;y<dh;y++) {
        const uint8_t *row=source+(y*sh/dh)*sw*3;
        uint8_t *out=dest+y*stride;
        for (int x=0;x<dw;x++) {
            int offset=offsets[x];
            out[3*x]=row[offset];out[3*x+1]=row[offset+1];out[3*x+2]=row[offset+2];
        }
    }
    return 1;
}
