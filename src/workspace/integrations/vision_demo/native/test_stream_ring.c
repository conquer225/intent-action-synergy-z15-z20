#include <stdio.h>
#include <string.h>
#include "stream_ring.h"
#define assert(condition) do {if(!(condition)){fprintf(stderr,"line %d: %s\n",__LINE__,#condition);return 1;}} while(0)
static uint32_t regs[128],clock_ms;static int stuck,delayed_start=1,priming_fault;
static uint32_t rd(uint32_t a){return regs[a/4];}
static void wr(uint32_t a,uint32_t v){
    if(a==0x34){if(priming_fault!=2)regs[a/4]&=~v;return;}
    regs[a/4]=v;
    if(a==0x00)regs[0x04/4]=(v&1)?(uint32_t)delayed_start:1;
    if(a==0x30 && (v&4) && !stuck){regs[a/4]=0;regs[0x34/4]=1;}
    if(a==0x30 && (v&1))regs[0x34/4]=(uint32_t)delayed_start|(priming_fault==3?0x20u:priming_fault?0x10u:0);
}
static uint32_t now(void){return clock_ms;}
static void wait_tick(void){clock_ms++;if(regs[0]&1)regs[4/4]=0;if(regs[0x30/4]&1){regs[0x34/4]&=~1u;regs[0x28/4]=(regs[0x28/4]&0x1f1fu)|((clock_ms%3)<<24)|(((clock_ms+2)%3)<<16);}}
int main(void){
    const StreamRingIo io={rd,wr,now,wait_tick};StreamRing ring={0};
    uint32_t old[3]={0x10000000,0x11000000,0x12000000},live[3]={0x20000000,0x21000000,0x22000000};
    regs[0]=1;regs[0x28/4]=2;regs[0x50/4]=720;regs[0x54/4]=3840;regs[0x58/4]=3840;
    for(int i=0;i<3;i++)regs[(0x5c+4*i)/4]=old[i];
    assert(stream_ring_start(&io,live,&ring));assert(ring.owned);
    assert((regs[0x28/4]&0x1f1fu)==0);
    assert((regs[0]&0xb)==0xb);assert((regs[0x30/4]&0x800b)==0x800b);
    for(int i=0;i<3;i++)assert(regs[(0x5c+4*i)/4]==live[i]);
    stuck=1;assert(!stream_ring_stop(&io,&ring));assert(ring.owned);
    stuck=0;assert(stream_ring_stop(&io,&ring));assert(!ring.owned);
    for(int i=0;i<3;i++)assert(regs[(0x5c+4*i)/4]==old[i]);
    assert(regs[0]==1 && regs[0x58/4]==3840);
    assert((regs[0x28/4]&0x1f1fu)==2);
    priming_fault=1;delayed_start=0;assert(stream_ring_start(&io,live,&ring));assert(!(regs[0x34/4]&0x10u));
    assert(stream_ring_stop(&io,&ring));
    priming_fault=2;assert(!stream_ring_start(&io,live,&ring));assert(ring.owned);assert(stream_ring_stop(&io,&ring));
    priming_fault=3;assert(!stream_ring_start(&io,live,&ring));assert(ring.owned);assert(stream_ring_stop(&io,&ring));priming_fault=0;
    uint32_t bad[3]={0x20000000,0x20000008,0x22000000};
    assert(!stream_ring_start(&io,bad,&ring));assert(!ring.owned);
    puts("STREAM_RING_PASS genlock ring, exact read-channel restoration, halt timeout retains ownership, invalid addresses");
}
