#ifndef Z15_NET_CONTROL_H
#define Z15_NET_CONTROL_H
#include "net_protocol.h"
enum {NET_SOURCE_LOCAL=0,NET_SOURCE_PC=1};
typedef struct {
    EyeTracker eye;
    Localization last,anchor;
    EyeFaceBox crop_face; /* stable crop until detected face approaches its edge */
    NetFrame pending;
    u32 session,sequence,sampled_ms,last_sample_ms,last_result_ms,accepted,rejected,timeouts;
    u32 detect_ms,period_ms;
    int source,stable,waiting,have_sample;
} NetControl;
void net_control_init(NetControl *c);
void net_control_reset(NetControl *c);
int net_control_source(NetControl *c,int source);
int net_control_crop(NetControl *c,const u8 *image,u32 stride,u32 width,u32 height,u32 sampled,u8 *pixels,NetFrame *out);
void net_control_begin(NetControl *c,const NetFrame *f,u32 session,u32 sequence,u32 sampled);
int net_control_result(NetControl *c,const NetPacket *p,u32 now);
int net_control_timeout(NetControl *c,u32 now);
int net_control_command(NetControl *c,char command,u32 now);
void net_control_local(NetControl *c,const u8 *frame,u32 stride,u32 width,u32 height,const Localization *detected,u32 sampled,u32 elapsed);
#endif
