// SPDX-License-Identifier: MIT
// Exercise the actual retained SCCB and Xilinx initializer against GPIO MMIO.
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "xil_io.h"
#include "xplatform_info.h"
#include "emio_sccb_cfg/emio_sccb_cfg.h"
#include "gpio_scope.h"
static u32 regs[1024];
u32 Xil_AssertStatus;
u32 XGetPlatform_Info(void){return XPLAT_ZYNQ;}
void Xil_Assert(const char *file,s32 line){fprintf(stderr,"%s:%ld\n",file,(long)line);abort();}
int z15_delay_us(unsigned us){(void)us;return 0;}
u32 Xil_In32(UINTPTR address){return regs[(address-0xe000a000u)/4];}
void Xil_Out32(UINTPTR address,u32 value){
    if(!vision_gpio_write_allowed(address))return;
    unsigned offset=address-0xe000a000u;
    if(offset>=0x214 && offset<=0x2d4 && (offset-0x214)%0x40==0)
        regs[(offset-8)/4]|=value; // INTDIS masks, INTMASK is read-only.
    else regs[offset/4]=value;
}
int main(void){
    const u32 masks[4]={0xffffe7ffu,0x12345678u,0xabcdef01u,0x55aa55aau};
    memset(regs,0,sizeof regs);
    for(unsigned bank=0;bank<4;bank++)regs[(0x20c+bank*0x40)/4]=masks[bank];
    regs[0x284/4]=0x80;regs[0x288/4]=0x100;
    for(unsigned repeat=0;repeat<2;repeat++){
        emio_init();
        for(unsigned bank=0;bank<4;bank++)
            assert(regs[(0x20c+bank*0x40)/4]==masks[bank]);
        assert(regs[0x284/4]==0x83);assert(regs[0x288/4]==0x103);
        assert(regs[0x10/4]==0xfffd0002u); // Last masked write drives SDA high.
    }
    puts("CAMERA_GPIO_COEXIST_PASS");return 0;
}
