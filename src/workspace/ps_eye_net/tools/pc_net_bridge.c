/* Stable byte ABI: Python and ARM share protocol bytes, not C struct padding. */
#include "net_protocol.h"
#include <string.h>
static EyeRoi to_camera(const EyeRoi *r,u32 x,u32 y,u32 w,u32 h,u32 iw,u32 ih){
    u32 x0=x+r->x*w/iw,y0=y+r->y*h/ih;
    u32 x1=x+((u32)(r->x+r->w)*w+iw-1)/iw,y1=y+((u32)(r->y+r->h)*h+ih-1)/ih;
    return (EyeRoi){(u16)x0,(u16)y0,(u16)(x1-x0),(u16)(y1-y0),24,80};
}
static int to_image(const EyeRoi *r,u32 x,u32 y,u32 w,u32 h,u32 iw,u32 ih,EyeRoi *out){
    if(r->x<x||r->y<y||(u32)r->x+r->w>x+w||(u32)r->y+r->h>y+h)return 0;
    u32 x0=(r->x-x)*iw/w,y0=(r->y-y)*ih/h;
    u32 x1=((r->x+r->w-x)*iw+w-1)/w,y1=((r->y+r->h-y)*ih+h-1)/h;
    *out=(EyeRoi){(u16)x0,(u16)y0,(u16)(x1-x0),(u16)(y1-y0),24,80};return 1;
}
static void roi_bytes(u8 *p,const EyeRoi *r){net_put16(p,r->x);net_put16(p+2,r->y);net_put16(p+4,r->w);net_put16(p+6,r->h);}
static EyeRoi read_roi(const u8 *p){return (EyeRoi){net_u16(p),net_u16(p+2),net_u16(p+4),net_u16(p+6),24,80};}
static void eye_bytes(u8 *out,const EyeRoi *det,const EyeRoi *roi,const EyeFeature *f,u32 x,u32 y,u32 w,u32 h,u32 iw,u32 ih){
    roi_bytes(out,det);roi_bytes(out+8,roi);
    if(f->valid){
        /* Pixel-center mapping matches the board crop sampler. Identity stays exact. */
        net_put32(out+16,x*256u+(u32)(((u64)f->x_q8+128)*w/iw)-128u);
        net_put32(out+20,y*256u+(u32)(((u64)f->y_q8+128)*h/ih)-128u);
    }
    out[24]=f->valid;out[25]=f->confidence;out[26]=f->contrast;out[27]=f->reason;
    net_put16(out+28,f->selected_count);net_put16(out+30,f->sample_count);
}
int pc_infer(const u8 *image,u32 bytes,const u8 *meta,u8 *result){
    if(!image||!meta||!result)return 0;
    u32 x=net_u16(meta),y=net_u16(meta+2),w=net_u16(meta+4),h=net_u16(meta+6);
    u32 iw=net_u16(meta+8),ih=net_u16(meta+10),cw=net_u16(meta+12),ch=net_u16(meta+14),flags=net_u32(meta+40);
    if(!w||!h||iw<64||ih<64||iw>NET_MAX_W||ih>NET_MAX_H||bytes!=iw*ih*3||x+w>cw||y+h>ch||cw>4096||ch>4096||flags>7)return 0;
    memset(result,0,NET_RESULT_BYTES);
    Localization local,loc,anchor={0};
    if(!auto_localize(image,iw*3,iw,ih,&local))return 1;
    EyeRoi face_roi={local.face.x,local.face.y,local.face.w,local.face.h,24,80};
    EyeRoi fc=to_camera(&face_roi,x,y,w,h,iw,ih);
    loc=(Localization){(EyeFaceBox){fc.x,fc.y,fc.w,fc.h,1},
        to_camera(&local.left,x,y,w,h,iw,ih),to_camera(&local.right,x,y,w,h,iw,ih),1,1,2};
    EyeRoi l=loc.left,r=loc.right;
    int pose=1;
    if(flags&NET_ANCHORED){
        EyeRoi af=read_roi(meta+16);anchor.face=(EyeFaceBox){af.x,af.y,af.w,af.h,1};
        anchor.left=read_roi(meta+24);anchor.right=read_roi(meta+32);anchor.valid=1;
        pose=localization_follow(&anchor,&loc,cw,ch,&l,&r);
    }
    EyeFeature lf={0},rf={0};EyeRoi image_l,image_r;
    if(pose&&to_image(&l,x,y,w,h,iw,ih,&image_l))eye_analyze_rgb888(image,iw*3,iw,ih,&image_l,&lf);
    if(pose&&to_image(&r,x,y,w,h,iw,ih,&image_r))eye_analyze_rgb888(image,iw*3,iw,ih,&image_r,&rf);
    roi_bytes(result,&fc);
    eye_bytes(result+8,&loc.left,&l,&lf,x,y,w,h,iw,ih);
    eye_bytes(result+40,&loc.right,&r,&rf,x,y,w,h,iw,ih);
    net_put32(result+76,1);return 1;
}
unsigned pc_protocol_version(void){return 1;}
