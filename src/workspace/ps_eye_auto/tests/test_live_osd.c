#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "video_mock/mock_hw.h"
#include "../src/app/live_osd.c"
static u32 registers[32],clock_ms,busy,commits,id=OSD_ID;
u32 video_now_ms(void) {return clock_ms;}
void usleep(unsigned n) {(void)n;clock_ms++;}
u32 Xil_In32(UINTPTR p) {unsigned w=(p-OSD_BASE)/4;return w==0?id:w==1?busy:registers[w];}
void Xil_Out32(UINTPTR p,u32 value) {unsigned w=(p-OSD_BASE)/4;assert(w<32);if(w==2)commits++;registers[w]=value;}
int main(void) {
    EyeTracker t={0};t.face=(EyeFaceBox){100,100,200,200,1};
    t.left_roi=(EyeRoi){120,130,50,30,24,80};t.right_roi=(EyeRoi){200,130,50,30,24,80};
    t.left.valid=t.right.valid=1;t.left.x=140;t.left.y=140;t.right.x=220;t.right.y=140;
    t.valid=1;t.candidate=1;t.calibration_mask=7;EyeTracker saved=t;
    assert(live_osd_init());clock_ms=200;assert(live_osd_publish(&t,5,0,1));
    assert(registers[9]==31 && registers[10]==200 && (registers[14]&64));
    assert(registers[15]==5 && memcmp(&t,&saved,sizeof(t))==0);
    clock_ms=300;assert(live_osd_publish(&t,6,0,1));assert(!(registers[14]&64));
    t.face.valid=0;assert(live_osd_publish(&t,7,0,1));assert(registers[9]==0);
    assert(live_osd_publish(&t,8,0,0));assert(registers[9]==30);
    clock_ms=5;assert(live_osd_publish(&t,9,UINT32_MAX-10,0));assert(registers[10]==16);
    assert(live_osd_clear());assert(registers[8]==3 && registers[9]==0);
    busy=1;u32 before=commits;assert(!live_osd_publish(&t,10,0,0));assert(commits==before);
    id=0;assert(!live_osd_init());
    puts("PASS OSD metadata: unchanged tracker, missing geometry, source age, stale validity, clear, busy timeout and wrap");return 0;
}
