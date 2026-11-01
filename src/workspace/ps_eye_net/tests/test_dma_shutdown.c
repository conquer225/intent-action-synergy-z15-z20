#include <assert.h>
#include <stdio.h>
#include "dma_shutdown.h"
static u32 tick,begin,ready[3],controls[3],status[3];
static unsigned writes,delays,vtc_stopped;
static int stuck;
static int channel(u32 a){
    if((a&~7u)==0x43000000u)return 0;
    if((a&~7u)==0x43000030u)return 1;
    if((a&~7u)==0x43010030u)return 2;
    assert(0);return -1;
}
static u32 read_reg(u32 a){
    int i=channel(a);
    if(!(stuck&(1<<i))&&(u32)(tick-begin)>=ready[i]){controls[i]=0;status[i]=1;}
    if((stuck&(1<<(i+3)))&&(u32)(tick-begin)>=ready[i]){controls[i]=0;status[i]=0;}
    return a&4u?status[i]:controls[i];
}
static void write_reg(u32 a,u32 v){
    if(a==0x43c10000u){assert(v==0);vtc_stopped=1;return;}
    assert(vtc_stopped&&v==4);controls[channel(a)]=v;writes++;
}
static u32 clock_ms(void){return tick;}
static void delay(void){tick++;delays++;}
static void reset(u32 start,int fault){
    begin=tick=start;stuck=fault;writes=delays=vtc_stopped=0;
    for(int i=0;i<3;i++){controls[i]=0;status[i]=0;ready[i]=3+i*7;}
}
int main(void){
    const Z15DmaIo io={read_reg,write_reg,clock_ms,delay};
    reset(100,0);assert(z15_dma_quiesce(&io)&&writes==3&&delays==17);
    reset(0xfffffff8u,0);assert(z15_dma_quiesce(&io)&&writes==3&&delays==17);
    for(int i=0;i<3;i++){
        reset(100,1<<i);assert(!z15_dma_quiesce(&io)&&writes==3&&delays==500);
    }
    /* A cleared reset bit without HALTED must also fail, even on partial init. */
    reset(100,32);
    assert(!z15_dma_quiesce(&io));
    puts("PASS Linux DMA shutdown: every channel halted, partial startup, stuck reset/status, timeout and wrap (mock)");
    return 0;
}
