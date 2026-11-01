#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <sys/mman.h>
#include <sys/types.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include "xil_io.h"
#include "xparameters.h"
#include "xplatform_info.h"
#include "xaxivdma.h"
#include "video_io.h"
#include "live_osd.h"
#include "net_control.h"
#include "emio_sccb_cfg/emio_sccb_cfg.h"
#include "ov5640/ov5640_init.h"
#include "display_ctrl_hdmi/display_ctrl_hdmi.h"
#include "dma_shutdown.h"
typedef struct {UINTPTR physical;size_t bytes;volatile u8 *virtual_address;} Mapping;
static Mapping maps[]={{0x43000000u,0x10000,0},{0x43010000u,0x10000,0},
    {0x43c00000u,0x10000,0},{0x43c10000u,0x10000,0},{0xe000a000u,0x1000,0}};
static XAxiVdma live_dma,capture_dma;
static DisplayCtrl display;
static int capture_index,owned_video;
static u32 display_ms,display_frames;
extern NetControl *board_control(void);
u32 Xil_AssertStatus;
u32 XGetPlatform_Info(void){return XPLAT_ZYNQ;}
void Xil_Assert(const char *file,s32 line){fprintf(stderr,"Driver assertion %s:%ld\n",file,(long)line);abort();}
void xil_printf(const char *format,...){va_list args;va_start(args,format);vfprintf(stdout,format,args);va_end(args);fflush(stdout);}
u32 video_now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (u32)((u64)t.tv_sec*1000u+t.tv_nsec/1000000u);}
/* 4-us SCCB transitions should not become Linux scheduler ticks. Long waits yield. */
int z15_delay_us(unsigned microseconds){
    if(microseconds>=1000){struct timespec t={microseconds/1000000u,(long)(microseconds%1000000u)*1000};while(nanosleep(&t,&t)&&errno==EINTR){}return 0;}
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);u64 end=(u64)t.tv_sec*1000000000u+t.tv_nsec+(u64)microseconds*1000u;
    do{clock_gettime(CLOCK_MONOTONIC,&t);}while((u64)t.tv_sec*1000000000u+t.tv_nsec<end);return 0;
}
static volatile u32 *address(UINTPTR physical){
    if(physical&3u){fprintf(stderr,"Unaligned MMIO\n");abort();}
    for(unsigned i=0;i<sizeof(maps)/sizeof(maps[0]);i++){
        if(maps[i].virtual_address&&physical>=maps[i].physical&&physical-maps[i].physical<=maps[i].bytes-4)
            return (volatile u32*)(maps[i].virtual_address+physical-maps[i].physical);
    }
    fprintf(stderr,"Unmapped register %lx\n",(unsigned long)physical);abort();
}
u32 Xil_In32(UINTPTR physical){u32 value=*address(physical);__sync_synchronize();return value;}
void Xil_Out32(UINTPTR physical,u32 value){__sync_synchronize();*address(physical)=value;__sync_synchronize();}
u32 video_rx_status(void){return Xil_In32(XPAR_AXIVDMA_1_BASEADDR+0x34);}
u32 video_tx_status(void){return Xil_In32(XPAR_AXIVDMA_0_BASEADDR+0x04);}
static int errors(void){return (video_rx_status()|video_tx_status()|Xil_In32(XPAR_AXIVDMA_0_BASEADDR+0x34))&(XAXIVDMA_SR_ERR_ALL_MASK|XAXIVDMA_SR_HALTED_MASK);}
static u32 dma_read(u32 address){return Xil_In32(address);}
static void dma_write(u32 address,u32 value){Xil_Out32(address,value);}
static void dma_delay(void){z15_delay_us(100);}
_Static_assert(XAXIVDMA_CR_RESET_MASK==4u&&XAXIVDMA_SR_HALTED_MASK==1u,"VDMA reset ABI changed");
int linux_hw_close(void){
    int stopped=1;
    if(owned_video){
        /* Reset also covers a partially successful startup. Do not free CMA
         * until every implemented channel has completed reset and halted. */
        const Z15DmaIo io={dma_read,dma_write,video_now_ms,dma_delay};
        stopped=z15_dma_quiesce(&io);
        if(!stopped)fprintf(stderr,"VDMA reset did not halt all channels; reset PL before freeing CMA\n");
        owned_video=0;
    }
    for(unsigned i=0;i<sizeof(maps)/sizeof(maps[0]);i++)if(maps[i].virtual_address){munmap((void*)maps[i].virtual_address,maps[i].bytes);maps[i].virtual_address=0;}
    return stopped;
}
int linux_hw_open(void){
    int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0){perror("/dev/mem");return 0;}
    for(unsigned i=0;i<sizeof(maps)/sizeof(maps[0]);i++){
        void *v=mmap(0,maps[i].bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,(off_t)maps[i].physical);
        if(v==MAP_FAILED){perror("mmap MMIO");close(fd);linux_hw_close();return 0;}
        maps[i].virtual_address=v;
    }
    close(fd);
    if(!live_osd_init()){fprintf(stderr,"Overlay ID mismatch: require eye_wifi.bit/hwh\n");linux_hw_close();return 0;}
    owned_video=1;
    emio_init();
    if(ov5640_init(VIDEO_W,VIDEO_H,2570,980)!=0){fprintf(stderr,"OV5640 initialization failed\n");linux_hw_close();return 0;}
    return 1;
}
static int setup(XAxiVdma *dma,int direction,const u32 *addresses,int sync){
    XAxiVdma_DmaSetup cfg;UINTPTR buffers[32];memset(&cfg,0,sizeof(cfg));
    cfg.VertSizeInput=VIDEO_H;cfg.HoriSizeInput=VIDEO_STRIDE;cfg.Stride=VIDEO_STRIDE;
    cfg.EnableCircularBuf=1;cfg.EnableSync=sync;cfg.PointNum=0;cfg.FrameDelay=1;cfg.GenLockRepeat=sync;
    for(int i=0;i<dma->MaxNumFrames;i++)buffers[i]=addresses[i];
    return XAxiVdma_DmaConfig(dma,direction,&cfg)==XST_SUCCESS&&
           XAxiVdma_DmaSetBufferAddr(dma,direction,buffers)==XST_SUCCESS&&XAxiVdma_DmaStart(dma,direction)==XST_SUCCESS;
}
static int park(int next,u32 timeout){
    if(XAxiVdma_StartParking(&capture_dma,next,XAXIVDMA_WRITE)!=XST_SUCCESS)return 0;
    u32 begin=video_now_ms();
    while(XAxiVdma_CurrFrameStore(&capture_dma,XAXIVDMA_WRITE)!=(u32)next){
        if(errors()||(u32)(video_now_ms()-begin)>=timeout){fprintf(stderr,"VDMA park timeout/fault target=%d rx=%08lx tx=%08lx\n",next,(unsigned long)video_rx_status(),(unsigned long)video_tx_status());return 0;}
        z15_delay_us(100);
    }
    return !errors();
}
int linux_video_init(const u32 *live,const u32 *capture){
    if(!live||!capture)return 0;
    u32 all[5]={live[0],live[1],live[2],capture[0],capture[1]};
    for(int i=0;i<5;i++){
        if(!all[i]||(all[i]&7u)||all[i]>0x40000000u-VIDEO_STRIDE*VIDEO_H)return 0;
        for(int j=0;j<i;j++)if(all[i]<all[j]+VIDEO_STRIDE*VIDEO_H&&all[j]<all[i]+VIDEO_STRIDE*VIDEO_H)return 0;
    }
    XAxiVdma_Config *cfg=XAxiVdma_LookupConfig(XPAR_AXIVDMA_0_DEVICE_ID);
    if(!cfg||XAxiVdma_CfgInitialize(&live_dma,cfg,cfg->BaseAddress)!=XST_SUCCESS)return 0;
    cfg=XAxiVdma_LookupConfig(XPAR_AXIVDMA_1_DEVICE_ID);
    if(!cfg||XAxiVdma_CfgInitialize(&capture_dma,cfg,cfg->BaseAddress)!=XST_SUCCESS)return 0;
    if(live_dma.MaxNumFrames!=3||capture_dma.MaxNumFrames!=2)return 0;
    if(!setup(&live_dma,XAXIVDMA_WRITE,live,1)||!setup(&live_dma,XAXIVDMA_READ,live,1)||!setup(&capture_dma,XAXIVDMA_WRITE,capture,0))return 0;
    if(XAxiVdma_StartParking(&capture_dma,0,XAXIVDMA_WRITE)!=XST_SUCCESS||DisplayInitialize(&display,XPAR_VTC_0_DEVICE_ID)!=XST_SUCCESS)return 0;
    VideoMode mode=VMODE_1280x720;
    if(DisplaySetMode(&display,&mode)!=XST_SUCCESS||DisplayStart(&display)!=XST_SUCCESS)return 0;
    if(!park(1,3000)||!park(0,500))return 0;
    capture_index=0;display_frames=live_osd_display_frames();display_ms=video_now_ms();
    u32 initial_rx=XAxiVdma_CurrFrameStore(&live_dma,XAXIVDMA_WRITE),initial_tx=XAxiVdma_CurrFrameStore(&live_dma,XAXIVDMA_READ);
    int rx=0,tx=0;
    while(!(rx&&tx&&live_osd_display_frames()!=display_frames)){
        rx|=XAxiVdma_CurrFrameStore(&live_dma,XAXIVDMA_WRITE)!=initial_rx;
        tx|=XAxiVdma_CurrFrameStore(&live_dma,XAXIVDMA_READ)!=initial_tx;
        if(errors()||(u32)(video_now_ms()-display_ms)>500)return 0;
        z15_delay_us(100);
    }
    return 1;
}
int linux_snapshot_index(void){
    int previous=capture_index,next=1-previous;
    if(!park(next,500))return -1;
    capture_index=next;return previous;
}
int linux_display_health(void){
    u32 frames=live_osd_display_frames(),now=video_now_ms();
    if(frames!=display_frames){display_frames=frames;display_ms=now;}
    return !errors()&&(u32)(now-display_ms)<500;
}
int linux_osd_publish(u32 seq,u32 sampled){return live_osd_publish(&board_control()->eye,seq,sampled,1);}
int linux_osd_clear(void){return live_osd_clear();}
