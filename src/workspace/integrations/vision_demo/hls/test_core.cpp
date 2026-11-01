#include <stdint.h>
#include <stdio.h>
extern "C" uint32_t vision_core(const uint32_t*,uint32_t*,uint32_t*,unsigned,unsigned,unsigned,unsigned,unsigned);
int main() {
    uint32_t input[16]={}, output[16]={}, history[16]={};
    for(unsigned mode=0;mode<10;mode++){
        for(unsigned i=0;i<16;i++){input[i]=0x6e6e6e;history[i]=0xffffffff;}
        if(vision_core(input,output,history,4,4,mode,1,127))return 1;
        uint32_t expected=(mode==0||mode==4||mode==6||mode==8||mode==9)?0x6e6e6e:(mode==2||mode==3)?0x1b1b1b:0;
        for(unsigned i=0;i<16;i++)if(output[i]!=expected)return 10+mode;
    }
    input[0]=0xFF0000;input[1]=0x00FF00;input[2]=0x0000FF;input[3]=0xFFFFFF;
    if(vision_core(input,output,history,4,4,4,1,127))return 2;
    if(output[0]!=0x4D4D4D||output[1]!=0x959595||output[2]!=0x1D1D1D||output[3]!=0xFFFFFF)return 3;
    for(unsigned i=0;i<16;i++)input[i]=0xc8c8c8;
    if(vision_core(input,output,history,4,4,2,1,127))return 4;
    for(unsigned i=0;i<16;i++)input[i]=0x6e6e6e;
    if(vision_core(input,output,history,4,4,2,0,127)||output[0]!=0xb45aff)return 5;
    if(vision_core(input,output,history,4,4,2,0,127)||output[0]!=0x9c4eea)return 6;
    if(vision_core(input,output,history,641,4,0,1,127)!=1)return 7;
    if(vision_core(input,output,history,4,4,10,1,127)!=2)return 8;
    puts("VISION_HLS_CSIM_PASS all_modes temporal_reset invalid_parameters");return 0;
}
