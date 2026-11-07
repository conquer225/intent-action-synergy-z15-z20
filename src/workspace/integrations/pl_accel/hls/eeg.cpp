#include <stdint.h>
#include "log_table.h"

namespace {
const unsigned MAGIC=0x46424331, MAX_WINDOW=1024;
int64_t divide(int64_t a,int64_t b) {
#pragma HLS INLINE off
    uint64_t value=a<0 ? (uint64_t)(-a) : (uint64_t)a;
    uint64_t divisor=(uint64_t)b,q=0,remainder=0;
    for(int bit=63;bit>=0;--bit) {
#pragma HLS PIPELINE off
        remainder=(remainder<<1)|((value>>bit)&1);
        if(remainder>=divisor){remainder-=divisor;q|=uint64_t(1)<<bit;}
    }
    return a<0 ? -(int64_t)q : (int64_t)q;
}
int32_t rounded(int64_t x, unsigned bits) {
    uint64_t a=x<0 ? (uint64_t)(-x) : (uint64_t)x;
    a=(a+(uint64_t(1)<<(bits-1)))>>bits;
    return x<0 ? -(int32_t)a : (int32_t)a;
}
int32_t sat24(int64_t x, uint32_t &clipped) {
    if(x>8388607) { ++clipped; return 8388607; }
    if(x<-8388608) { ++clipped; return -8388608; }
    return (int32_t)x;
}
int32_t logq(uint64_t v) {
    if(!v) v=1;
    unsigned exponent=0;
    for(unsigned i=0;i<64;++i) if(v>>i) exponent=i;
    unsigned index=(unsigned)(((v-(uint64_t(1)<<exponent))<<8)>>exponent);
    return (int32_t)(exponent*4096)+LOG2_Q12[index];
}
uint64_t variance(int64_t sum,uint64_t squares,unsigned n) {
#pragma HLS INLINE
    int64_t mean=divide(sum,n);
    int64_t residual=sum-mean*n;
    int64_t centered=(int64_t)squares-2*mean*sum+mean*mean*n;
    int64_t whole=divide(centered,n), remainder=centered-whole*n;
    if(remainder*n<residual*residual) --whole;
    return whole>0 ? (uint64_t)whole : 0;
}
}

