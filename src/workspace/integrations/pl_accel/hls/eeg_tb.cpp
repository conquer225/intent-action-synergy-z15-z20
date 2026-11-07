#include <stdint.h>
#include <stdio.h>
#include "eeg_vectors.h"
extern "C" void z15_fbcsp(const int32_t*,const int32_t*,int32_t*,unsigned,unsigned);
int main() {
    static int32_t p[94]={0},x[512]={0},r[16]={0};
    p[0]=0x46424331;p[1]=1;p[2]=4;p[3]=2;p[4]=8;p[5]=3;p[6]=2;p[7]=250;
    for(int b=0;b<3;++b) {
        for(int s=0;s<2;++s)p[8+(b*2+s)*5]=1<<28;
        p[38+b*16+2]=1<<14;p[38+b*16+8+3]=1<<14;
    }
    p[86]=-4096;p[87]=4096;
    x[2]=256;x[3]=512;x[10]=-256;x[11]=-512;
    z15_fbcsp(x,p,r,2,1);
    if(r[1]!=0 || r[2]!=2)return 1;
    z15_fbcsp(x,p,r,2,0);
    if(r[1]!=3 || r[2]!=4 || r[3]!=1 || r[4]!=1 || r[5]!=33554432 || r[6]!=0)return 2;
    z15_fbcsp(x,p,r,2,0);
    if(r[1]!=3 || r[2]!=6 || r[3]!=2 || r[9]-r[8]!=8192)return 3;
    p[86]=-4095;z15_fbcsp(x,p,r,2,0);
    if(r[1]!=8)return 4;
    unsigned window=0;
    for(unsigned offset=0;offset<96;offset+=16) {
        z15_fbcsp(eeg_fixture_samples+offset*8,eeg_fixture_params,r,16,offset==0);
        if(r[1]&1) {
            const int32_t *expected=eeg_fixture_expected+window*10;
            if(((r[1]>>1)&1)!=expected[0] || r[4]!=expected[1] || r[5]!=expected[2]
               || r[6]!=(expected[2]<0 ? -1 : 0) || r[2]!=expected[9])return 5;
            for(unsigned j=0;j<6;++j)if(r[8+j]!=expected[3+j])return 6;
            ++window;
        }
    }
    if(window!=5)return 7;
    puts("PASS: EEG filter/CSP/window/log/SVM memory contract");return 0;
}
