// SPDX-License-Identifier: MIT
// VDMA0 autonomous triple ring; offsets and genlock match retained video_live.c.
#ifndef VISION_STREAM_RING_H
#define VISION_STREAM_RING_H
#include <stdint.h>
#include <string.h>
typedef struct {uint32_t (*read)(uint32_t);void (*write)(uint32_t,uint32_t);uint32_t (*now)(void);void (*wait)(void);} StreamRingIo;
typedef struct {int owned;uint32_t control,park,vsize,hsize,stride,addresses[3];} StreamRing;
static int stream_wait(const StreamRingIo *io,uint32_t reg,uint32_t mask,uint32_t expected){
    uint32_t start=io->now();
    while((io->read(reg)&mask)!=expected){if((uint32_t)(io->now()-start)>=500)return 0;io->wait();}
    return 1;
}
static int stream_ring_stop(const StreamRingIo *io,StreamRing *r){
    if(!r->owned)return 1;
    io->write(0x30,4);
    if(!stream_wait(io,0x30,4,0)||!stream_wait(io,0x34,1,1))return 0;
    io->write(0x00,io->read(0x00)&~1u);
    if(!stream_wait(io,0x04,1,1))return 0;
    for(unsigned i=0;i<3;i++)io->write(0x5c+4*i,r->addresses[i]);
    io->write(0x58,r->stride);io->write(0x54,r->hsize);io->write(0x28,r->park&0x1f1fu);
    io->write(0x00,r->control);io->write(0x50,r->vsize);
    if((r->control&1) && !stream_wait(io,0x04,1,0))return 0;
    r->owned=0;return 1;
}
static int stream_ring_start(const StreamRingIo *io,const uint32_t p[3],StreamRing *r){
    const uint32_t bytes=1280u*720u*3u;
    if(r->owned)return 0;
    for(unsigned i=0;i<3;i++){
        if(!p[i]||(p[i]&7u)||p[i]>0x40000000u-bytes)return 0;
        for(unsigned j=0;j<i;j++)if(p[i]<p[j]+bytes && p[j]<p[i]+bytes)return 0;
    }
    r->control=io->read(0x00);r->park=io->read(0x28);r->vsize=io->read(0x50);
    r->hsize=io->read(0x54);r->stride=io->read(0x58);
    for(unsigned i=0;i<3;i++)r->addresses[i]=io->read(0x5c+4*i);
    r->owned=1;
    io->write(0x00,r->control&~1u);if(!stream_wait(io,0x04,1,1))return 0;
    io->write(0x30,4);if(!stream_wait(io,0x30,4,0)||!stream_wait(io,0x34,1,1))return 0;
    io->write(0x34,0xffffffffu);
    // CPU parking may leave read reference 1/2; prime genlock from frame 0.
    // stop() restores the saved CPU references with its original buffers.
    io->write(0x28,0);
    for(unsigned i=0;i<3;i++){io->write(0x5c+4*i,p[i]);io->write(0xac+4*i,p[i]);}
    io->write(0x58,0x01000f00);io->write(0x54,3840);
    io->write(0xa8,0x01000f00);io->write(0xa4,3840);
    io->write(0x30,0x800b);io->write(0xa0,720);
    io->write(0x00,(r->control&~0x8f1fu)|0xbu);io->write(0x50,720);
    uint32_t start=io->now(),initial=io->read(0x28);int moved_read=0,moved_write=0;unsigned discarded=0;
    while(!moved_read || !moved_write){
        uint32_t current=io->read(0x28);
        // RUNSTOP and HALTED cross internal clock domains. During priming,
        // permit HALTED to clear; genuine DMA errors still fail immediately.
        uint32_t read_error=io->read(4)&0x770u,write_status=io->read(0x34);
        // During a source handoff the input FIFO can expose one incomplete
        // old frame. Discard only this non-halted internal/frame error; bus,
        // decode, repeated framing faults and all runtime faults remain fatal.
        if(!read_error && (write_status&0x771u)==0x10u && discarded<2){
            io->write(0x34,0x10u);discarded++;
        }else if(read_error || (write_status&0x770u))return 0;
        moved_read|=((current^initial)&0x001f0000u)!=0;
        moved_write|=((current^initial)&0x1f000000u)!=0;
        if((uint32_t)(io->now()-start)>=3000)return 0;
        io->wait();
    }
    return 1;
}
#endif
