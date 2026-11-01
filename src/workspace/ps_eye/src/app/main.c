#include <stdio.h>
#include <string.h>
#include "xil_types.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xparameters.h"
#include "xaxivdma.h"
#include "xaxivdma_i.h"
#include "xuartps_hw.h"
#include "sleep.h"
#include "display_ctrl_hdmi/display_ctrl_hdmi.h"
#include "vdma_api/vdma_api.h"
#include "emio_sccb_cfg/emio_sccb_cfg.h"
#include "ov5640/ov5640_init.h"
#include "eye_tracker.h"
#include "hdmi_overlay.h"

#define VDMA_ID XPAR_AXIVDMA_0_DEVICE_ID
#define DISP_VTC_ID XPAR_VTC_0_DEVICE_ID
#define WIDTH 1280u
#define HEIGHT 720u
#define BYTES_PER_PIXEL 3u
#define STRIDE (WIDTH * BYTES_PER_PIXEL)
#define FRAME_BYTES (STRIDE * HEIGHT)
#define FRAME_BUFFER_ADDR (XPAR_PS7_DDR_0_S_AXI_BASEADDR + 0x01000000u)
#define DISPLAY_BUFFER_ADDR (FRAME_BUFFER_ADDR + FRAME_BYTES * 3u + 0x00100000u)
#define UART_BASE STDIN_BASEADDRESS
#define UART_RX_FIFO XUARTPS_FIFO_OFFSET
#define UART_RX_EMPTY XUARTPS_SR_RXEMPTY
#define VDMA_MM2S_STATUS 0x00000004u
#define VDMA_S2MM_STATUS 0x00000034u

static XAxiVdma vdma;
static DisplayCtrl display_ctrl;
static VideoMode video_mode;

static int command_ready(void)
{
    return (Xil_In32(UART_BASE + XUARTPS_SR_OFFSET) & UART_RX_EMPTY) == 0;
}

static char read_command(void) { return (char)Xil_In32(UART_BASE + UART_RX_FIFO); }

static void print_status(const EyeTracker *t, u32 frame_no, u32 mm2s, u32 s2mm)
{
    xil_printf("PS_EYE frame=%lu valid=%d dir=%s cand=%s conf=%d "
               "L=(%d,%d,%d) R=(%d,%d,%d) cal=%x stage=%d dwell=%lu "
               "vdma_tx=%08lx vdma_rx=%08lx\r\n",
        (unsigned long)frame_no, t->valid, eye_direction_name(t->direction),
        eye_direction_name(t->candidate), t->confidence,
        t->left.x, t->left.y, t->left.normalized_x,
        t->right.x, t->right.y, t->right.normalized_x,
        t->calibration_mask, t->calibration_stage,
        (unsigned long)t->dwell_ms, (unsigned long)mm2s, (unsigned long)s2mm);
}

int main(void)
{
    u32 status, frame_no = 0, last_signature = 0, elapsed_ms = 100;
    u32 mm2s, s2mm;
    EyeRoi left = {300, 240, 260, 160, 24, 80};
    EyeRoi right = {720, 240, 260, 160, 24, 80};
    EyeTracker tracker;
    const u8 *frame = (const u8 *)(UINTPTR)FRAME_BUFFER_ADDR;
    u8 *display_frame = (u8 *)(UINTPTR)DISPLAY_BUFFER_ADDR;

    xil_printf("\r\nPS_EYE_START z15 xc7z015 1280x720 RGB888\r\n");
    xil_printf("DDR capture=0x%08lx display=0x%08lx stride=%lu bytes=%lu\r\n",
               (unsigned long)FRAME_BUFFER_ADDR, (unsigned long)DISPLAY_BUFFER_ADDR,
               (unsigned long)STRIDE,
               (unsigned long)FRAME_BYTES);
    emio_init();
    status = ov5640_init(WIDTH, HEIGHT, 2570, 980);
    xil_printf("OV5640 %s\r\n", status == 0 ? "OK" : "FAIL");
    video_mode = VMODE_1280x720;
    status = run_vdma_frame_buffer(&vdma, VDMA_ID, WIDTH, HEIGHT,
                                   FRAME_BUFFER_ADDR, 0, 0, ONLY_WRITE);
    if (status == XST_SUCCESS)
        status = run_vdma_frame_buffer(&vdma, VDMA_ID, WIDTH, HEIGHT,
                                       DISPLAY_BUFFER_ADDR, 0, 0, ONLY_READ);
    xil_printf("VDMA %s capture=0x%08lx display=0x%08lx\r\n",
               status == XST_SUCCESS ? "OK" : "FAIL",
               (unsigned long)FRAME_BUFFER_ADDR,
               (unsigned long)DISPLAY_BUFFER_ADDR);
    if (status != XST_SUCCESS) return XST_FAILURE;
    status = DisplayInitialize(&display_ctrl, DISP_VTC_ID);
    if (status == XST_SUCCESS) status = DisplaySetMode(&display_ctrl, &video_mode);
    if (status == XST_SUCCESS) status = DisplayStart(&display_ctrl);
    xil_printf("HDMI %s\r\n", status == XST_SUCCESS ? "STARTED" : "FAIL");

    eye_tracker_init(&tracker, &left, &right);
    xil_printf("ROI L=%d,%d,%d,%d R=%d,%d,%d,%d\r\n",
               left.x, left.y, left.w, left.h, right.x, right.y, right.w, right.h);
    xil_printf("Commands: c=calibrate left/center/right, r=clear, p=status\r\n");
    for (;;) {
        if (command_ready()) {
            char c = read_command();
            if (c == 'c' || c == 'C') {
                eye_tracker_start_calibration(&tracker);
                xil_printf("CAL START: look LEFT, then CENTER, then RIGHT\r\n");
            } else if (c == 'r' || c == 'R') {
                eye_tracker_clear_calibration(&tracker);
                xil_printf("CAL CLEARED\r\n");
            } else if (c == 'p' || c == 'P') {
                print_status(&tracker, frame_no,
                    Xil_In32(XPAR_AXIVDMA_0_BASEADDR + VDMA_MM2S_STATUS),
                    Xil_In32(XPAR_AXIVDMA_0_BASEADDR + VDMA_S2MM_STATUS));
            }
        }
        Xil_DCacheInvalidateRange((UINTPTR)frame, FRAME_BYTES);
        eye_tracker_process(&tracker, frame, STRIDE, WIDTH, HEIGHT, elapsed_ms);
        memcpy(display_frame, frame, FRAME_BYTES);
        hdmi_overlay_apply(display_frame, STRIDE, WIDTH, HEIGHT, &tracker);
        Xil_DCacheFlushRange((UINTPTR)display_frame, FRAME_BYTES);
        {
            u32 signature = Xil_In32((UINTPTR)frame) ^ Xil_In32((UINTPTR)(frame + FRAME_BYTES - 64u));
            if (signature != last_signature) {
                frame_no++;
                last_signature = signature;
            }
        }
        mm2s = Xil_In32(XPAR_AXIVDMA_0_BASEADDR + VDMA_MM2S_STATUS);
        s2mm = Xil_In32(XPAR_AXIVDMA_0_BASEADDR + VDMA_S2MM_STATUS);
        if (frame_no != 0u && (frame_no % 10u) == 0u)
            print_status(&tracker, frame_no, mm2s, s2mm);
        if (tracker.commit)
            xil_printf("EYE_EVENT seq=%lu direction=%s confidence=%d\r\n",
                       (unsigned long)tracker.event_seq,
                       eye_direction_name(tracker.direction), tracker.confidence);
        usleep(elapsed_ms * 1000u);
    }
    return 0;
}
