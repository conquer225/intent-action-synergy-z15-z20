#include "live_osd.h"
#include "video_io.h"
#include "xparameters.h"
#include "xil_io.h"
#include "sleep.h"
#include <string.h>
#if defined(XPAR_LIVE_OSD_0_S_AXI_BASEADDR)
#define OSD_BASE XPAR_LIVE_OSD_0_S_AXI_BASEADDR
#elif defined(XPAR_LIVE_OSD_0_BASEADDR)
#define OSD_BASE XPAR_LIVE_OSD_0_BASEADDR
#else
#error Rebuild the r8 live OSD hardware and BSP first
#endif
#define OSD_ID 0x4f534438u
static void put(unsigned word,u32 value) { Xil_Out32(OSD_BASE+4u*word,value); }
u32 live_osd_display_frames(void) { return Xil_In32(OSD_BASE+12u); }
u32 live_osd_camera_frames(void) { return Xil_In32(OSD_BASE+16u); }
static int available(void) {
    u32 start=video_now_ms();
    while(Xil_In32(OSD_BASE+4u)&1u) {
        if((u32)(video_now_ms()-start)>=100u)return 0;
        usleep(100);
    }
    return 1;
}
static int publish(u32 words[32]) {
    if(!available())return 0;
    for(unsigned i=8;i<31;i++)put(i,words[i]);
    put(2,1);return 1;
}
int live_osd_init(void) {
    if(Xil_In32(OSD_BASE)!=OSD_ID)return 0;
    return 1;
}
int live_osd_clear(void) {
    u32 w[32]={0};w[8]=3;w[11]=1500;w[12]=500;w[13]=2;
    return publish(w);
}
static void shape(u32 w[32],unsigned index,int x,int y,int width,int height,u32 rgb) {
    int x1=x+width,y1=y+height;
    if(x<0)x=0;
    if(y<0)y=0;
    if(x1>(int)VIDEO_W)x1=VIDEO_W;
    if(y1>(int)VIDEO_H)y1=VIDEO_H;
    if(x>=x1||y>=y1)return;
    unsigned n=16+3*index;w[9]|=1u<<index;
    w[n]=(u32)x|((u32)y<<16);w[n+1]=(u32)x1|((u32)y1<<16);w[n+2]=rgb;
}
int live_osd_publish(const EyeTracker *t,u32 source_seq,u32 source_ms,int auto_mode) {
    u32 w[32]={0},age=video_now_ms()-source_ms;
    w[8]=1;w[10]=age>65535u?65535u:age;w[11]=1500;w[12]=500;w[13]=2;
    unsigned done=(t->calibration_mask&1)+((t->calibration_mask>>1)&1)+((t->calibration_mask>>2)&1);
    w[14]=(u32)t->calibration_stage|((u32)t->candidate<<3)|((u32)(t->valid && age<=EYE_RUNTIME_GAP_MS)<<6)|(done<<7);
    w[15]=source_seq;
    if(t->face.valid)shape(w,0,t->face.x,t->face.y,t->face.w,t->face.h,0xffff00);
    if(t->face.valid || !auto_mode) {
        shape(w,1,t->left_roi.x,t->left_roi.y,t->left_roi.w,t->left_roi.h,t->left.valid?0x00dc00:0xe60000);
        shape(w,2,t->right_roi.x,t->right_roi.y,t->right_roi.w,t->right_roi.h,t->right.valid?0x00dc00:0xe60000);
        if(t->left.valid)shape(w,3,t->left.x-10,t->left.y-10,21,21,0x00dc00);
        if(t->right.valid)shape(w,4,t->right.x-10,t->right.y-10,21,21,0x00dc00);
    }
    return publish(w);
}
