// SPDX-License-Identifier: MIT
// Capture-only VDMA1 adapter; SCCB and GPIO driver sources retain vendor notices.
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
#include "gpio_scope.h"

static volatile unsigned char *dma,*gpio;
static int owned,index_now;
u32 Xil_AssertStatus;
u32 XGetPlatform_Info(void){return XPLAT_ZYNQ;}
void Xil_Assert(const char *file,s32 line){fprintf(stderr,"GPIO assertion %s:%ld\n",file,(long)line);abort();}
void xil_printf(const char *format,...){va_list a;va_start(a,format);vfprintf(stderr,format,a);va_end(a);}
static unsigned now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (unsigned)(t.tv_sec*1000ull+t.tv_nsec/1000000);}
int z15_delay_us(unsigned us){
    if(us>=1000){struct timespec t={us/1000000,(long)(us%1000000)*1000};while(nanosleep(&t,&t)&&errno==EINTR){}return 0;}
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);unsigned long long end=t.tv_sec*1000000000ull+t.tv_nsec+us*1000ull;
    do{clock_gettime(CLOCK_MONOTONIC,&t);}while(t.tv_sec*1000000000ull+t.tv_nsec<end);return 0;
}
static volatile u32 *reg32(UINTPTR physical){
    if((physical&3)==0 && physical>=0x43010000u && physical<0x43020000u && dma)return (volatile u32*)(dma+physical-0x43010000u);
    if((physical&3)==0 && physical>=0xe000a000u && physical<0xe000b000u && gpio)return (volatile u32*)(gpio+physical-0xe000a000u);
    fprintf(stderr,"Capture attempted an unmapped register\n");abort();
}
u32 Xil_In32(UINTPTR address){u32 v=*reg32(address);__sync_synchronize();return v;}
void Xil_Out32(UINTPTR address,u32 value){
    if(!vision_gpio_write_allowed(address))return;
    __sync_synchronize();*reg32(address)=value;__sync_synchronize();
}
static u32 get(unsigned offset){return Xil_In32(0x43010000u+offset);}
static void put(unsigned offset,u32 value){Xil_Out32(0x43010000u+offset,value);}
static int fault(void){return (get(0x34)&0x00000771u)!=0;}
static int park(unsigned target,unsigned timeout){
    put(0x28,(get(0x28)&~0x1f00u)|(target<<8));
    unsigned start=now_ms();
    while(((get(0x28)>>24)&31)!=target){if(fault()||now_ms()-start>=timeout)return 0;z15_delay_us(100);}
    return !fault();
}
void vision_camera_forget(void){
    owned=0;
    if(dma){munmap((void*)dma,0x10000);dma=NULL;}
    if(gpio){munmap((void*)gpio,0x1000);gpio=NULL;}
}
int vision_camera_close(void){
    if(dma && owned){put(0x30,4);unsigned start=now_ms();
        while((get(0x30)&4)||!(get(0x34)&1)){if(now_ms()-start>500)return 0;z15_delay_us(100);}}
    vision_camera_forget();return 1;
}
int vision_camera_open(u32 first,u32 second){
    if(dma || !first || !second || (first&7) || (second&7))return 0;
    const u32 size=720u*1280u*3u;
    if(first>0x40000000u-size || second>0x40000000u-size || (first<second+size && second<first+size))return 0;
    int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0)return 0;
    void *a=mmap(NULL,0x10000,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x43010000);
    void *b=mmap(NULL,0x1000,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0xe000a000);close(fd);
    if(a==MAP_FAILED||b==MAP_FAILED){if(a!=MAP_FAILED)munmap(a,0x10000);if(b!=MAP_FAILED)munmap(b,0x1000);return 0;}
    dma=a;gpio=b;owned=1;
    put(0x30,4);unsigned start=now_ms();
    while(get(0x30)&4){if(now_ms()-start>500)goto bad;z15_delay_us(100);}
    emio_init();if(ov5640_init(1280,720,2570,980)!=0)goto bad;
    put(0x34,0xffffffffu);put(0xac,first);put(0xb0,second);
    put(0xa8,3840);put(0xa4,3840);put(0x28,0);put(0x30,1);put(0xa0,720);
    if(!park(1,3000)||!park(0,500))goto bad;
    index_now=0;return 1;
bad:
    vision_camera_close();return 0;
}
int vision_camera_next(void){
    if(!owned)return -1;
    int old=index_now,next=1-index_now;
    if(!park((unsigned)next,500))return -1;
    index_now=next;return old;
}
