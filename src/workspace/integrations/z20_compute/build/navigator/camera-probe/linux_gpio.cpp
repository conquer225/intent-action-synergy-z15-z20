#include "xgpiops.h"
#include <unistd.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
static int base,fd[4]={-1,-1,-1,-1},direction[4]={0},enabled[4]={0};
static XGpioPs_Config config;
static void write_file(const char *p,const char *s){int f=open(p,O_WRONLY);if(f<0){perror(p);exit(20);}if(write(f,s,strlen(s))!=(ssize_t)strlen(s)){perror(p);exit(21);}close(f);}
XGpioPs_Config *XGpioPs_LookupConfig(unsigned){return &config;}
int XGpioPs_CfgInitialize(XGpioPs *,XGpioPs_Config *,unsigned){return 0;}
static int slot(unsigned pin){if(pin<54||pin>57){fprintf(stderr,"Refuse non-SCCB GPIO\n");exit(22);}return pin-54;}
static void apply(unsigned pin){int i=slot(pin);char p[160];snprintf(p,sizeof p,"/sys/class/gpio/gpio%d/direction",base+(int)pin);write_file(p,direction[i]&&enabled[i]?"out":"in");}
void XGpioPs_SetDirectionPin(XGpioPs *,unsigned p,unsigned v){direction[slot(p)]=v;apply(p);}
void XGpioPs_SetOutputEnablePin(XGpioPs *,unsigned p,unsigned v){enabled[slot(p)]=v;apply(p);}
void XGpioPs_WritePin(XGpioPs *,unsigned p,unsigned v){int f=fd[slot(p)];lseek(f,0,SEEK_SET);if(write(f,v?"1":"0",1)!=1){perror("gpio write");exit(23);}}
unsigned XGpioPs_ReadPin(XGpioPs *,unsigned p){char c;int f=fd[slot(p)];lseek(f,0,SEEK_SET);if(read(f,&c,1)!=1){perror("gpio read");exit(24);}return c=='1';}
extern void emio_init(void);
extern u8 sccb_read_reg16(u8,u16);
extern u8 ov5640_init(u8,u16,u16,u16,u16);
int main(int argc,char **argv){
 if(argc<2){fprintf(stderr,"usage: probe gpiochip-base [init]\n");return 2;}base=atoi(argv[1]);
 if(base!=906){fprintf(stderr,"Unexpected GPIO base; inspect actual gpiochip before use\n");return 3;}
 for(int i=0;i<4;i++){char p[160],v[32];snprintf(v,sizeof v,"%d",base+54+i);int f=open("/sys/class/gpio/export",O_WRONLY);if(f<0)return 4;int n=write(f,v,strlen(v));int e=errno;close(f);if(n<0&&e!=EBUSY){errno=e;perror("export");return 5;}snprintf(p,sizeof p,"/sys/class/gpio/gpio%d/value",base+54+i);fd[i]=open(p,O_RDWR);if(fd[i]<0){perror(p);return 6;}}
 emio_init();usleep(30000);int all=1;
 for(unsigned c=0;c<2;c++){unsigned id=(sccb_read_reg16(c,0x300a)<<8)|sccb_read_reg16(c,0x300b);printf("CAM%u_ID=0x%04x\n",c,id);fflush(stdout);if(id!=0x5640)all=0;}
 if(!all)return 7;
 if(argc>2&&strcmp(argv[2],"init")==0)for(unsigned c=0;c<2;c++){int s=ov5640_init(c,640,720,2570,980);printf("CAM%u_INIT=%d\n",c,s);fflush(stdout);if(s)return 8;}
 for(int i=0;i<4;i++)close(fd[i]);return 0;
}
