#include <stdint.h>
#include <cmath>
#include <cstdio>
extern "C" void audio_fft(const int32_t[1024],int32_t[513],int32_t[513]);
int main(){
 int32_t x[1024],r[513],i[513];uint32_t seed=20261020;
 for(int test=0;test<7;test++){
  for(int n=0;n<1024;n++){
   seed=1664525*seed+1013904223;
   switch(test){
    case 0:x[n]=0;break;case 1:x[n]=10000;break;case 2:x[n]=(n%2)?-12000:12000;break;
    case 3:x[n]=n==0?32767:0;break;
    case 4:x[n]=(int)(20000*sin(2*3.141592653589793*32*n/1024));break;
    case 5:x[n]=(int16_t)(seed>>16);break;
    default:x[n]=(int)(10000*sin(2*3.141592653589793*9*n/1024)+16000*cos(2*3.141592653589793*71*n/1024));break;
   }
  }
  audio_fft(x,r,i);
  for(int k=0;k<513;k++){
   double re=0,im=0;
   for(int n=0;n<1024;n++){double angle=2*3.141592653589793*k*n/1024;re+=x[n]*cos(angle)/1024;im-=x[n]*sin(angle)/1024;}
   if(fabs(r[k]-re)>12||fabs(i[k]-im)>12){printf("AUDIO_FFT_FAIL test=%d bin=%d\n",test,k);return 1;}
  }
 }
 puts("AUDIO_FFT_CSIM_PASS 7 vectors,3591 complex bins against independent DFT");return 0;
}