extern "C" void z15_fbcsp(const int32_t *samples,const int32_t *params,
                          int32_t *result,unsigned count,unsigned reset) {
#pragma HLS INTERFACE m_axi port=samples offset=slave bundle=data depth=512
#pragma HLS INTERFACE m_axi port=params offset=slave bundle=model depth=94
#pragma HLS INTERFACE m_axi port=result offset=slave bundle=data depth=16
#pragma HLS INTERFACE s_axilite port=samples bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=params bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=result bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=count bundle=control offset=0x40
#pragma HLS INTERFACE s_axilite port=reset bundle=control offset=0x48
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS ALLOCATION operation instances=mul limit=4
#pragma HLS ALLOCATION instances=divide limit=1 function
    static int32_t history[3][2][8][4];
    static int32_t ring[6][MAX_WINDOW];
#pragma HLS BIND_STORAGE variable=ring type=ram_t2p impl=bram
#pragma HLS ARRAY_PARTITION variable=ring complete dim=1
    static int64_t sums[6];
    static uint64_t squares[6];
    static unsigned position=0,total=0,windows=0,clipped=0,signature=0;
    static bool configured=false;
    int32_t p[94],features[6]={0,0,0,0,0,0};
    unsigned hash=2166136261u;
    for(unsigned i=0;i<94;++i) { p[i]=params[i]; hash=(hash^(uint32_t)p[i])*16777619u; }
    unsigned n=(unsigned)p[2],hop=(unsigned)p[3];
    unsigned flags=0;
    int64_t score=0;
    for(unsigned i=0;i<16;++i) result[i]=0;
    result[0]=(int32_t)MAGIC;
    if((unsigned)p[0]!=MAGIC || p[1]!=1 || n<4 || n>MAX_WINDOW || hop<1 || hop>n
       || p[4]!=8 || p[5]!=3 || p[6]!=2 || p[7]!=250 || count>64 || count>hop) {
        result[1]=8; return;
    }
    for(unsigned i=0;i<count*8;++i) if(samples[i]<-8388608 || samples[i]>8388607) {
        result[1]=8;return;
    }
    if(reset) {
        for(unsigned b=0;b<3;++b) for(unsigned s=0;s<2;++s)
            for(unsigned c=0;c<8;++c) for(unsigned h=0;h<4;++h) history[b][s][c][h]=0;
        for(unsigned c=0;c<6;++c) {
            sums[c]=0;squares[c]=0;
            for(unsigned i=0;i<MAX_WINDOW;++i) ring[c][i]=0;
        }
        position=total=windows=clipped=0; signature=hash; configured=true;
    }
    if(!configured || signature!=hash || total>0xffffffffu-count) { result[1]=8;return; }
    for(unsigned sample=0;sample<count;++sample) {
        int32_t z[6];
        for(unsigned band=0;band<3;++band) {
            int32_t filtered[8];
            for(unsigned channel=0;channel<8;++channel) {
                int32_t x=samples[sample*8+channel];
                for(unsigned section=0;section<2;++section) {
                    unsigned k=8+(band*2+section)*5;
                    int64_t acc=(int64_t)p[k]*x+(int64_t)p[k+1]*history[band][section][channel][0]
                        +(int64_t)p[k+2]*history[band][section][channel][1]
                        -(int64_t)p[k+3]*history[band][section][channel][2]
                        -(int64_t)p[k+4]*history[band][section][channel][3];
                    // Shift in 64 bits before saturation: the rounded value may exceed int32.
                    uint64_t mag=acc<0 ? (uint64_t)(-acc) : (uint64_t)acc;
                    int64_t value=(int64_t)((mag+(uint64_t(1)<<27))>>28);
                    int32_t y=sat24(acc<0 ? -value : value,clipped);
                    history[band][section][channel][1]=history[band][section][channel][0];
                    history[band][section][channel][0]=x;
                    history[band][section][channel][3]=history[band][section][channel][2];
                    history[band][section][channel][2]=y;x=y;
                }
                filtered[channel]=x;
            }
            for(unsigned component=0;component<2;++component) {
                int64_t acc=0;
                for(unsigned channel=0;channel<8;++channel)
                    acc+=(int64_t)p[38+(band*2+component)*8+channel]*filtered[channel];
                uint64_t mag=acc<0 ? (uint64_t)(-acc) : (uint64_t)acc;
                int64_t value=(int64_t)((mag+8192)>>14);
                z[band*2+component]=sat24(acc<0 ? -value : value,clipped);
            }
        }
        for(unsigned c=0;c<6;++c) {
            int64_t old=ring[c][position],value=z[c];
            sums[c]+=value-old;
            squares[c]=(uint64_t)((int64_t)squares[c]+value*value-old*old);
            ring[c][position]=z[c];
        }
        if(++position==n) position=0;
        ++total;
        if(total>=n && (total-n)%hop==0) {
            bool energy=true;
            for(unsigned band=0;band<3;++band) {
                uint64_t a=variance(sums[band*2],squares[band*2],n);
                uint64_t b=variance(sums[band*2+1],squares[band*2+1],n);
                if(a+b==0) energy=false;
                if(!a)a=1;if(!b)b=1;
                int32_t den=logq(a+b);
                features[band*2]=logq(a)-den;features[band*2+1]=logq(b)-den;
            }
            uint64_t bits=(uint32_t)p[92]|((uint64_t)(uint32_t)p[93]<<32);
            score=(int64_t)bits;
            for(unsigned c=0;c<6;++c) score+=(int64_t)p[86+c]*features[c];
            ++windows;flags=1|(energy && !clipped ? 2 : 0);
        }
    }
    if(clipped) flags|=4;
    result[1]=(int32_t)flags;result[2]=(int32_t)total;result[3]=(int32_t)windows;
    result[4]=score>=0 ? 1 : 0;result[5]=(int32_t)(uint32_t)score;
    result[6]=(int32_t)(uint32_t)((uint64_t)score>>32);result[7]=(int32_t)clipped;
    for(unsigned c=0;c<6;++c) result[8+c]=features[c];
}
