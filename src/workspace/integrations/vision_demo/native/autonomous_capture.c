// SPDX-License-Identifier: MIT
// Only VDMA0 streaming-ring handoff and original OV5640 SCCB setup.
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <errno.h>
#include "xil_io.h"
#include "xplatform_info.h"
#include "emio_sccb_cfg/emio_sccb_cfg.h"
#include "ov5640/ov5640_init.h"
#include "stream_ring.h"
#include "gpio_scope.h"
static volatile unsigned char *dma,*gpio;
static StreamRing ring;
u32 Xil_AssertStatus;
u32 XGetPlatform_Info(void){return XPLAT_ZYNQ;}
void Xil_Assert(const char *file,s32 line){fprintf(stderr,"GPIO assertion %s:%ld\n",file,(long)line);abort();}
void xil_printf(const char *format,...){va_list a;va_start(a,format);vfprintf(stderr,format,a);va_end(a);}
static uint32_t now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint32_t)(t.tv_sec*1000ull+t.tv_nsec/1000000);}
int z15_delay_us(unsigned us){
    if(us>=1000){struct timespec t={us/1000000,(long)(us%1000000)*1000};while(nanosleep(&t,&t)&&errno==EINTR){}return 0;}
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);unsigned long long end=t.tv_sec*1000000000ull+t.tv_nsec+us*1000ull;
    do{clock_gettime(CLOCK_MONOTONIC,&t);}while(t.tv_sec*1000000000ull+t.tv_nsec<end);return 0;
}
static volatile u32 *reg32(UINTPTR physical){
    if((physical&3)==0 && physical>=0x43000000u && physical<0x43010000u && dma)return (volatile u32*)(dma+physical-0x43000000u);
    if((physical&3)==0 && physical>=0xe000a000u && physical<0xe000b000u && gpio)return (volatile u32*)(gpio+physical-0xe000a000u);
    fprintf(stderr,"Streaming attempted an unmapped register\n");abort();
}
u32 Xil_In32(UINTPTR address){u32 v=*reg32(address);__sync_synchronize();return v;}
void Xil_Out32(UINTPTR address,u32 value){
    if(!vision_gpio_write_allowed(address))return;
    __sync_synchronize();*reg32(address)=value;__sync_synchronize();
}
static uint32_t rd(uint32_t offset){return Xil_In32(0x43000000u+offset);}
static void wr(uint32_t offset,uint32_t value){Xil_Out32(0x43000000u+offset,value);}
static void wait_tick(void){z15_delay_us(100);}
static const StreamRingIo io={rd,wr,now_ms,wait_tick};
void vision_live_forget(void){
    ring.owned=0;
    if(dma){munmap((void*)dma,0x10000);dma=NULL;}
    if(gpio){munmap((void*)gpio,0x1000);gpio=NULL;}
}
int vision_live_close(void){
    if(dma && !stream_ring_stop(&io,&ring))return 0;
    vision_live_forget();return 1;
}
int vision_live_open(const uint32_t *addresses){
    if(dma || !addresses)return 0;
    int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0)return 0;
    void *a=mmap(NULL,0x10000,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x43000000);
    void *b=mmap(NULL,0x1000,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0xe000a000);close(fd);
    if(a==MAP_FAILED||b==MAP_FAILED){if(a!=MAP_FAILED)munmap(a,0x10000);if(b!=MAP_FAILED)munmap(b,0x1000);return 0;}
    dma=a;gpio=b;
    emio_init();
    if(ov5640_init(1280,720,2570,980)!=0 || !stream_ring_start(&io,addresses,&ring)){
        vision_live_close();return 0;
    }
    return 1;
}
int vision_live_health(void){return dma && ring.owned && !((rd(4)|rd(0x34))&0x771u);}
uint32_t vision_live_indices(void){return dma?rd(0x28):0;}
