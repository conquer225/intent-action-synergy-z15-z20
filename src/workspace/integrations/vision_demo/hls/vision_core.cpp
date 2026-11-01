// SPDX-License-Identifier: MIT
// RGB8 packed as 0x00RRGGBB. History is per-pixel grey | (trail << 8).
// The host resets history on every source/mode/gap transition.
#include <stdint.h>

static const unsigned MAX_WIDTH = 640, MAX_HEIGHT = 480;
static unsigned gray(uint32_t rgb) {
    return (77*((rgb>>16)&255)+150*((rgb>>8)&255)+29*(rgb&255)+128)>>8;
}
static unsigned minimum(unsigned x, unsigned y) { return x<y?x:y; }
static unsigned absolute(int x) { return x<0?unsigned(-x):unsigned(x); }
static uint32_t mono(unsigned x) { return (x<<16)|(x<<8)|x; }
static uint32_t colour(unsigned x) {
    return (minimum(x*2,255)<<16)|(x<<8)|minimum(x*3,255);
}

extern "C" uint32_t vision_core(const uint32_t *input_pixels, uint32_t *output_pixels,
    uint32_t *history, unsigned width, unsigned height, unsigned mode,
    unsigned reset_history, unsigned threshold) {
#pragma HLS INTERFACE m_axi port=input_pixels offset=slave bundle=memory depth=307200 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=output_pixels offset=slave bundle=memory depth=307200 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=history offset=slave bundle=history_bus depth=307200
#pragma HLS INTERFACE s_axilite port=input_pixels bundle=control
#pragma HLS INTERFACE s_axilite port=output_pixels bundle=control
#pragma HLS INTERFACE s_axilite port=history bundle=control
#pragma HLS INTERFACE s_axilite port=width bundle=control
#pragma HLS INTERFACE s_axilite port=height bundle=control
#pragma HLS INTERFACE s_axilite port=mode bundle=control
#pragma HLS INTERFACE s_axilite port=reset_history bundle=control
#pragma HLS INTERFACE s_axilite port=threshold bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    if (!width || width>MAX_WIDTH || !height || height>MAX_HEIGHT) return 1;
    if (mode>9 || threshold>255) return 2;
    uint32_t rows[3][MAX_WIDTH];
#pragma HLS ARRAY_PARTITION variable=rows complete dim=1
    unsigned histogram[256];
    unsigned char lookup[256];
    const unsigned total=width*height;
    if (mode==8) {
        for (unsigned i=0;i<256;i++) histogram[i]=0;
        for (unsigned i=0;i<total;i++) histogram[gray(input_pixels[i])]++;
        unsigned first=0;
        while (first<255 && histogram[first]==0) first++;
        unsigned denominator=total-histogram[first], sum=0;
        for (unsigned i=0;i<256;i++) {
            if (!denominator) lookup[i]=(unsigned char)i;
            else if (i<=first) lookup[i]=0;
            else {
                sum+=histogram[i];
                unsigned numerator=sum*255, value=numerator/denominator;
                unsigned remainder=numerator%denominator;
                // OpenCV rounds to nearest with ties to even.
                if (remainder*2>denominator || (remainder*2==denominator && (value&1))) value++;
                lookup[i]=(unsigned char)value;
            }
        }
    }
    for (unsigned x=0;x<width;x++) rows[0][x]=input_pixels[x];
    if (height>1) for (unsigned x=0;x<width;x++) rows[1][x]=input_pixels[width+x];
    for (unsigned y=0;y<height;y++) {
        if (y+1>=2 && y+1<height)
            for (unsigned x=0;x<width;x++) rows[(y+1)%3][x]=input_pixels[(y+1)*width+x];
        for (unsigned x=0;x<width;x++) {
            unsigned i=y*width+x;
            uint32_t rgb=rows[y%3][x];
            unsigned g=gray(rgb), old=history[i];
            unsigned delta=reset_history?0:absolute(int(g)-int(old&255));
            unsigned decayed=reset_history?0:(((old>>8)&255)*7)>>3;
            unsigned trail=delta>decayed?delta:decayed;
            uint32_t result=mono(g);
            if (mode==0) result=rgb&0xFFFFFF;
            else if (mode==2 || mode==3) {
                unsigned value=mode==2?trail:delta;
                result=value>16?colour(value):mono(g>>2);
            } else if (mode==5) result=mono(g>threshold?255:0);
            else if (mode==8) result=mono(lookup[g]);
            else if (mode==1 || mode==6 || mode==7) {
                unsigned window[9];
#pragma HLS ARRAY_PARTITION variable=window complete
                for (int dy=-1;dy<=1;dy++) {
                    int yy=int(y)+dy;
                    if(yy<0)yy=0; if(yy>=int(height))yy=int(height)-1;
                    for (int dx=-1;dx<=1;dx++) {
                        int xx=int(x)+dx;
                        if(xx<0)xx=0; if(xx>=int(width))xx=int(width)-1;
                        window[(dy+1)*3+dx+1]=gray(rows[yy%3][xx]);
                    }
                }
                if (mode==6) {
                    for(unsigned a=0;a<8;a++) for(unsigned b=a+1;b<9;b++)
                        if(window[b]<window[a]) {unsigned v=window[a];window[a]=window[b];window[b]=v;}
                    result=mono(window[4]);
                } else {
                    int gx=-int(window[0])+int(window[2])-2*int(window[3])+2*int(window[5])-int(window[6])+int(window[8]);
                    int gy=-int(window[0])-2*int(window[1])-int(window[2])+int(window[6])+2*int(window[7])+int(window[8]);
                    unsigned edge=minimum(absolute(gx)+absolute(gy),255);
                    result=mode==1?colour(edge<32?0:edge):mono(edge);
                }
            }
            history[i]=g|(trail<<8);
            output_pixels[i]=result;
        }
    }
    return 0;
}
