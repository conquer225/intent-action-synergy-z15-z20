/* Z20 standalone continuous dual-camera bring-up, not a Linux application. */
#include <string.h>
#include "xparameters.h"
#include "xaxivdma.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "sleep.h"
#include "display_ctrl_hdmi/display_ctrl_hdmi.h"
#include "emio_sccb_cfg/emio_sccb_cfg.h"
#include "ov5640/ov5640_init.h"
#include "video_boot.h"

#define FRAME_BASE 0x01000000u
#define FRAME_BYTES 8294400u
static XAxiVdma channels[3];
static DisplayCtrl display;
static const unsigned ids[3] = {XPAR_AXIVDMA_0_DEVICE_ID,
    XPAR_AXIVDMA_1_DEVICE_ID, XPAR_AXIVDMA_2_DEVICE_ID};
static const unsigned bases[3] = {0x43000000u, 0x43010000u, 0x43020000u};

static int camera_init(void *unused, unsigned id, unsigned width, unsigned height)
{
    int status;
    (void)unused;
    status = ov5640_init(id, width, height, 2570, 980);
    xil_printf("CAM%u init=%d size=%ux%u\r\n", id, status, width, height);
    return status;
}

static int dma_init(void *unused, unsigned id, unsigned address, unsigned active,
                    unsigned stride, unsigned height)
{
    XAxiVdma_Config *config = XAxiVdma_LookupConfig(ids[id]);
    XAxiVdma_DmaSetup setup;
    UINTPTR addresses[3];
    int direction = id==2?XAXIVDMA_READ:XAXIVDMA_WRITE;
    int status;
    unsigned i;
    (void)unused;
    if (!config || config->BaseAddress != bases[id]) return -1;
    status = XAxiVdma_CfgInitialize(&channels[id], config, config->BaseAddress);
    if (status != XST_SUCCESS || channels[id].MaxNumFrames != 3) return -2;
    memset(&setup, 0, sizeof setup);
    setup.VertSizeInput=height; setup.HoriSizeInput=active; setup.Stride=stride;
    setup.FrameDelay=id==2?1:0;
    setup.EnableCircularBuf=1; setup.EnableSync=1;
    status=XAxiVdma_DmaConfig(&channels[id], direction, &setup);
    if (status != XST_SUCCESS) return status;
    for (i=0;i<3;++i) addresses[i]=address+i*stride*height;
    status=XAxiVdma_DmaSetBufferAddr(&channels[id], direction, addresses);
    if (status != XST_SUCCESS) return status;
    status=XAxiVdma_DmaStart(&channels[id], direction);
    xil_printf("VDMA%u start=%d active=%u stride=%u base=%08x\r\n",
               id, status, active, stride, address);
    return status;
}

static int display_init(void *unused)
{
    int status;
    (void)unused;
    status=DisplayInitialize(&display, XPAR_VTC_0_DEVICE_ID);
    if (status != XST_SUCCESS) return status;
    status=DisplaySetMode(&display, &VMODE_1280x720);
    if (status != XST_SUCCESS) return status;
    return DisplayStart(&display);
}

int main(void)
{
    const z20_video_ops ops={camera_init, dma_init, display_init};
    int status;
    xil_printf("Z20_DUAL_VIDEO_BRINGUP v1; no inference owns video\r\n");
    memset((void *)FRAME_BASE, 0, FRAME_BYTES);
    Xil_DCacheFlushRange(FRAME_BASE, FRAME_BYTES);
    emio_init();
    status=z20_video_start(&ops, 0, FRAME_BASE);
    if (status) {
        xil_printf("VIDEO_START_FAILED stage=%d; inspect camera/VDMA wiring and status\r\n",status);
        for (;;) usleep(1000000);
    }
    xil_printf("VIDEO_START_CONFIGURED; verify two moving images on HDMI\r\n");
#ifdef Z20_UBOOT_ENTRY
    /* Reuse the vendor FSBL's CPU handoff sequence; leave all video DMA running. */
    extern void FsblHandoffExit(unsigned);
    xil_printf("VIDEO_HANDOFF_UBOOT entry=%08x\r\n", Z20_UBOOT_ENTRY);
    Xil_DCacheFlush();
    Xil_DCacheDisable();
    __asm__ volatile ("cpsid if" ::: "memory");
    FsblHandoffExit(Z20_UBOOT_ENTRY);
#endif
    for (;;) {
        xil_printf("VDMA_RAW left=%08x right=%08x display=%08x park=%08x/%08x/%08x\r\n",
          Xil_In32(bases[0]+0x34), Xil_In32(bases[1]+0x34), Xil_In32(bases[2]+4),
          Xil_In32(bases[0]+0x28), Xil_In32(bases[1]+0x28), Xil_In32(bases[2]+0x28));
        usleep(1000000);
    }
}
