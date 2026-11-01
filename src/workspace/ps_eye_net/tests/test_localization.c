#include <assert.h>
#include <string.h>
#include "auto_face.h"
static u8 pixels[320*240*3];
int main(void)
{
    Localization loc,a={0},b={0};
    for(int value=0;value<256;value+=51) {
        memset(pixels,value,sizeof(pixels));
        assert(!auto_localize(pixels,960,320,240,&loc));
        assert(!loc.valid&&!loc.eye_count);
    }
    assert(!auto_localize(0,960,320,240,&loc));
    assert(!auto_localize(pixels,100,320,240,&loc));
    assert(!auto_localize(pixels,960,320,0,&loc));
    unsigned rng=123;
    for(unsigned i=0;i<sizeof(pixels);i++) { rng=rng*1664525u+1013904223u; pixels[i]=(u8)(rng>>24); }
    assert(!auto_localize(pixels,960,320,240,&loc));
    a.valid=b.valid=1; a.face=(EyeFaceBox){50,50,120,120,1}; b.face=a.face;
    a.left=b.left=(EyeRoi){70,80,30,15,24,80}; a.right=b.right=(EyeRoi){130,80,30,15,24,80};
    assert(localization_near(&a,&b)); b.face.x+=50; assert(!localization_near(&a,&b));
    b=a; b.left.y+=40; assert(!localization_near(&a,&b));
    b=a; b.right.w+=40; assert(!localization_near(&a,&b));
    b=a; b.valid=0; assert(!localization_near(&a,&b));
    EyeRoi l,r;
    b=a; b.face.x+=25;b.face.y+=18;
    b.left.x+=25;b.right.x+=25;b.left.y+=18;b.right.y+=18;
    assert(!localization_near(&a,&b));
    assert(localization_follow(&a,&b,320,240,&l,&r));
    assert(l.x==95&&l.y==98&&l.w==30&&l.h==15&&r.x==155&&r.y==98);
    b=a; b.face=(EyeFaceBox){60,60,144,144,1};
    b.left=(EyeRoi){84,96,36,18,24,80};b.right=(EyeRoi){156,96,36,18,24,80};
    assert(localization_follow(&a,&b,320,240,&l,&r));
    assert(l.x==84&&l.y==96&&l.w==36&&l.h==18&&r.x==156);
    /* Independent cascade box-size jitter must not rescale the calibrated ROIs. */
    b=a;b.left.x-=4;b.left.w+=8;b.right.x+=3;b.right.w-=6;
    assert(localization_follow(&a,&b,320,240,&l,&r));
    assert(l.x==a.left.x&&l.w==a.left.w&&r.x==a.right.x&&r.w==a.right.w);
    /* A paired eye-box shift with a fixed face must not move the analysis ROI. */
    b=a;b.left.x+=8;b.right.x+=8;
    assert(localization_follow(&a,&b,320,240,&l,&r));
    assert(l.x==a.left.x&&r.x==a.right.x);
    b=a;b.right.y+=20;assert(!localization_follow(&a,&b,320,240,&l,&r));
    b=a;b.right.x+=40;assert(!localization_follow(&a,&b,320,240,&l,&r));
    b=a;b.face.x+=100;assert(!localization_follow(&a,&b,320,240,&l,&r));
    b=a;b.face.w=200;assert(!localization_follow(&a,&b,320,240,&l,&r));
    b=a;b.left.x=65530;l.x=777;
    assert(!localization_follow(&a,&b,320,240,&l,&r)&&l.x==777);
    b=a;b.valid=0;assert(!localization_follow(&a,&b,320,240,&l,&r));
    assert(!localization_follow(&a,&a,80,60,&l,&r));
    assert(!localization_follow(0,&a,320,240,&l,&r));
    Detection d;
    assert(haar_detect(pixels,320,240,320,0,0,240,3,&d,1)==-1);
    assert(haar_detect(pixels,320,240,320,0,1000,2000,3,&d,1)==-1);
    return 0;
}
