#ifndef VIDEO_MOCK_HW_H
#define VIDEO_MOCK_HW_H
#include <stdint.h>
#include <stddef.h>
#include "xil_types.h"
typedef uintptr_t UINTPTR;
typedef uint64_t XTime;
#define COUNTS_PER_SECOND 1000000u
#define XPAR_AXIVDMA_0_BASEADDR 0x43000000u
#define XPAR_AXIVDMA_0_DEVICE_ID 0
#define XPAR_AXIVDMA_1_DEVICE_ID 1
#define XPAR_AXIVDMA_1_BASEADDR 0x43010000u
#define XPAR_LIVE_OSD_0_BASEADDR 0x43c00000u
#define XPAR_VTC_0_DEVICE_ID 0
#define XAXIVDMA_READ 0
#define XAXIVDMA_WRITE 1
#define XAXIVDMA_SR_ERR_ALL_MASK 0xFF0u
#define XAXIVDMA_SR_HALTED_MASK 1u
#define XST_SUCCESS 0
typedef struct { int MaxNumFrames,MockId; } XAxiVdma;
typedef struct { UINTPTR BaseAddress; } XAxiVdma_Config;
typedef struct { int VertSizeInput,HoriSizeInput,Stride,EnableCircularBuf,EnableSync,PointNum,FrameDelay,GenLockRepeat; } XAxiVdma_DmaSetup;
#define DISPLAY_CTRL_HDMI_H_
typedef int DisplayCtrl;
typedef int VideoMode;
#define VMODE_1280x720 0
XAxiVdma_Config *XAxiVdma_LookupConfig(int id);
int XAxiVdma_CfgInitialize(XAxiVdma *d, XAxiVdma_Config *c,UINTPTR b);
int XAxiVdma_DmaConfig(XAxiVdma *d,int dir,XAxiVdma_DmaSetup *cfg);
int XAxiVdma_DmaSetBufferAddr(XAxiVdma *d,int dir,UINTPTR *a);
int XAxiVdma_DmaStart(XAxiVdma *d,int dir);
int XAxiVdma_StartParking(XAxiVdma *d,int frame,int dir);
u32 XAxiVdma_CurrFrameStore(XAxiVdma *d,int dir);
int DisplayInitialize(DisplayCtrl *d,int id);
int DisplaySetMode(DisplayCtrl *d,const VideoMode *m);
int DisplayStart(DisplayCtrl *d);
u32 Xil_In32(UINTPTR p);
void Xil_Out32(UINTPTR p,u32 v);
void Xil_DCacheFlushRange(UINTPTR p,u32 n);
void Xil_DCacheInvalidateRange(UINTPTR p,u32 n);
void XTime_GetTime(XTime *now);
void usleep(unsigned n);
#endif
