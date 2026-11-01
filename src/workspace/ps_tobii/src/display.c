/* Camera-independent HDMI using the paired r9 overlay and CMA buffers. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include "xil_io.h"
#include "xparameters.h"
#include "xplatform_info.h"
#include "xaxivdma.h"
#include "display_ctrl_hdmi/display_ctrl_hdmi.h"
#include "dma_shutdown.h"
typedef struct {UINTPTR base; volatile unsigned char *ptr;} Mapping;
static Mapping maps[]={{0x43000000,0},{0x43010000,0},{0x43c00000,0},{0x43c10000,0}};
static XAxiVdma dma;
static DisplayCtrl display;
static int owned;
u32 Xil_AssertStatus;
u32 XGetPlatform_Info(void){return XPLAT_ZYNQ;}
void Xil_Assert(const char *file,s32 line){fprintf(stderr,"Assertion %s:%ld\n",file,(long)line);abort();}
void xil_printf(const char *fmt,...){va_list a;va_start(a,fmt);vfprintf(stderr,fmt,a);va_end(a);}
static volatile u32 *reg(UINTPTR p){
    if(!(p&3u))for(unsigned i=0;i<4;i++)
        if(maps[i].ptr&&p>=maps[i].base&&p-maps[i].base<=0xfffcu)
            return (volatile u32*)(maps[i].ptr+p-maps[i].base);
    fprintf(stderr,"Invalid display MMIO %lx\n",(unsigned long)p);abort();
}
u32 Xil_In32(UINTPTR p){u32 v=*reg(p);__sync_synchronize();return v;}
void Xil_Out32(UINTPTR p,u32 v){__sync_synchronize();*reg(p)=v;__sync_synchronize();}
static u32 now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (u32)((u64)t.tv_sec*1000+t.tv_nsec/1000000);}
static void delay(void){struct timespec t={0,100000};nanosleep(&t,0);}
static u32 read_reg(u32 p){return Xil_In32(p);}
static void write_reg(u32 p,u32 v){Xil_Out32(p,v);}
int display_close(void){
    int halted=1;
    if(owned){const Z15DmaIo io={read_reg,write_reg,now_ms,delay};halted=z15_dma_quiesce(&io);owned=0;}
    for(unsigned i=0;i<4;i++)if(maps[i].ptr){munmap((void*)maps[i].ptr,0x10000);maps[i].ptr=0;}
    return halted;
}
int display_open(const u32 *physical){
    if(!physical)return 0;
    for(unsigned i=0;i<3;i++){
        if(!physical[i]||(physical[i]&7)||physical[i]>0x40000000u-2764800u)return 0;
        for(unsigned j=0;j<i;j++)if(physical[i]<physical[j]+2764800u&&physical[j]<physical[i]+2764800u)return 0;
    }
    int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0)return 0;
    for(unsigned i=0;i<4;i++){
        void *p=mmap(0,0x10000,PROT_READ|PROT_WRITE,MAP_SHARED,fd,(off_t)maps[i].base);
        if(p==MAP_FAILED){close(fd);display_close();return 0;}maps[i].ptr=p;
    }
    close(fd);
    if(Xil_In32(0x43c00000)!=0x4f534438u){display_close();return 0;}
    owned=1;
    const Z15DmaIo io={read_reg,write_reg,now_ms,delay};
    if(!z15_dma_quiesce(&io))return 0;
    XAxiVdma_Config *c=XAxiVdma_LookupConfig(XPAR_AXIVDMA_0_DEVICE_ID);
    if(!c||XAxiVdma_CfgInitialize(&dma,c,c->BaseAddress)!=XST_SUCCESS||dma.MaxNumFrames!=3)return 0;
    XAxiVdma_DmaSetup setup;memset(&setup,0,sizeof(setup));
    setup.VertSizeInput=720;setup.HoriSizeInput=3840;setup.Stride=3840;
    setup.EnableCircularBuf=1;setup.EnableSync=0;setup.FrameDelay=0;
    UINTPTR buffers[3]={physical[0],physical[1],physical[2]};
    if(XAxiVdma_DmaConfig(&dma,XAXIVDMA_READ,&setup)!=XST_SUCCESS||
       XAxiVdma_DmaSetBufferAddr(&dma,XAXIVDMA_READ,buffers)!=XST_SUCCESS||
       XAxiVdma_DmaStart(&dma,XAXIVDMA_READ)!=XST_SUCCESS)return 0;
    VideoMode mode=VMODE_1280x720;
    return DisplayInitialize(&display,XPAR_VTC_0_DEVICE_ID)==XST_SUCCESS&&
           DisplaySetMode(&display,&mode)==XST_SUCCESS&&DisplayStart(&display)==XST_SUCCESS;
}
u32 display_status(void){return Xil_In32(0x43000004);}
u32 display_frames(void){return Xil_In32(0x43c0000c);}
int display_index(void){return (int)XAxiVdma_CurrFrameStore(&dma,XAXIVDMA_READ);}
int display_park(unsigned index){
    if(index>=3||XAxiVdma_StartParking(&dma,index,XAXIVDMA_READ)!=XST_SUCCESS)return 0;
    u32 begin=now_ms();
    while(display_index()!=(int)index){if((u32)(now_ms()-begin)>=500)return 0;delay();}
    return !(display_status()&(XAXIVDMA_SR_ERR_ALL_MASK|XAXIVDMA_SR_HALTED_MASK));
}
