#include "video_io.h"
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
static XAxiVdma dma;
static DisplayCtrl display;
static int capture_index,display_index;
static int park_and_wait(int direction,int next,u32 timeout_ms,const char *stage);
u32 video_now_ms(void) { XTime now; XTime_GetTime(&now); return (u32)(now/(COUNTS_PER_SECOND/1000u)); }
u32 video_rx_status(void) { return Xil_In32(XPAR_AXIVDMA_0_BASEADDR+0x34); }
u32 video_tx_status(void) { return Xil_In32(XPAR_AXIVDMA_0_BASEADDR+0x04); }
static int error(void) {
    return (video_rx_status()|video_tx_status())&(XAXIVDMA_SR_ERR_ALL_MASK|XAXIVDMA_SR_HALTED_MASK);
}
static int init_failed(const char *stage,int status)
{
    xil_printf("VIDEO_INIT_FAIL stage=%s rc=%d\r\n",stage,status);
    return 0;
}
static void report_wait(const char *result,const char *stage,int next,u32 elapsed)
{
    xil_printf("VIDEO_%s stage=%s target=%d elapsed_ms=%lu rx=%08lx tx=%08lx park=%08lx rx_cr=%08lx tx_cr=%08lx\r\n",
        result,stage,next,(unsigned long)elapsed,
        (unsigned long)video_rx_status(),(unsigned long)video_tx_status(),
        (unsigned long)Xil_In32(XPAR_AXIVDMA_0_BASEADDR+0x28),
        (unsigned long)Xil_In32(XPAR_AXIVDMA_0_BASEADDR+0x30),
        (unsigned long)Xil_In32(XPAR_AXIVDMA_0_BASEADDR));
}
static int setup(int direction,u32 base)
{
    XAxiVdma_DmaSetup cfg;
    UINTPTR addresses[32];
    int status;
    memset(&cfg,0,sizeof(cfg));
    cfg.VertSizeInput=VIDEO_H; cfg.HoriSizeInput=VIDEO_STRIDE; cfg.Stride=VIDEO_STRIDE;
    /* Unlike the vendor pass-through, RX and TX do not share frame buffers.
       Keep genlock off so CPU-owned parking remains independent. */
    cfg.EnableCircularBuf=1; cfg.EnableSync=0;
    status=XAxiVdma_DmaConfig(&dma,direction,&cfg);
    if(status!=XST_SUCCESS)
        return init_failed(direction==XAXIVDMA_WRITE?"rx-config":"tx-config",status);
    for(int i=0;i<dma.MaxNumFrames;i++) addresses[i]=base+i*VIDEO_BYTES;
    status=XAxiVdma_DmaSetBufferAddr(&dma,direction,addresses);
    if(status!=XST_SUCCESS)
        return init_failed(direction==XAXIVDMA_WRITE?"rx-address":"tx-address",status);
    status=XAxiVdma_DmaStart(&dma,direction);
    if(status!=XST_SUCCESS)
        return init_failed(direction==XAXIVDMA_WRITE?"rx-start":"tx-start",status);
    status=XAxiVdma_StartParking(&dma,0,direction);
    if(status!=XST_SUCCESS)
        return init_failed(direction==XAXIVDMA_WRITE?"rx-park":"tx-park",status);
    return 1;
}
int video_init(void)
{
    int status;
    u32 start=video_now_ms();
    xil_printf("VIDEO_BOOT r7-video1 startup_ms=%lu runtime_ms=%lu\r\n",
        (unsigned long)VIDEO_STARTUP_TIMEOUT_MS,(unsigned long)VIDEO_FRAME_TIMEOUT_MS);
    XAxiVdma_Config *cfg=XAxiVdma_LookupConfig(XPAR_AXIVDMA_0_DEVICE_ID);
    if(!cfg) return init_failed("vdma-lookup",-1);
    status=XAxiVdma_CfgInitialize(&dma,cfg,cfg->BaseAddress);
    if(status!=XST_SUCCESS) return init_failed("vdma-init",status);
    if(dma.MaxNumFrames<2||dma.MaxNumFrames>3)
        return init_failed("vdma-frame-count",dma.MaxNumFrames);
    memset((void*)DISPLAY_BASE,0,3*VIDEO_BYTES);
    Xil_DCacheFlushRange(DISPLAY_BASE,3*VIDEO_BYTES);
    if(!setup(XAXIVDMA_WRITE,CAPTURE_BASE)||!setup(XAXIVDMA_READ,DISPLAY_BASE)) return 0;
    status=DisplayInitialize(&display,XPAR_VTC_0_DEVICE_ID);
    if(status!=XST_SUCCESS) return init_failed("display-init",status);
    VideoMode mode=VMODE_1280x720;
    status=DisplaySetMode(&display,&mode);
    if(status!=XST_SUCCESS) return init_failed("display-mode",status);
    status=DisplayStart(&display);
    if(status!=XST_SUCCESS) return init_failed("display-start",status);
    xil_printf("VIDEO_INIT display-configured; waiting-for-camera-frames\r\n");
    /* Initial read index zero is also not proof that HDMI is consuming frames. */
    if(!park_and_wait(XAXIVDMA_READ,1,VIDEO_FRAME_TIMEOUT_MS,"tx-prime-1")||
       !park_and_wait(XAXIVDMA_READ,0,VIDEO_FRAME_TIMEOUT_MS,"tx-prime-0")) return 0;
    /* Confirm actual frame-boundary transitions before treating slot 0 as a
       capture buffer. At power-on the current-index register alone can read
       zero even though no camera frame has ever been written. */
    /* First RX transition includes sensor settling and the PL WAIT_FRAME gate.
       Once frames arrive, use the normal bounded deadline for every transition. */
    if(!park_and_wait(XAXIVDMA_WRITE,1,VIDEO_STARTUP_TIMEOUT_MS,"rx-prime-1")||
       !park_and_wait(XAXIVDMA_WRITE,0,VIDEO_FRAME_TIMEOUT_MS,"rx-prime-0")) return 0;
    report_wait("READY","primed",0,(u32)(video_now_ms()-start));
    capture_index=0; display_index=0;
    return 1;
}
static int park_and_wait(int direction,int next,u32 timeout_ms,const char *stage)
{
    int status=XAxiVdma_StartParking(&dma,next,direction);
    if(status!=XST_SUCCESS) return init_failed(stage,status);
    u32 start=video_now_ms(),last_report=0;
    for(;;) {
        u32 elapsed=(u32)(video_now_ms()-start);
        if(error()) { report_wait("FAULT",stage,next,elapsed);return 0; }
        if((int)XAxiVdma_CurrFrameStore(&dma,direction)==next) return 1;
        if(elapsed>timeout_ms) { report_wait("TIMEOUT",stage,next,elapsed);return 0; }
        if(timeout_ms>VIDEO_FRAME_TIMEOUT_MS && elapsed-last_report>=500u) {
            report_wait("WAIT",stage,next,elapsed);last_report=elapsed;
        }
        usleep(100);
    }
}
const u8 *video_snapshot(void)
{
    int previous=capture_index,next=1-previous;
    if(!park_and_wait(XAXIVDMA_WRITE,next,VIDEO_FRAME_TIMEOUT_MS,"rx-snapshot")) return 0;
    capture_index=next;
    /* Previous capture slot is no longer written and remains parked away. */
    UINTPTR source=CAPTURE_BASE+previous*VIDEO_BYTES;
    Xil_DCacheInvalidateRange(source,VIDEO_BYTES);
    memcpy((void*)SNAPSHOT_BASE,(const void*)source,VIDEO_BYTES);
    return (const u8*)SNAPSHOT_BASE;
}
u8 *video_work_frame(void) { return (u8*)SNAPSHOT_BASE; }
int video_present(const u8 *image)
{
    int next=1-display_index;
    UINTPTR dest=DISPLAY_BASE+next*VIDEO_BYTES;
    memcpy((void*)dest,image,VIDEO_BYTES);
    Xil_DCacheFlushRange(dest,VIDEO_BYTES);
    if(!park_and_wait(XAXIVDMA_READ,next,VIDEO_FRAME_TIMEOUT_MS,"tx-present")) return 0;
    display_index=next;
    return 1;
}
