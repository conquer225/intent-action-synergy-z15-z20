#include "haar.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>
#include "face_model.inc"
#include "eye_model.inc"
#include "face_alt_model.inc"
#define PITCH (HAAR_MAX_W+1)
#define MAX_RAW 1024
static uint8_t pyramid[HAAR_MAX_W*HAAR_MAX_H];
static uint32_t integral[(HAAR_MAX_W+1)*(HAAR_MAX_H+1)];
static uint64_t squared[(HAAR_MAX_W+1)*(HAAR_MAX_H+1)];
static Detection raw[MAX_RAW], groups[MAX_RAW];
static int parent[MAX_RAW];
void gray_resize(const uint8_t *src,int sw,int sh,int stride,uint8_t *dst,int dw,int dh)
{
    int y,x;
    for(y=0;y<dh;y++) {
        float fy=(y+0.5f)*sh/dh-0.5f;
        int y0=(int)floorf(fy); float ay=fy-y0;
        if(y0<0) { y0=0; ay=0; }
        if(y0>=sh-1) { y0=sh-1; ay=0; }
        int y1=y0+(y0<sh-1);
        for(x=0;x<dw;x++) {
            float fx=(x+0.5f)*sw/dw-0.5f;
            int x0=(int)floorf(fx); float ax=fx-x0;
            if(x0<0) { x0=0; ax=0; }
            if(x0>=sw-1) { x0=sw-1; ax=0; }
            int x1=x0+(x0<sw-1);
            float a=src[y0*stride+x0]*(1-ax)+src[y0*stride+x1]*ax;
            float b=src[y1*stride+x0]*(1-ax)+src[y1*stride+x1]*ax;
            dst[y*dw+x]=(uint8_t)(a*(1-ay)+b*ay+0.5f);
        }
    }
}
static void sums(const uint8_t *p,int w,int h,int stride)
{
    int y,x;
    memset(integral,0,(w+1)*sizeof(*integral));
    memset(squared,0,(w+1)*sizeof(*squared));
    for(y=0;y<h;y++) {
        uint32_t s=0; uint64_t q=0;
        integral[(y+1)*PITCH]=0; squared[(y+1)*PITCH]=0;
        for(x=0;x<w;x++) {
            uint32_t v=p[y*stride+x]; s+=v; q+=v*v;
            integral[(y+1)*PITCH+x+1]=integral[y*PITCH+x+1]+s;
            squared[(y+1)*PITCH+x+1]=squared[y*PITCH+x+1]+q;
        }
    }
}
static uint32_t sum(int x,int y,int w,int h) {
    return integral[(y+h)*PITCH+x+w]-integral[y*PITCH+x+w]
          -integral[(y+h)*PITCH+x]+integral[y*PITCH+x];
}
static int evaluate(const HaarModel *m,int x,int y)
{
    int nx=x+1,ny=y+1,w=m->w-2,h=m->h-2;
    uint32_t s=sum(nx,ny,w,h);
    uint64_t q=squared[(ny+h)*PITCH+nx+w]-squared[ny*PITCH+nx+w]
              -squared[(ny+h)*PITCH+nx]+squared[ny*PITCH+nx];
    double area=w*h, variance=area*(double)q-(double)s*s;
    if(variance<=area*area*100.0) return -1;
    float norm=(float)(1.0/sqrt(variance));
    for(int st=0;st<m->stages;st++) {
        const HaarStage *stage=m->stage+st;
        double total=0;
        for(int i=0;i<stage->count;i++) {
            const HaarStump *weak=m->stump+stage->first+i;
            const HaarFeature *feature=m->features+weak->feature;
            float value=0;
            for(int j=0;j<feature->count;j++) {
                const HaarRect *r=feature->rect+j;
                value += r->weight*sum(x+r->x,y+r->y,r->w,r->h);
            }
            value*=norm;
            total+=value<weak->threshold?weak->left:weak->right;
        }
        if(total<stage->threshold) return -st;
    }
    return 1;
}
int haar_window(const uint8_t *p,int stride,int eyes) {
    const HaarModel *m=eyes==1?&eye_model:eyes==2?&face_alt_model:&face_model;
    if(!p||stride<m->w) return -1;
    sums(p,m->w,m->h,stride); return evaluate(m,0,0);
}
static int root(int x) { while(parent[x]!=x) { parent[x]=parent[parent[x]]; x=parent[x]; } return x; }
static int similar(Detection a,Detection b) {
    int d=(a.w<b.w?a.w:b.w)/5;
    return abs(a.x-b.x)<=d && abs(a.y-b.y)<=d &&
           abs(a.x+a.w-b.x-b.w)<=d && abs(a.y+a.h-b.y-b.h)<=d;
}
int haar_detect(const uint8_t *gray,int w,int h,int stride,int eyes,
                int min_size,int max_size,int min_neighbors,Detection *out,int capacity)
{
    const HaarModel *m=eyes==1?&eye_model:eyes==2?&face_alt_model:&face_model;
    int count=0,n=0;
    if(!gray||!out||w<1||h<1||w>HAAR_MAX_W||h>HAAR_MAX_H||stride<w||stride>65536||capacity<1||
       eyes<0||eyes>2||min_size<1||max_size<min_size||max_size>HAAR_MAX_W||min_neighbors<1) return -1;
    for(float factor=1.0f;;factor*=1.1f) {
        int win=(int)(m->w*factor+0.5f);
        if(win>max_size) break;
        if(win<min_size) continue;
        int pw=(int)(w/factor+0.5f),ph=(int)(h/factor+0.5f);
        if(pw<m->w||ph<m->h) break;
        gray_resize(gray,w,h,stride,pyramid,pw,ph);
        sums(pyramid,pw,ph,pw);
        int step=factor<2.0f?2:1;
        for(int y=0;y<=ph-m->h;y+=step) for(int x=0;x<=pw-m->w;x+=step) {
            if(evaluate(m,x,y)>0) {
                if(count==MAX_RAW) return -2;
                raw[count++]=(Detection){(int)(x*factor+0.5f),(int)(y*factor+0.5f),win,win,1};
            }
        }
    }
    for(int i=0;i<count;i++) { parent[i]=i; groups[i]=(Detection){0}; }
    for(int i=0;i<count;i++) for(int j=0;j<i;j++)
        if(similar(raw[i],raw[j])) parent[root(i)]=root(j);
    for(int i=0;i<count;i++) {
        Detection *g=groups+root(i); g->x+=raw[i].x; g->y+=raw[i].y;
        g->w+=raw[i].w; g->h+=raw[i].h; g->neighbors++;
    }
    for(int i=0;i<count;i++) {
        Detection *g=groups+i;
        if(g->neighbors<min_neighbors) { g->neighbors=0; continue; }
        int k=g->neighbors; g->x=(g->x+k/2)/k; g->y=(g->y+k/2)/k;
        g->w=(g->w+k/2)/k; g->h=(g->h+k/2)/k;
    }
    for(int i=0;i<count;i++) if(groups[i].neighbors) {
        for(int j=0;j<count;j++) if(i!=j&&groups[j].neighbors>groups[i].neighbors) {
            Detection a=groups[i],b=groups[j]; int d=b.w/5;
            if(a.x>=b.x-d&&a.y>=b.y-d&&a.x+a.w<=b.x+b.w+d&&a.y+a.h<=b.y+b.h+d) {
                groups[i].neighbors=0; break;
            }
        }
    }
    while(n<capacity) {
        int best=-1;
        for(int i=0;i<count;i++) if(groups[i].neighbors>0 && (best<0||groups[i].neighbors>groups[best].neighbors)) best=i;
        if(best<0) break;
        out[n++]=groups[best]; groups[best].neighbors=0;
    }
    return n;
}
