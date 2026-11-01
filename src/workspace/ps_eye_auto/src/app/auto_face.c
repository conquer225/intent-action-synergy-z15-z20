#include "auto_face.h"
#include <string.h>
#include <stdlib.h>
static u8 small[HAAR_MAX_W*HAAR_MAX_H];
static u8 equalized[HAAR_MAX_W*HAAR_MAX_H];
static u8 upper[240*168];
static void equalize(const u8 *src,u8 *dst,int n)
{
    unsigned hist[256]={0},cumulative=0,first=0; u8 lut[256];
    for(int i=0;i<n;i++) hist[src[i]]++;
    for(int i=0;i<256;i++) if(hist[i]) { first=hist[i]; break; }
    if(first==(unsigned)n) { memcpy(dst,src,n); return; }
    for(int i=0;i<256;i++) {
        cumulative+=hist[i];
        lut[i]=(u8)(cumulative<=first?0:((cumulative-first)*255+(n-first)/2)/(n-first));
    }
    for(int i=0;i<n;i++) dst[i]=lut[src[i]];
}
static void crop_gray(const u8 *bgr,int stride,int x,int y,int w,int h,u8 *dst,int dw,int dh)
{
    /* Four spatial samples reduce aliasing; operate on original capture pixels. */
    for(int j=0;j<dh;j++) for(int i=0;i<dw;i++) {
        unsigned sum=0;
        for(int yy=0;yy<2;yy++) for(int xx=0;xx<2;xx++) {
            int sy=y+((4*j+1+2*yy)*h)/(4*dh),sx=x+((4*i+1+2*xx)*w)/(4*dw);
            const u8 *p=bgr+sy*stride+sx*3;
            sum+=(29u*p[0]+150u*p[1]+77u*p[2])>>8;
        }
        dst[j*dw+i]=(u8)((sum+2)/4);
    }
}
static EyeRoi eye_roi(Detection e,int fx,int fy,int fw,int upper_h)
{
    /* Wider spatial coverage, including above the old lower-half crop. */
    int x=fx+(20*e.x-e.w)*fw/4800;
    int y=fy+(10*e.y+e.h)*upper_h/1680;
    int x1=fx+(20*e.x+21*e.w)*fw/4800;
    int y1=fy+(10*e.y+9*e.h)*upper_h/1680;
    if(x<fx) x=fx;
    if(y<fy) y=fy;
    if(x1>fx+fw) x1=fx+fw;
    if(y1>fy+upper_h) y1=fy+upper_h;
    return (EyeRoi){(u16)x,(u16)y,(u16)(x1-x),(u16)(y1-y),24,80};
}
int auto_localize(const u8 *bgr,u32 stride,u32 width,u32 height,Localization *out)
{
    Detection faces[16],eyes[16]; int sw=320,sh;
    if(!out) return 0;
    memset(out,0,sizeof(*out));
    if(!bgr||width<64||height<64||width>4096||height>4096||stride<width*3||stride>65536) return 0;
    sh=(int)(height*sw/width);
    if(sh>240) { sh=240; sw=(int)(width*sh/height); }
    crop_gray(bgr,(int)stride,0,0,(int)width,(int)height,small,sw,sh);
    equalize(small,equalized,sw*sh);
    int n=haar_detect(equalized,sw,sh,sw,0,36,sh,3,faces,16);
    if(n==0) n=haar_detect(equalized,sw,sh,sw,2,36,sh,3,faces,16);
    out->faces=n>0?n:0;
    /* Prefer largest face (seated foreground user), require a detected eye pair. */
    for(int i=0;i<n;i++) for(int j=i+1;j<n;j++) if(faces[j].w>faces[i].w) {
        Detection t=faces[i]; faces[i]=faces[j]; faces[j]=t;
    }
    for(int f=0;f<n && f<3;f++) {
        int fx=faces[f].x*(int)width/sw,fy=faces[f].y*(int)height/sh;
        int fw=faces[f].w*(int)width/sw,fh=faces[f].h*(int)height/sh;
        if(fx<0||fy<0||fx+fw>(int)width||fy+fh>(int)height) continue;
        int uh=fh*7/10;
        crop_gray(bgr,(int)stride,fx,fy,fw,uh,upper,240,168);
        equalize(upper,upper,240*168);
        int ne=haar_detect(upper,240,168,240,1,24,84,3,eyes,16);
        int best=-1,bi=-1,bj=-1;
        for(int i=0;i<ne;i++) for(int j=0;j<ne;j++) {
            Detection a=eyes[i],b=eyes[j];
            int ax=a.x+a.w/2,ay=a.y+a.h/2,bx=b.x+b.w/2,by=b.y+b.h/2;
            if(ax>=115||bx<=125||bx-ax<60||bx-ax>170||abs(ay-by)>24) continue;
            if(ay<45||ay>143||by<45||by>143||a.x+a.w>=b.x) continue;
            if(a.w*2<b.w||b.w*2<a.w) continue;
            int score=a.neighbors+b.neighbors-abs(ay-by);
            if(score>best) { best=score; bi=i; bj=j; }
        }
        if(bi<0) continue;
        out->left=eye_roi(eyes[bi],fx,fy,fw,uh); out->right=eye_roi(eyes[bj],fx,fy,fw,uh);
        if(out->left.w<16||out->right.w<16||out->left.h<8||out->right.h<8||
           out->left.x+out->left.w>=out->right.x) continue;
        out->face=(EyeFaceBox){fx,fy,fw,fh,1}; out->valid=1; out->eye_count=2;
        return 1;
    }
    return 0;
}
int localization_near(const Localization *a,const Localization *b)
{
    int t=a->face.w/12+2;
    return a->valid&&b->valid&&abs((int)a->face.x-b->face.x)<=t&&
        abs((int)a->face.y-b->face.y)<=t&&abs((int)a->face.w-b->face.w)<=t&&
        abs((int)a->face.h-b->face.h)<=t&&
        abs((int)a->left.x-b->left.x)<=t&&abs((int)a->right.x-b->right.x)<=t&&
        abs((int)a->left.y-b->left.y)<=t&&abs((int)a->right.y-b->right.y)<=t&&
        abs((int)a->left.w-b->left.w)<=t&&abs((int)a->right.w-b->right.w)<=t;
}

