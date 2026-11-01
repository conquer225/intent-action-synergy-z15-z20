#ifndef AUTO_HAAR_H
#define AUTO_HAAR_H
#include <stdint.h>
#define HAAR_MAX_W 320
#define HAAR_MAX_H 240
#define HAAR_MAX_RESULTS 16
typedef struct { int x,y,w,h,neighbors; } Detection;
typedef struct { uint8_t x,y,w,h; float weight; } HaarRect;
typedef struct { HaarRect rect[3]; uint8_t count; } HaarFeature;
typedef struct { uint16_t first,count; float threshold; } HaarStage;
typedef struct { uint16_t feature; float threshold,left,right; } HaarStump;
typedef struct {
    int w,h,stages;
    const HaarFeature *features;
    const HaarStage *stage;
    const HaarStump *stump;
} HaarModel;
/* Single-threaded static workspace; caller images remain unchanged. */
int haar_detect(const uint8_t *gray, int w,int h,int stride,int eyes,
                int min_size,int max_size,int min_neighbors,Detection *out,int capacity);
void gray_resize(const uint8_t *src,int sw,int sh,int stride,uint8_t *dst,int dw,int dh);
/* Native-size classifier result for differential validation. */
int haar_window(const uint8_t *gray,int stride,int eyes);
#endif
