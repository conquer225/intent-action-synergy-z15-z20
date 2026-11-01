#include <stdint.h>
#include "audio_twiddle.h"
// Independent radix-2 DIT FFT, Q15 input. Every butterfly scales by 1/2.
// Output is the unwindowed input FFT divided by 1024, natural frequency order.
extern "C" void audio_fft(const int32_t samples[1024],int32_t real_out[513],int32_t imag_out[513]) {
#pragma HLS INTERFACE s_axilite port=samples bundle=control offset=0x1000
#pragma HLS INTERFACE s_axilite port=real_out bundle=control offset=0x2000
#pragma HLS INTERFACE s_axilite port=imag_out bundle=control offset=0x3000
#pragma HLS INTERFACE s_axilite port=return bundle=control
 int32_t re[1024],im[1024];
 for(int n=0;n<1024;n++) {
  unsigned rev=0,v=n;
  for(int b=0;b<10;b++){rev=(rev<<1)|(v&1);v>>=1;}
  re[rev]=(int16_t)samples[n];im[rev]=0;
 }
 for(int stage=1;stage<=10;stage++) {
  int half=1<<(stage-1),size=half<<1,step=1024/size;
  for(int k=0;k<512;k++) {
   int group=k/half,j=k%half,a=group*size+j,b=a+half,t=j*step;
   int32_t ar=re[a],ai=im[a],br=re[b],bi=im[b];
   int32_t tr=(int32_t)(((int64_t)WR[t]*br-(int64_t)WI[t]*bi)>>15);
   int32_t ti=(int32_t)(((int64_t)WR[t]*bi+(int64_t)WI[t]*br)>>15);
   re[a]=(ar+tr)>>1;im[a]=(ai+ti)>>1;
   re[b]=(ar-tr)>>1;im[b]=(ai-ti)>>1;
  }
 }
 for(int k=0;k<513;k++){real_out[k]=re[k];imag_out[k]=im[k];}
}
