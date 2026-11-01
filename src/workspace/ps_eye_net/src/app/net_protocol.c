#include "net_protocol.h"
#include <string.h>
u16 net_u16(const u8 *p){return (u16)((u16)p[0]<<8|p[1]);}
u32 net_u32(const u8 *p){return (u32)p[0]<<24|(u32)p[1]<<16|(u32)p[2]<<8|p[3];}
void net_put16(u8 *p,u16 v){p[0]=(u8)(v>>8);p[1]=(u8)v;}
void net_put32(u8 *p,u32 v){p[0]=(u8)(v>>24);p[1]=(u8)(v>>16);p[2]=(u8)(v>>8);p[3]=(u8)v;}
static u32 crc_table[256];
static int crc_ready;
static u32 crc_update(u32 crc,const u8 *data,u32 n){
    if(!crc_ready){
        for(u32 i=0;i<256;i++){u32 c=i;for(int j=0;j<8;j++)c=(c>>1)^((c&1)?0xedb88320u:0);crc_table[i]=c;}
        crc_ready=1;
    }
    for(u32 i=0;i<n;i++)crc=crc_table[(crc^data[i])&255]^(crc>>8);
    return crc;
}
u32 net_crc32(const u8 *data,u32 n){return crc_update(0xffffffffu,data,n)^0xffffffffu;}
int net_encode(u8 *d,u8 type,u32 session,u32 seq,u32 ms,const u8 *p,u16 n){
    if(!d||n>NET_MTU-NET_HEADER||(!p&&n)||type<1||type>5)return 0;
    memcpy(d,"Z15E",4);d[4]=1;d[5]=type;net_put16(d+6,n);
    net_put32(d+8,session);net_put32(d+12,seq);net_put32(d+16,ms);
    if(n)memcpy(d+NET_HEADER,p,n);
    net_put32(d+20,crc_update(crc_update(0xffffffffu,d,20),d+NET_HEADER,n)^0xffffffffu);
    return NET_HEADER+n;
}
int net_decode(const u8 *d,u32 n,NetPacket *o){
    if(!d||!o||n<NET_HEADER||n>NET_MTU||memcmp(d,"Z15E",4)||d[4]!=1||d[5]<1||d[5]>5||net_u16(d+6)!=n-NET_HEADER)return 0;
    u32 crc=crc_update(crc_update(0xffffffffu,d,20),d+NET_HEADER,n-NET_HEADER)^0xffffffffu;
    if(crc!=net_u32(d+20))return 0;
    *o=(NetPacket){d[5],net_u32(d+8),net_u32(d+12),net_u32(d+16),net_u16(d+6),d+NET_HEADER};return 1;
}
static void put_roi(u8 *p,const EyeRoi *r){net_put16(p,r->x);net_put16(p+2,r->y);net_put16(p+4,r->w);net_put16(p+6,r->h);}
static EyeRoi get_roi(const u8 *p){return (EyeRoi){net_u16(p),net_u16(p+2),net_u16(p+4),net_u16(p+6),24,80};}
void net_frame_encode(u8 *p,const NetFrame *f){
    const u16 dims[]={f->x,f->y,f->w,f->h,f->image_w,f->image_h,f->camera_w,f->camera_h};
    for(int i=0;i<8;i++)net_put16(p+2*i,dims[i]);
    net_put16(p+16,f->anchor.face.x);net_put16(p+18,f->anchor.face.y);
    net_put16(p+20,f->anchor.face.w);net_put16(p+22,f->anchor.face.h);
    put_roi(p+24,&f->anchor.left);put_roi(p+32,&f->anchor.right);
    net_put32(p+40,f->flags);net_put32(p+44,f->total);net_put32(p+48,f->image_crc);
    net_put32(p+52,f->offset);net_put16(p+56,f->index);net_put16(p+58,f->count);
}
static NetEye get_eye(const u8 *p){
    NetEye e;e.detected=get_roi(p);e.analyzed=get_roi(p+8);e.x_q8=net_u32(p+16);e.y_q8=net_u32(p+20);
    e.valid=p[24];e.quality=p[25];e.contrast=p[26];e.reason=p[27];e.selected=net_u16(p+28);e.samples=net_u16(p+30);return e;
}
int net_result_decode(const u8 *p,u32 n,NetResult *o){
    if(!p||!o||n!=NET_RESULT_BYTES)return 0;
    *o=(NetResult){(EyeFaceBox){net_u16(p),net_u16(p+2),net_u16(p+4),net_u16(p+6),0},get_eye(p+8),get_eye(p+40),net_u32(p+72),net_u32(p+76)};
    o->face.valid=o->face.w&&o->face.h;
    return o->left.valid<=1&&o->right.valid<=1&&o->flags<=1;
}
int net_crop(const u8 *src,u32 stride,u32 width,u32 height,const EyeFaceBox *face,u8 *dst,NetFrame *o){
    if(!src||!dst||!o||width<64||height<64||width>4096||height>4096||stride<width*3||stride>65536)return 0;
    *o=(NetFrame){0};o->camera_w=(u16)width;o->camera_h=(u16)height;
    u32 x=0,y=0,w=width,h=height;
    if(face&&face->valid&&face->w>=32&&face->h>=32&&(u32)face->x+face->w<=width&&(u32)face->y+face->h<=height){
        u32 mx=face->w/5,my=face->h/5;
        x=face->x>mx?face->x-mx:0;y=face->y>my?face->y-my:0;
        u32 x1=(u32)face->x+face->w+mx,y1=(u32)face->y+face->h+my;
        if(x1>width)x1=width;
        if(y1>height)y1=height;
        w=x1-x;h=y1-y;
        if(w<64){x=x+ w/2>32?x+w/2-32:0;if(x+64>width)x=width-64;w=64;}
        if(h<64){y=y+ h/2>32?y+h/2-32:0;if(y+64>height)y=height-64;h=64;}
    }else o->flags=NET_SEARCH;
    u32 iw=w,ih=h;
    if(o->flags&NET_SEARCH){iw=(width+1)/2;ih=(height+1)/2;}
    if(iw>NET_MAX_W){ih=ih*NET_MAX_W/iw;iw=NET_MAX_W;}
    if(ih>NET_MAX_H){iw=iw*NET_MAX_H/ih;ih=NET_MAX_H;}
    if(iw<64)iw=64;
    if(ih<64)ih=64;
    o->x=(u16)x;o->y=(u16)y;o->w=(u16)w;o->h=(u16)h;o->image_w=(u16)iw;o->image_h=(u16)ih;
    o->total=iw*ih*3;o->count=(u16)((o->total+NET_CHUNK-1)/NET_CHUNK);
    /* Native crop has an exact 1:1 path; search/downsize uses pixel centers. */
    for(u32 j=0;j<ih;j++)for(u32 i=0;i<iw;i++){
        u32 sx=x+((2*i+1)*w)/(2*iw),sy=y+((2*j+1)*h)/(2*ih);
        memcpy(dst+3*(j*iw+i),src+sy*stride+3*sx,3);
    }
    o->image_crc=net_crc32(dst,o->total);return 1;
}
