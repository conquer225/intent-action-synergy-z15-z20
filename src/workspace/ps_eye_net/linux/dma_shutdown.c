#include "dma_shutdown.h"
int z15_dma_quiesce(const Z15DmaIo *io){
    const u32 controls[]={0x43000000u,0x43000030u,0x43010030u};
    io->write(0x43c10000u,0); /* stop VTC */
    for(unsigned i=0;i<3;i++)io->write(controls[i],4u);
    u32 begin=io->now();
    for(;;){
        int stopped=1;
        for(unsigned i=0;i<3;i++)
            if((io->read(controls[i])&4u)||!(io->read(controls[i]+4)&1u))stopped=0;
        if(stopped)return 1;
        if((u32)(io->now()-begin)>=500u)return 0;
        io->delay();
    }
}
