#include "mlp.h"
#include <stdio.h>
int main() {
    // Full interface depths are required by the generated RTL co-simulation adapter.
    static int8_t input[1024] = {3,-2}, w1[32*1024] = {2,1,-1,2,100,-100,1,-1};
    int32_t b1[32] = {0,1}, b2[3] = {1,-2,0}, out[3] = {0};
    int8_t w2[3*32] = {0};
    w2[0] = 1; w2[33] = 1; w2[34] = 1; w2[67] = -1;
    if (z20_mlp(input,w1,b1,w2,b2,out,2,1) || out[0]!=3 || out[1]!=125 || out[2]!=-3) return 1;
    out[0] = 123;
    if (z20_mlp(input,w1,b1,w2,b2,out,0,1)!=1 || out[0]!=123) return 2;
    unsigned sizes[4] = {20,40,180,1024};
    for (unsigned vector=0; vector<4; ++vector) {
        unsigned size=sizes[vector], shift=vector*2;
        int sum=0;
        for (unsigned i=0;i<1024;++i) input[i]=(int)(i%5)-1;
        for (unsigned i=0;i<32*1024;++i) w1[i]=0;
        for (unsigned i=0;i<32;++i) b1[i]=0;
        for (unsigned i=0;i<96;++i) w2[i]=0;
        for (unsigned i=0;i<size;++i) { sum+=input[i]; w1[i]=1; w1[size+i]=2; }
        b1[1]=3; b1[2]=4096;
        w2[0]=1;w2[1]=1;w2[2]=-1;w2[32+2]=2;w2[64]=-1;
        b2[0]=5;b2[1]=-7;b2[2]=11;
        int h[3]={sum,2*sum+3,4096};
        for (unsigned i=0;i<3;++i) {
            if (shift) h[i]=(h[i]+(1<<(shift-1)))>>shift;
            if (h[i]>127) h[i]=127;
            if (h[i]<0) h[i]=0;
        }
        if (z20_mlp(input,w1,b1,w2,b2,out,size,shift)) return 3;
        if (out[0]!=h[0]+h[1]-h[2]+5 || out[1]!=2*h[2]-7 || out[2]!=-h[0]+11) return 4;
    }
    puts("PASS: shared D->32->3 six transactions including four model dimensions");
    return 0;
}
