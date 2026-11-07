#include <stdint.h>
#include <stdio.h>
#include "map_vectors.h"
extern "C" void z20_map(const int32_t*,const int32_t*,int32_t*,int32_t*,int32_t*);
int main() {
    static int32_t p[32]={0},v[266240]={0},frame[921600]={0},depth[921600]={0},stats[16];
    p[0]=0x4d415031;p[1]=1;p[2]=9;p[3]=9;p[4]=3;p[6]=3277;p[7]=6553600;
    p[9]=0x0c121c;p[10]=0xffc440;p[12]=p[17]=p[22]=65536;
    p[24]=p[25]=4*65536;p[26]=p[27]=4*65536;
    v[2]=2*65536;v[3]=0xff0000;v[6]=65536;v[7]=0x00ff00;v[10]=-65536;v[11]=0x0000ff;
    z20_map(v,p,frame,depth,stats);
    if(stats[1] || stats[2]!=2 || stats[3]!=1 || frame[40]!=0x00ff00)return 1;
    p[5]=2;v[12]=-2*65536;v[14]=65536;v[16]=2*65536;v[18]=65536;
    z20_map(v,p,frame,depth,stats);
    if(stats[4]!=1)return 2;
    for(int x=0;x<9;++x)if(frame[36+x]!=0xffc440)return 3;
    z20_map(map_fixture_vertices,map_fixture_params,frame,depth,stats);
    if(stats[1])return 4;
    for(unsigned i=0;i<2961;++i)if(frame[i]!=map_fixture_frame[i])return 5;
    for(unsigned i=0;i<3;++i)if(stats[i+2]!=map_fixture_stats[i])return 6;
    puts("PASS: map projection/depth/trajectory memory contract");return 0;
}
