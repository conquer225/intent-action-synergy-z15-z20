/* Software ownership model; does not pretend to simulate vendor VDMA RTL. */
#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include "video_mock/mock_hw.h"
static int current[2][2],started[2][2],requested,completed[2],capture_live,copies;
static int display_started,freeze_capture,freeze_live,freeze_display,latest_complete;
static u32 faults[2][2],cam_count,hdmi_count;static XTime tick,camera_ready,next_camera,next_display;
static int bad_id=-1,bad_count,fail_display,fail_park;static char last_message[512];
static void *copy_frame(void*,const void*,size_t);static void *clear_frame(void*,int,size_t);
#define memcpy copy_frame
#define memset clear_frame
#include "../src/app/video_live.c"
#undef memcpy
#undef memset
static XAxiVdma_Config configs[2]={{XPAR_AXIVDMA_0_BASEADDR},{XPAR_AXIVDMA_1_BASEADDR}};
void xil_printf(const char *f,...) {va_list a;va_start(a,f);vsnprintf(last_message,sizeof(last_message),f,a);va_end(a);}
XAxiVdma_Config *XAxiVdma_LookupConfig(int id) {return id==bad_id?NULL:&configs[id];}
int XAxiVdma_CfgInitialize(XAxiVdma*d,XAxiVdma_Config*c,UINTPTR base) {
    (void)c;d->MockId=base==XPAR_AXIVDMA_1_BASEADDR;d->MaxNumFrames=bad_count?1:(d->MockId?2:3);return 0;
}
int XAxiVdma_DmaConfig(XAxiVdma*d,int dir,XAxiVdma_DmaSetup*c) {
    assert(c->Stride==3840 && c->VertSizeInput==720 && c->HoriSizeInput==3840);
    assert(c->EnableSync==!d->MockId && c->EnableCircularBuf);
    if(d->MockId)assert(dir==XAXIVDMA_WRITE);
    return 0;
}
int XAxiVdma_DmaSetBufferAddr(XAxiVdma*d,int dir,UINTPTR*a) {
    (void)dir;assert(a[0]==(d->MockId?CAPTURE_BASE:DISPLAY_BASE));
    for(int i=1;i<d->MaxNumFrames;i++)assert(a[i]-a[i-1]==VIDEO_BYTES);
    return 0;
}
int XAxiVdma_DmaStart(XAxiVdma*d,int dir) {started[d->MockId][dir]=1;return 0;}
int XAxiVdma_StartParking(XAxiVdma*d,int frame,int dir) {
    assert(d->MockId==1 && dir==XAXIVDMA_WRITE && frame<2);
    if(fail_park)return 55;
    requested=frame;return 0;
}
u32 XAxiVdma_CurrFrameStore(XAxiVdma*d,int dir) {return current[d->MockId][dir];}
u32 live_osd_display_frames(void) {return hdmi_count;}
u32 live_osd_camera_frames(void) {return cam_count;}
void XTime_GetTime(XTime*t) {*t=tick;}
void usleep(unsigned n) {
    XTime end=tick+n;
    while(next_camera<=end || next_display<=end) {
        if(next_camera<=next_display) {
            tick=next_camera;next_camera+=50000;
            if(tick<camera_ready)continue;
            cam_count++;
            if(started[0][1] && !freeze_live) {
                latest_complete=current[0][1];int next=(latest_complete+1)%3;
                if(next==current[0][0])next=(next+1)%3;
                current[0][1]=next;
            }
            if(started[1][1] && !freeze_capture) {
                if(capture_live)completed[current[1][1]]=1;
                capture_live=1;current[1][1]=requested;
            }
        } else {
            tick=next_display;next_display+=16667;
            if(started[0][0] && display_started && !freeze_display) {
                hdmi_count++;if(latest_complete>=0)current[0][0]=latest_complete;
            }
        }
    }
    tick=end;
}
u32 Xil_In32(UINTPTR p) {
    int id=p>=XPAR_AXIVDMA_1_BASEADDR;UINTPTR off=p-configs[id].BaseAddress;
    assert(off==4 || off==0x34);int dir=off==0x34;
    return 0x11000u|faults[id][dir];
}
int DisplayInitialize(DisplayCtrl*d,int id) {(void)d;(void)id;return fail_display?55:0;}
int DisplaySetMode(DisplayCtrl*d,const VideoMode*m) {(void)d;(void)m;return 0;}
int DisplayStart(DisplayCtrl*d) {(void)d;display_started=1;return 0;}
static void *clear_frame(void*d,int v,size_t n) {
    if((UINTPTR)d==DISPLAY_BASE) {assert(!started[0][0]&&!started[0][1]&&n==3*VIDEO_BYTES);return d;}
    return memset(d,v,n);
}
static void *copy_frame(void*d,const void*s,size_t n) {
    assert((UINTPTR)d==SNAPSHOT_BASE && n==VIDEO_BYTES);
    int slot=((UINTPTR)s-CAPTURE_BASE)/VIDEO_BYTES;
    assert(slot>=0 && slot<2 && slot!=current[1][1] && completed[slot]);
    // Simulate a slow copy. Parked writer must remain off source throughout.
    usleep(75000);assert(slot!=current[1][1]);copies++;return d;
}
void Xil_DCacheInvalidateRange(UINTPTR p,u32 n) {assert(n==VIDEO_BYTES && p!=CAPTURE_BASE+current[1][1]*VIDEO_BYTES);}
void Xil_DCacheFlushRange(UINTPTR p,u32 n) {assert(p==DISPLAY_BASE&&n==3*VIDEO_BYTES&&!started[0][0]&&!started[0][1]);}
static void reset(void) {
    memset(current,0,sizeof(current));memset(started,0,sizeof(started));memset(completed,0,sizeof(completed));memset(faults,0,sizeof(faults));
    requested=capture_live=copies=display_started=freeze_capture=freeze_live=freeze_display=0;
    tick=camera_ready=0;cam_count=hdmi_count=0;next_camera=50000;next_display=16667;latest_complete=-1;
    bad_id=-1;bad_count=fail_display=fail_park=0;last_message[0]=0;
}
int main(void) {
    unsigned delays[]={600000,1200000,2900000};
    for(unsigned i=0;i<3;i++) {reset();camera_ready=delays[i];assert(video_init());assert(tick>=delays[i]);assert(video_snapshot());}
    reset();assert(video_init());u32 before=hdmi_count;usleep(2000000);
    assert(hdmi_count-before>=119 && copies==0);assert(video_present(video_work_frame()));
    for(int i=0;i<5;i++){assert(video_snapshot());usleep(650000);assert(video_present(video_work_frame()));}
    assert(copies==5);
    reset();freeze_capture=1;assert(!video_init());assert(tick>=3000000 && strstr(last_message,"rx-prime-1"));
    reset();freeze_live=1;assert(!video_init());assert(strstr(last_message,"live-prime"));
    reset();freeze_display=1;assert(!video_init());assert(strstr(last_message,"live-prime"));
    reset();assert(video_init());freeze_capture=1;before=hdmi_count;assert(!video_snapshot());assert(hdmi_count>before);
    reset();assert(video_init());freeze_display=1;usleep(500000);assert(!video_present(video_work_frame()));
    for(int id=0;id<2;id++){reset();bad_id=id;assert(!video_init());}
    reset();bad_count=1;assert(!video_init());reset();fail_display=1;assert(!video_init());
    reset();fail_park=1;assert(!video_init());
    reset();assert(video_init());faults[1][1]=0x10;assert(!video_snapshot());
    reset();assert(video_init());faults[0][0]=1;assert(!video_present(video_work_frame()));
    reset();tick=((XTime)UINT32_MAX-100)*1000;next_camera=tick+50000;next_display=tick+16667;freeze_capture=1;
    assert(!video_init());assert(strstr(last_message,"rx-prime-1"));
    puts("PASS independent live/snapshot ownership: PS stalls, 75ms copy, warmup, missing streams, faults, wrap (software model)");return 0;
}
