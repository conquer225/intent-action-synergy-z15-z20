/* Test production buffer ownership code against a frame-boundary VDMA model.
   This verifies the software protocol, not the real AXI/VDMA hardware. */
#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include "video_mock/mock_hw.h"
#include "video_io.h"
static int current[2],requested[2],started[2],live,freeze,completed[3],copies;
static u32 fault;
static XTime clock_us;
static XTime camera_ready_us, next_frame_us[2];
static const unsigned frame_period_us[2]={16667,50000};
static char last_message[512];
static const char *fail_stage;
static int frame_count,display_started,freeze_rx,freeze_tx,frame_irq[2];
static XTime stop_rx_us;
static int fails(const char *stage) { return fail_stage && !strcmp(fail_stage,stage); }
void xil_printf(const char *format,...) {
    va_list args;va_start(args,format);
    vsnprintf(last_message,sizeof(last_message),format,args);
    va_end(args);
}
static void *mock_copy(void *dst,const void *src,size_t n);
static void *mock_set(void *dst,int value,size_t n);
#define memcpy mock_copy
#define memset mock_set
#include "../src/app/video_io.c"
#undef memcpy
#undef memset
static XAxiVdma_Config config={XPAR_AXIVDMA_0_BASEADDR};
XAxiVdma_Config *XAxiVdma_LookupConfig(int id) { (void)id; return fails("vdma-lookup")?NULL:&config; }
int XAxiVdma_CfgInitialize(XAxiVdma *d,XAxiVdma_Config *c,UINTPTR b) {
    (void)c;(void)b; d->MaxNumFrames=frame_count; return fails("vdma-init")?55:0;
}
int XAxiVdma_DmaConfig(XAxiVdma *d,int dir,XAxiVdma_DmaSetup *c) {
    (void)d;(void)dir;
    assert(c->Stride==3840&&c->HoriSizeInput==3840&&c->VertSizeInput==720);
    assert(c->EnableSync==0); /* CPU-owned buffers must not be genlocked. */
    return fails(dir==XAXIVDMA_WRITE?"rx-config":"tx-config")?55:0;
}
int XAxiVdma_DmaSetBufferAddr(XAxiVdma *d,int dir,UINTPTR *a) {
    (void)d;assert(a[0]==(dir==XAXIVDMA_WRITE?CAPTURE_BASE:DISPLAY_BASE));
    assert(a[1]-a[0]==VIDEO_BYTES);
    if(d->MaxNumFrames==3)assert(a[2]-a[1]==VIDEO_BYTES);
    return fails(dir==XAXIVDMA_WRITE?"rx-address":"tx-address")?55:0;
}
int XAxiVdma_DmaStart(XAxiVdma *d,int dir) {
    (void)d;
    if(fails(dir==XAXIVDMA_WRITE?"rx-start":"tx-start"))return 55;
    started[dir]=1;return 0;
}
int XAxiVdma_StartParking(XAxiVdma *d,int frame,int dir) {
    (void)d;assert(frame==0||frame==1);
    if(fails(dir==XAXIVDMA_WRITE?"rx-park":"tx-park"))return 55;
    requested[dir]=frame;return 0;
}
u32 XAxiVdma_CurrFrameStore(XAxiVdma *d,int dir) {
    (void)d;return (u32)current[dir];
}
void usleep(unsigned n) {
    clock_us+=n;
    if(freeze)return;
    for(int dir=0;dir<2;dir++) while(next_frame_us[dir]<=clock_us) {
        XTime boundary=next_frame_us[dir];
        next_frame_us[dir]+=frame_period_us[dir];
        if(!started[dir])continue;
        if(dir==XAXIVDMA_WRITE && (freeze_rx || boundary<camera_ready_us ||
           (stop_rx_us && boundary>=stop_rx_us)))continue;
        if(dir==XAXIVDMA_READ && (freeze_tx || !display_started))continue;
        if(dir==XAXIVDMA_WRITE) {
            if(live) { completed[current[dir]]=1;frame_irq[dir]=1; }
            live=1;
        } else frame_irq[dir]=1;
        current[dir]=requested[dir];
    }
}
void XTime_GetTime(XTime *now) { *now=clock_us; }
u32 Xil_In32(UINTPTR p) {
    switch(p-XPAR_AXIVDMA_0_BASEADDR) {
    case 0x34: return 0x10000u | (frame_irq[1]?0x1000u:0) | fault;
    case 0x04: return 0x10000u | (frame_irq[0]?0x1000u:0) | fault;
    case 0x28: return (u32)(current[1]<<24 | current[0]<<16 | requested[1]<<8 | requested[0]);
    case 0x30: return (u32)started[1];
    case 0x00: return (u32)started[0];
    default: assert(0);return 0;
    }
}
int DisplayInitialize(DisplayCtrl *d,int id) { (void)d;(void)id;return fails("display-init")?55:0; }
int DisplaySetMode(DisplayCtrl *d,const VideoMode *m) { (void)d;(void)m;return fails("display-mode")?55:0; }
int DisplayStart(DisplayCtrl *d) {
    (void)d;if(fails("display-start"))return 55;display_started=1;return 0;
}
static void *mock_set(void *dst,int value,size_t n) {
    if((UINTPTR)dst==DISPLAY_BASE) { assert(!started[XAXIVDMA_READ]&&n==3*VIDEO_BYTES);return dst; }
    return memset(dst,value,n);
}
static void *mock_copy(void *dst,const void *src,size_t n) {
    assert(n==VIDEO_BYTES);
    if((UINTPTR)dst==SNAPSHOT_BASE) {
        int slot=((UINTPTR)src-CAPTURE_BASE)/VIDEO_BYTES;
        assert(slot>=0&&slot<2&&slot!=current[XAXIVDMA_WRITE]&&completed[slot]);
        copies++;
    } else {
        int slot=((UINTPTR)dst-DISPLAY_BASE)/VIDEO_BYTES;
        assert(slot>=0&&slot<2&&slot!=current[XAXIVDMA_READ]);
        assert((UINTPTR)src==SNAPSHOT_BASE);
    }
    return dst;
}
void Xil_DCacheInvalidateRange(UINTPTR p,u32 n) {
    assert(n==VIDEO_BYTES&&p!=CAPTURE_BASE+current[XAXIVDMA_WRITE]*VIDEO_BYTES);
}
void Xil_DCacheFlushRange(UINTPTR p,u32 n) {
    if(started[XAXIVDMA_READ])assert(n==VIDEO_BYTES&&p!=DISPLAY_BASE+current[XAXIVDMA_READ]*VIDEO_BYTES);
}
static void reset_mock(void) {
    memset(current,0,sizeof(current));memset(requested,0,sizeof(requested));
    memset(started,0,sizeof(started));memset(completed,0,sizeof(completed));
    live=freeze=copies=0;fault=0;clock_us=0;
    camera_ready_us=0;
    next_frame_us[0]=frame_period_us[0];next_frame_us[1]=frame_period_us[1];
    fail_stage=NULL;frame_count=3;display_started=freeze_rx=freeze_tx=0;
    frame_irq[0]=frame_irq[1]=0;stop_rx_us=0;last_message[0]=0;
}
int main(void) {
    /* Vendor capture waits ten VSYNCs and enables on the next one.
       A realistic cold camera must not be rejected by the runtime deadline. */
    reset_mock();camera_ready_us=600000;
    if(!video_init()) {
        puts("FAIL cold-start: camera becomes ready at 600 ms, but video_init rejected it");
        return 1;
    }
    assert(clock_us>=650000 && copies==0);
    assert(strstr(last_message,"VIDEO_READY"));
    for(unsigned delay=1200000;delay<=2900000;delay+=1700000) {
        reset_mock();camera_ready_us=delay;assert(video_init());
        assert(clock_us>=delay+50000 && copies==0);
        assert(video_snapshot()==(const u8*)SNAPSHOT_BASE);
    }
    reset_mock();freeze_rx=1;assert(!video_init());
    assert(clock_us>=3000000 && clock_us<3100000 && copies==0);
    assert(strstr(last_message,"VIDEO_TIMEOUT stage=rx-prime-1"));
    assert(strstr(last_message,"rx=00010000 tx=00011000"));
    reset_mock();freeze_tx=1;assert(!video_init());
    assert(clock_us>=500000 && clock_us<502000 && copies==0);
    assert(strstr(last_message,"VIDEO_TIMEOUT stage=tx-prime-1"));
    /* Seeing slot 1 once is not enough: a stalled writer must not pass priming. */
    reset_mock();stop_rx_us=100000;assert(!video_init());
    assert(strstr(last_message,"VIDEO_TIMEOUT stage=rx-prime-0") && copies==0);
    reset_mock();frame_count=2;assert(video_init());
    reset_mock();frame_count=1;assert(!video_init());
    assert(strstr(last_message,"stage=vdma-frame-count"));
    reset_mock();frame_count=4;assert(!video_init());
    assert(strstr(last_message,"stage=vdma-frame-count"));
    const char *stages[]={"vdma-lookup","vdma-init","rx-config","tx-config",
        "rx-address","tx-address","rx-start","tx-start","rx-park","tx-park",
        "display-init","display-mode","display-start"};
    for(unsigned i=0;i<sizeof(stages)/sizeof(stages[0]);i++) {
        reset_mock();fail_stage=stages[i];assert(!video_init());
        assert(strstr(last_message,"VIDEO_INIT_FAIL") && strstr(last_message,stages[i]) && copies==0);
    }
    reset_mock();assert(video_init());
    for(int i=0;i<4;i++) {
        assert(video_snapshot()==(const u8*)SNAPSHOT_BASE);
        assert(video_present(video_work_frame()));
    }
    assert(copies==4);
    freeze=1;
    XTime before=clock_us;
    assert(!video_snapshot());assert(clock_us-before>=500000&&copies==4);
    assert(clock_us-before<502000 && strstr(last_message,"stage=rx-snapshot"));
    reset_mock();freeze=1;assert(!video_init());assert(copies==0);
    reset_mock();assert(video_init());fault=XAXIVDMA_SR_HALTED_MASK;
    assert(!video_snapshot());assert(copies==0);
    reset_mock();assert(video_init());fault=0x10;
    assert(!video_present(video_work_frame()));
    reset_mock();assert(video_init());freeze_tx=1;before=clock_us;
    assert(!video_present(video_work_frame()));
    assert(clock_us-before>=500000 && clock_us-before<502000);
    assert(strstr(last_message,"VIDEO_TIMEOUT stage=tx-present"));
    reset_mock();fault=0x20;assert(!video_init());
    assert(clock_us<1000 && strstr(last_message,"VIDEO_FAULT") && copies==0);
    /* Timeout subtraction remains valid across the 32-bit millisecond wrap. */
    reset_mock();clock_us=((XTime)UINT32_MAX-100u)*1000u;freeze_rx=1;
    next_frame_us[0]=clock_us+frame_period_us[0];next_frame_us[1]=clock_us+frame_period_us[1];
    before=clock_us;assert(!video_init());
    assert(clock_us-before>=3000000 && clock_us-before<3100000);
    puts("PASS VDMA cold warmup 600/1200/2900 ms, stage failures, ownership, missing frames, runtime RX/TX timeout, faults and timer wrap (mock)");
    return 0;
}
