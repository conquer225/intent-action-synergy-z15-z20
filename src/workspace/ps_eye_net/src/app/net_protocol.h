#ifndef Z15_NET_PROTOCOL_H
#define Z15_NET_PROTOCOL_H
#include "auto_face.h"
#define NET_PORT 5001u
#define NET_HEADER 24u
#define NET_MTU 1200u
#define NET_CHUNK 1100u
#define NET_FRAME_META 60u
#define NET_RESULT_BYTES 80u
#define NET_MAX_W 640u
#define NET_MAX_H 480u
#define NET_MAX_IMAGE (NET_MAX_W*NET_MAX_H*3u)
#define NET_RESULT_TIMEOUT 220u
#define NET_PEER_TIMEOUT 1500u
enum {NET_HELLO=1,NET_FRAME=2,NET_RESULT=3,NET_COMMAND=4,NET_STATUS=5};
enum {NET_SEARCH=1,NET_ANCHORED=2,NET_JPEG=4};
typedef struct {u8 type;u32 session,sequence,sampled_ms;u16 size;const u8 *payload;} NetPacket;
typedef struct {
    u16 x,y,w,h,image_w,image_h,camera_w,camera_h;
    Localization anchor;
    u32 flags,total,image_crc,offset;
    u16 index,count;
} NetFrame;
typedef struct {EyeRoi detected,analyzed;u32 x_q8,y_q8;u8 valid,quality,contrast,reason;u16 selected,samples;} NetEye;
typedef struct {EyeFaceBox face;NetEye left,right;u32 process_ms,flags;} NetResult;
u16 net_u16(const u8 *p);
u32 net_u32(const u8 *p);
void net_put16(u8 *p,u16 value);
void net_put32(u8 *p,u32 value);
u32 net_crc32(const u8 *data,u32 length);
int net_encode(u8 *dst,u8 type,u32 session,u32 seq,u32 sampled,const u8 *payload,u16 length);
int net_decode(const u8 *data,u32 length,NetPacket *out);
void net_frame_encode(u8 *p,const NetFrame *frame);
int net_result_decode(const u8 *p,u32 size,NetResult *out);
int net_crop(const u8 *bgr,u32 stride,u32 width,u32 height,const EyeFaceBox *face,u8 *dst,NetFrame *out);
#endif
