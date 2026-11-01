/* Same control state machine on bare metal, Linux ARM and host regression. */
#include "net_control.h"
#include <time.h>
#include <string.h>
static NetControl board;
static NetControl probe;
static u8 probe_packet[NET_HEADER+NET_RESULT_BYTES];
static int probe_accepted;
NetControl *board_control(void){return &board;}
void board_init(void){net_control_init(&board);net_control_init(&probe);probe_accepted=0;}
void board_reset(void){net_control_reset(&board);net_control_reset(&probe);probe_accepted=0;}
int board_source(int source){int changed=net_control_source(&board,source);if(changed){net_control_reset(&probe);probe_accepted=0;}return changed;}
int board_command(unsigned cmd,u32 now){int ok=net_control_command(&board,(char)cmd,now);if(ok){probe.waiting=0;probe_accepted=0;}return ok;}
int board_timeout(u32 now){return net_control_timeout(&board,now);}
int board_waiting(void){return board.waiting;}
int board_packet(const u8 *data,u32 bytes,u32 now){
    NetPacket p;if(!net_decode(data,bytes,&p)){board.rejected++;return 0;}
    return net_control_result(&board,&p,now);
}
static int prepare(NetControl *c,const u8 *image,u32 bytes,u32 sampled,u32 sequence,u32 session,u8 *meta,u8 *pixels){
    if(bytes!=1280u*720u*3u||!image||!meta||!pixels||c->source!=NET_SOURCE_PC)return 0;
    NetFrame f;
    if(!net_control_crop(c,image,3840,1280,720,sampled,pixels,&f))return 0;
    if(c->eye.calibration_mask||c->eye.calibration_stage||c->eye.cal_failed){f.flags|=NET_ANCHORED;f.anchor=c->anchor;}
    net_control_begin(c,&f,session,sequence,sampled);net_frame_encode(meta,&f);return (int)f.total;
}
int board_prepare(const u8 *image,u32 bytes,u32 sampled,u32 sequence,u32 session,u8 *meta,u8 *pixels){return prepare(&board,image,bytes,sampled,sequence,session,meta,pixels);}
int board_probe_prepare(const u8 *image,u32 bytes,u32 sampled,u32 sequence,u32 session,u8 *meta,u8 *pixels){
    net_control_init(&probe);probe.source=NET_SOURCE_PC;probe_accepted=0;
    probe.last=board.last;probe.last_result_ms=board.last_result_ms;
    return prepare(&probe,image,bytes,sampled,sequence,session,meta,pixels);
}
int board_probe_waiting(void){return probe.waiting;}
int board_probe_timeout(u32 now){int expired=net_control_timeout(&probe,now);if(expired)board.timeouts++;return expired;}
int board_probe_packet(const u8 *data,u32 bytes,u32 now){
    NetPacket p;
    if(bytes!=sizeof(probe_packet)||!net_decode(data,bytes,&p)||!net_control_result(&probe,&p,now)){board.rejected++;return 0;}
    memcpy(probe_packet,data,bytes);probe_accepted=1;return 1;
}
int board_probe_promote(u32 now){
    if(!probe_accepted||(u32)(now-probe.sampled_ms)>NET_RESULT_TIMEOUT)return 0;
    NetPacket p;if(!net_decode(probe_packet,sizeof(probe_packet),&p))return 0;
    net_control_source(&board,NET_SOURCE_PC);
    net_control_begin(&board,&probe.pending,probe.session,probe.sequence,probe.sampled_ms);
    probe_accepted=0;return net_control_result(&board,&p,now);
}
void board_pause(void){eye_tracker_pause(&board.eye,EYE_PAUSE_TIMING);board.stable=0;}
int board_local(const u8 *image,u32 bytes,u32 sampled,u32 sequence){
    if(bytes!=1280u*720u*3u||!image)return 0;
    Localization loc;
#ifdef __linux__
    struct timespec begin,end;clock_gettime(CLOCK_MONOTONIC,&begin);
#else
    clock_t started=clock();
#endif
    auto_localize(image,3840,1280,720,&loc);
#ifdef __linux__
    clock_gettime(CLOCK_MONOTONIC,&end);
    u32 elapsed=(u32)(((long long)(end.tv_sec-begin.tv_sec)*1000000000LL+end.tv_nsec-begin.tv_nsec)/1000000);
#else
    u32 elapsed=(u32)((clock()-started)*1000/CLOCKS_PER_SEC);
#endif
    board.sequence=sequence?sequence:board.sequence+1;
    net_control_local(&board,image,3840,1280,720,&loc,sampled,elapsed);return (int)elapsed;
}
unsigned board_status(u32 *out,unsigned capacity){
    EyeTracker *t=&board.eye;
    u32 values[]={board.source,board.last.valid,board.stable,t->calibration_mask,t->calibration_stage,t->cal_failed,
        t->valid,t->direction,t->armed,t->dwell_ms,t->event_seq,board.sequence,t->left.normalized_x,t->right.normalized_x,
        t->left.x,t->left.y,t->right.x,t->right.y,t->left.valid,t->right.valid,t->calibration_count[0],t->calibration_count[1],
        t->calibration[0][0],t->calibration[0][1],t->calibration[0][2],t->calibration[1][0],t->calibration[1][1],t->calibration[1][2],
        t->calibration_paused,t->tracking_reason,t->cal_failure_reason,t->cal_retry_stage,board.detect_ms,board.period_ms,
        board.accepted,board.rejected,board.timeouts,t->commit,board.last_result_ms};
    unsigned n=(unsigned)(sizeof(values)/sizeof(values[0]));if(!out||capacity<n)return n;
    memcpy(out,values,sizeof(values));return n;
}
void board_event_consumed(void){board.eye.commit=0;}
