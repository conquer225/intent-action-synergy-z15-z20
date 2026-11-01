#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "eye_tracker.h"
#define W 96
#define H 64
static u8 frame[W*H*3];
static const EyeRoi roi={0,0,W,H,24,80};
static void pixel(int x,int y,int g) { memset(frame+(y*W+x)*3,g,3); }
static void disk(int cx,int cy,int r,int g)
{
    for(int y=0;y<H;y++) for(int x=0;x<W;x++)
        if((x-cx)*(x-cx)+(y-cy)*(y-cy)<=r*r) pixel(x,y,g);
}
static EyeFeature analyze(void)
{ EyeFeature f;eye_analyze_rgb888(frame,W*3,W,H,&roi,&f);return f; }
#define REQUIRE(expr) do {if(!(expr)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#expr);return 1;}}while(0)
int main(void)
{
    EyeFeature f;
    /* Underexposed eye: the old min+24 threshold swallowed the background. */
    for(int x=26;x<=70;x+=22) {
        memset(frame,25,sizeof(frame));disk(x,32,12,5);pixel(x-2,30,220);
        f=analyze();REQUIRE(f.valid);REQUIRE(abs((int)f.x-x)<=1);REQUIRE(abs((int)f.y-32)<=1);
        REQUIRE(f.threshold<25);REQUIRE(f.selected_count>300);
        memset(frame,180,sizeof(frame));disk(x,32,12,35);
        f=analyze();REQUIRE(f.valid);REQUIRE(abs((int)f.x-x)<=1);
    }
    memset(frame,25,sizeof(frame));f=analyze();REQUIRE(!f.valid&&f.reason==EYE_FEATURE_CONTRAST);
    memset(frame,100,sizeof(frame));disk(48,32,12,94);f=analyze();REQUIRE(!f.valid);
    memset(frame,100,sizeof(frame));disk(48,32,12,91);f=analyze();REQUIRE(f.valid);
    REQUIRE(abs((int)f.x-48)<=1&&abs((int)f.y-32)<=1);
    /* Isolated black pixel, glint-only patch, noise, edge gradients, eyelid line. */
    memset(frame,90,sizeof(frame));pixel(40,30,0);f=analyze();REQUIRE(!f.valid);
    memset(frame,20,sizeof(frame));disk(48,32,3,250);f=analyze();REQUIRE(!f.valid);
    unsigned seed=7;
    for(unsigned i=0;i<sizeof(frame);i+=3) {seed=seed*1664525u+1013904223u;memset(frame+i,seed>>24,3);}
    f=analyze();REQUIRE(!f.valid);
    for(int y=0;y<H;y++) for(int x=0;x<W;x++) pixel(x,y,10+x);
    f=analyze();REQUIRE(!f.valid);
    memset(frame,80,sizeof(frame));for(int y=15;y<18;y++) for(int x=5;x<90;x++) pixel(x,y,5);
    f=analyze();REQUIRE(!f.valid);
    memset(frame,80,sizeof(frame));disk(28,32,10,5);disk(68,32,10,5);
    f=analyze();REQUIRE(!f.valid&&f.reason==EYE_FEATURE_AMBIGUOUS);
    EyeRoi invalid={65530,0,100,10,24,80};
    REQUIRE(!eye_analyze_rgb888(frame,W*3,W,H,&invalid,&f));REQUIRE(f.reason==EYE_FEATURE_ROI);
    /* A failed partner must not erase measured diagnostics from either eye. */
    EyeTracker t;EyeRoi l={0,0,48,64,24,80},r={48,0,48,64,24,80};
    eye_tracker_init(&t,&l,&r);memset(frame,80,sizeof(frame));disk(24,32,10,5);
    eye_tracker_process(&t,frame,W*3,W,H,100);
    REQUIRE(t.left.valid&&!t.right.valid&&!t.valid&&!t.commit);
    REQUIRE(t.right.reason==EYE_FEATURE_CONTRAST&&t.left.sample_count>0);
    puts("PASS adaptive dark core: exposure/position/glint, negatives and per-eye diagnostics");
    return 0;
}