static int project_roi(const EyeRoi *source,int ax4,int ay4,int bx4,int by4,
                       int scale,u32 width,u32 height,EyeRoi *out)
{
    int x=(bx4*1024+(4*(int)source->x-ax4)*scale+2048)/4096;
    int y=(by4*1024+(4*(int)source->y-ay4)*scale+2048)/4096;
    int w=((int)source->w*scale+512)/1024,h=((int)source->h*scale+512)/1024;
    if(x<0||y<0||w<8||h<6||x+w>(int)width||y+h>(int)height) return 0;
    *out=*source;out->x=(u16)x;out->y=(u16)y;out->w=(u16)w;out->h=(u16)h;
    return 1;
}

static int localization_inside(const Localization *p,u32 width,u32 height)
{
    return p&&p->valid&&p->face.valid&&p->face.w&&p->face.h&&
        (u32)p->face.x+p->face.w<=width&&(u32)p->face.y+p->face.h<=height&&
        p->left.w>=8&&p->right.w>=8&&p->left.h>=6&&p->right.h>=6&&
        (u32)p->left.x+p->left.w<=width&&(u32)p->right.x+p->right.w<=width&&
        (u32)p->left.y+p->left.h<=height&&(u32)p->right.y+p->right.h<=height;
}
int localization_follow(const Localization *a,const Localization *b,
                        u32 width,u32 height,EyeRoi *left,EyeRoi *right)
{
    if(!left||!right||!width||!height||width>4096||height>4096||
       !localization_inside(a,width,height)||!localization_inside(b,width,height)) return 0;
    /* Doubled box centers keep the half-pixel information in integer math. */
    int alx=2*(int)a->left.x+a->left.w,arx=2*(int)a->right.x+a->right.w;
    int aly=2*(int)a->left.y+a->left.h,ary=2*(int)a->right.y+a->right.h;
    int blx=2*(int)b->left.x+b->left.w,brx=2*(int)b->right.x+b->right.w;
    int bly=2*(int)b->left.y+b->left.h,bry=2*(int)b->right.y+b->right.h;
    int ad=arx-alx,bd=brx-blx;
    if(ad<16||bd<16) return 0;
    /* Haar eye boxes can follow iris motion. Their common translation is not
       an independent head-motion estimate: subtracting it can erase gaze.
       Use the face transform, and keep the eye pair only as a pose gate. */
    int scale=((int)b->face.w*1024/a->face.w+(int)b->face.h*1024/a->face.h)/2;
    if(scale<768||scale>1365) return 0;
    if(abs((2*(int)b->face.x+b->face.w)-(2*(int)a->face.x+a->face.w))>a->face.w||
       abs((2*(int)b->face.y+b->face.h)-(2*(int)a->face.y+a->face.h))>a->face.h) return 0;
    if(abs((int)b->face.w*1024-(int)a->face.w*scale)>(int)a->face.w*scale/4||
       abs((int)b->face.h*1024-(int)a->face.h*scale)>(int)a->face.h*scale/4) return 0;
    if(abs(bd*1024-ad*scale)>ad*scale/4) return 0;
    if(abs((bry-bly)*ad-(ary-aly)*bd)>ad*bd/6) return 0;
    /* A detector jump in the eye pair without corresponding facial movement
       is not a head transform. Compare pair centers relative to face centers. */
    int ax4=alx+arx,ay4=aly+ary,bx4=blx+brx,by4=bly+bry;
    int aox=ax4-4*(int)a->face.x-2*(int)a->face.w;
    int aoy=ay4-4*(int)a->face.y-2*(int)a->face.h;
    int box=bx4-4*(int)b->face.x-2*(int)b->face.w;
    int boy=by4-4*(int)b->face.y-2*(int)b->face.h;
    if(abs(box*1024-aox*scale)>(int)a->face.w*scale*2/3||
       abs(boy*1024-aoy*scale)>(int)a->face.h*scale*2/3) return 0;
    EyeRoi l,r;
    int afx4=4*(int)a->face.x+2*(int)a->face.w,afy4=4*(int)a->face.y+2*(int)a->face.h;
    int bfx4=4*(int)b->face.x+2*(int)b->face.w,bfy4=4*(int)b->face.y+2*(int)b->face.h;
    if(!project_roi(&a->left,afx4,afy4,bfx4,bfy4,scale,width,height,&l)||
       !project_roi(&a->right,afx4,afy4,bfx4,bfy4,scale,width,height,&r)||l.x+l.w>=r.x) return 0;
    *left=l;*right=r;return 1;
}
