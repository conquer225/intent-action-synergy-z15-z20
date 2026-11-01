#include "video_io.h"
#include "live_osd.h"
#include <string.h>
#include "xparameters.h"
#include "xaxivdma.h"
#include "xil_io.h"
#include "xil_cache.h"
#include "xtime_l.h"
#include "sleep.h"
#include "xil_printf.h"
#include "display_ctrl_hdmi/display_ctrl_hdmi.h"
#define CAPTURE_BASE 0x02000000u
#define DISPLAY_BASE 0x03000000u
#define SNAPSHOT_BASE 0x04000000u
/* VDMA0: autonomous triple-buffer video; VDMA1: independent parked snapshot. */
static XAxiVdma live_dma,capture_dma;
static DisplayCtrl display;
static int capture_index;
static u32 last_display_count,last_display_ms;
u32 video_now_ms(void) { XTime t;XTime_GetTime(&t);return (u32)(t/(COUNTS_PER_SECOND/1000u)); }
u32 video_rx_status(void) { return Xil_In32(XPAR_AXIVDMA_1_BASEADDR+0x34); }
u32 video_tx_status(void) { return Xil_In32(XPAR_AXIVDMA_0_BASEADDR+0x04); }
static u32 live_rx_status(void) { return Xil_In32(XPAR_AXIVDMA_0_BASEADDR+0x34); }
static int error(void) {
    return (video_rx_status()|video_tx_status()|live_rx_status())&(XAXIVDMA_SR_ERR_ALL_MASK|XAXIVDMA_SR_HALTED_MASK);
}
static int failed(const char *stage,int rc) {
    xil_printf("VIDEO_INIT_FAIL stage=%s rc=%d\r\n",stage,rc);return 0;
}
static void report(const char *result,const char *stage,int next,u32 elapsed) {
    xil_printf("VIDEO_%s stage=%s target=%d elapsed_ms=%lu rx=%08lx tx=%08lx live_rx=%08lx cam_frames=%lu hdmi_frames=%lu\r\n",
        result,stage,next,(unsigned long)elapsed,(unsigned long)video_rx_status(),
        (unsigned long)video_tx_status(),(unsigned long)live_rx_status(),
        (unsigned long)live_osd_camera_frames(),(unsigned long)live_osd_display_frames());
}
static int setup(XAxiVdma *dma,int direction,u32 base,int sync,const char *stage) {
    XAxiVdma_DmaSetup cfg;UINTPTR addresses[32];int rc;
    memset(&cfg,0,sizeof(cfg));
    cfg.VertSizeInput=VIDEO_H;cfg.HoriSizeInput=VIDEO_STRIDE;cfg.Stride=VIDEO_STRIDE;
    cfg.EnableCircularBuf=1;cfg.EnableSync=sync;cfg.PointNum=0;cfg.FrameDelay=1;cfg.GenLockRepeat=sync;
    rc=XAxiVdma_DmaConfig(dma,direction,&cfg);if(rc!=XST_SUCCESS)return failed(stage,rc);
    for(int i=0;i<dma->MaxNumFrames;i++)addresses[i]=base+i*VIDEO_BYTES;
    rc=XAxiVdma_DmaSetBufferAddr(dma,direction,addresses);if(rc!=XST_SUCCESS)return failed(stage,rc);
    rc=XAxiVdma_DmaStart(dma,direction);if(rc!=XST_SUCCESS)return failed(stage,rc);
    return 1;
}
static int park_and_wait(int next,u32 timeout,const char *stage) {
    int rc=XAxiVdma_StartParking(&capture_dma,next,XAXIVDMA_WRITE);
    if(rc!=XST_SUCCESS)return failed(stage,rc);
    u32 start=video_now_ms(),last_report=0;
    for(;;) {
        u32 elapsed=video_now_ms()-start;
        if(error()) {report("FAULT",stage,next,elapsed);return 0;}
        if(XAxiVdma_CurrFrameStore(&capture_dma,XAXIVDMA_WRITE)==(u32)next)return 1;
        if(elapsed>=timeout) {report("TIMEOUT",stage,next,elapsed);return 0;}
        if(timeout>VIDEO_FRAME_TIMEOUT_MS && elapsed-last_report>=500u) {
            report("WAIT",stage,next,elapsed);last_report=elapsed;
        }
        usleep(100);
    }
}
static int wait_live_progress(void) {
    u32 start=video_now_ms(),frames=live_osd_display_frames();
    u32 rx=XAxiVdma_CurrFrameStore(&live_dma,XAXIVDMA_WRITE);
    u32 tx=XAxiVdma_CurrFrameStore(&live_dma,XAXIVDMA_READ);
    int rx_changed=0,tx_changed=0;
    for(;;) {
        if(error()) {report("FAULT","live-prime",0,video_now_ms()-start);return 0;}
        rx_changed|=XAxiVdma_CurrFrameStore(&live_dma,XAXIVDMA_WRITE)!=rx;
        tx_changed|=XAxiVdma_CurrFrameStore(&live_dma,XAXIVDMA_READ)!=tx;
        if(rx_changed && tx_changed && live_osd_display_frames()!=frames)return 1;
        if((u32)(video_now_ms()-start)>=VIDEO_FRAME_TIMEOUT_MS) {
            report("TIMEOUT","live-prime",0,video_now_ms()-start);return 0;
        }
        usleep(100);
    }
}
int video_init(void) {
    int rc;u32 start=video_now_ms();
    xil_printf("VIDEO_BOOT r8-live-osd startup_ms=%lu runtime_ms=%lu live=triple-genlock snapshot=independent\r\n",
        (unsigned long)VIDEO_STARTUP_TIMEOUT_MS,(unsigned long)VIDEO_FRAME_TIMEOUT_MS);
    XAxiVdma_Config *cfg=XAxiVdma_LookupConfig(XPAR_AXIVDMA_0_DEVICE_ID);
    if(!cfg)return failed("live-lookup",-1);
    rc=XAxiVdma_CfgInitialize(&live_dma,cfg,cfg->BaseAddress);if(rc!=XST_SUCCESS)return failed("live-init",rc);
    cfg=XAxiVdma_LookupConfig(XPAR_AXIVDMA_1_DEVICE_ID);
    if(!cfg)return failed("snapshot-lookup",-1);
    rc=XAxiVdma_CfgInitialize(&capture_dma,cfg,cfg->BaseAddress);if(rc!=XST_SUCCESS)return failed("snapshot-init",rc);
    if(live_dma.MaxNumFrames!=3 || capture_dma.MaxNumFrames!=2)return failed("vdma-frame-count",-1);
    memset((void*)DISPLAY_BASE,0,3*VIDEO_BYTES);Xil_DCacheFlushRange(DISPLAY_BASE,3*VIDEO_BYTES);
    if(!setup(&live_dma,XAXIVDMA_WRITE,DISPLAY_BASE,1,"live-rx-config") ||
       !setup(&live_dma,XAXIVDMA_READ,DISPLAY_BASE,1,"live-tx-config") ||
       !setup(&capture_dma,XAXIVDMA_WRITE,CAPTURE_BASE,0,"snapshot-config"))return 0;
    rc=XAxiVdma_StartParking(&capture_dma,0,XAXIVDMA_WRITE);if(rc!=XST_SUCCESS)return failed("rx-park",rc);
    rc=DisplayInitialize(&display,XPAR_VTC_0_DEVICE_ID);if(rc!=XST_SUCCESS)return failed("display-init",rc);
    VideoMode mode=VMODE_1280x720;
    rc=DisplaySetMode(&display,&mode);if(rc!=XST_SUCCESS)return failed("display-mode",rc);
    rc=DisplayStart(&display);if(rc!=XST_SUCCESS)return failed("display-start",rc);
    xil_printf("VIDEO_INIT live-display-configured; waiting-for-camera-frames\r\n");
    if(!park_and_wait(1,VIDEO_STARTUP_TIMEOUT_MS,"rx-prime-1") ||
       !park_and_wait(0,VIDEO_FRAME_TIMEOUT_MS,"rx-prime-0") || !wait_live_progress())return 0;
    capture_index=0;last_display_count=live_osd_display_frames();last_display_ms=video_now_ms();
    report("READY","live-and-snapshot",0,video_now_ms()-start);return 1;
}
const u8 *video_snapshot(void) {
    int previous=capture_index,next=1-previous;
    if(!park_and_wait(next,VIDEO_FRAME_TIMEOUT_MS,"rx-snapshot"))return 0;
    capture_index=next;
    UINTPTR source=CAPTURE_BASE+previous*VIDEO_BYTES;
    Xil_DCacheInvalidateRange(source,VIDEO_BYTES);
    memcpy((void*)SNAPSHOT_BASE,(const void*)source,VIDEO_BYTES);
    return (const u8*)SNAPSHOT_BASE;
}
int video_present(const u8 *image) {
    /* Health check only. Live pixels never wait for this software call. */
    (void)image;u32 now=video_now_ms(),frames=live_osd_display_frames();
    if(error())return 0;
    if(frames!=last_display_count) {last_display_count=frames;last_display_ms=now;}
    return (u32)(now-last_display_ms)<VIDEO_FRAME_TIMEOUT_MS;
}
u8 *video_work_frame(void) {return (u8*)SNAPSHOT_BASE;}
