/* FIRMWARE_MAIN is replaced at test time with the current original main.c,
 * removing only hardware includes. Its loop and all AUTO decisions run as-is. */
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <setjmp.h>
#include "eye_tracker.h"
#include "auto_face.h"
#include "../tools/pc_gaze_bridge.c"
#define VIDEO_W 240u
#define VIDEO_H 140u
#define VIDEO_STRIDE (VIDEO_W*3u)
#define STDIN_BASEADDRESS 0
#define XUARTPS_SR_OFFSET 1
#define XUARTPS_FIFO_OFFSET 2
#define XUARTPS_SR_RXEMPTY 1

typedef struct { int lx,rx,command,valid,shift,dark; unsigned dt,detect; int dx,dy; } Step;
static Step steps[1200];
static int step_count,current=-1,command_read,comparisons;
static u8 pixels[VIDEO_W*VIDEO_H*3];
static unsigned tick=100,sampled;
static jmp_buf finished;
static PcGaze *session;
static Localization current_loc;
static int compare_step(void);
static void xil_printf(const char *fmt,...) { (void)fmt; }
static void emio_init(void) {}
static int ov5640_init(unsigned a,unsigned b,unsigned c,unsigned d) {(void)a;(void)b;(void)c;(void)d;return 0;}
static int video_init(void) {return 1;}
static unsigned video_rx_status(void) {return 0;}
static unsigned video_tx_status(void) {return 0;}
static unsigned video_now_ms(void) {return tick;}
static void usleep(unsigned dt) {(void)dt;}
static unsigned Xil_In32(unsigned address)
{
    int command=current+1<step_count?steps[current+1].command:0;
    if(address==XUARTPS_SR_OFFSET) return command&&!command_read?0:1;
    command_read=1;return command;
}
static u8 *video_work_frame(void) {return pixels;}
static const u8 *video_snapshot(void)
{
    if(++current>=step_count) longjmp(finished,1);
    command_read=0;
    Step p=steps[current];sampled+=p.dt;tick=sampled;
    memset(pixels,p.dark==1?0:160,sizeof(pixels));
    if(p.dark!=1) for(int y=28+p.dy;y<36+p.dy;y++) for(int e=0;e<2;e++) {
        if((p.dark==2&&e==0)||(p.dark==3&&e==1)) continue;
        int center=(e?p.rx:p.lx)+p.dx;
        for(int x=center-4;x<=center+4;x++) memset(pixels+y*VIDEO_STRIDE+x*3,5,3);
    }
    current_loc=(Localization){.face={p.shift+p.dx,p.dy,150,80,1},
        .left={10+p.dx,10+p.dy,60,50,24,80},.right={90+p.dx,10+p.dy,60,50,24,80},
        .valid=p.valid,.faces=p.valid,.eye_count=2*p.valid};
    return pixels;
}
static int mock_localize(const u8 *p,u32 stride,u32 w,u32 h,Localization *out)
{(void)p;(void)stride;(void)w;(void)h;*out=current_loc;tick+=steps[current].detect;return out->valid;}
static int live_osd_init(void) {return 1;}
static int live_osd_clear(void) {return 1;}
static unsigned live_osd_camera_frames(void) {return (unsigned)(current+1);}
static unsigned live_osd_display_frames(void) {return (unsigned)(current+1);}
static int live_osd_publish(const EyeTracker *t,u32 seq,u32 ms,int mode)
{(void)t;(void)seq;(void)ms;(void)mode;return 1;}
static int video_present(const u8 *p) {(void)p;return compare_step();}
#define main firmware_main
#define auto_localize mock_localize
/* FIRMWARE_MAIN */
#undef auto_localize
#undef main

static int compare_step(void)
{
    Step p=steps[current];
    if(p.command=='c') pc_gaze_calibrate(session);
    if(p.command=='t') pc_gaze_retry(session);
    if(p.command=='a'||p.command=='r') pc_gaze_reset(session);
    pc_gaze_step(session,pixels,VIDEO_STRIDE,VIDEO_W,VIDEO_H,&current_loc,current?p.dt:0,p.detect);
    PcGaze reference={.tracker=tracker,.anchor=anchor,.last=last,.stable=stable};
    u32 expected[128],actual[128];
    unsigned count=pc_gaze_values(&reference,expected,128);
    if(count>128||pc_gaze_values(session,actual,128)!=count) exit(3);
    for(unsigned i=0;i<count;i++) if(i!=15 && actual[i]!=expected[i]) {
        fprintf(stderr,"Mismatch step=%d field=%u expected=%u actual=%u\n",current,i,expected[i],actual[i]);
        exit(2);
    }
    comparisons++;return 1;
}
static void add(int lx,int rx,int n,int command,int valid,int shift,int dark,unsigned dt,unsigned detect)
{
    for(int i=0;i<n;i++) steps[step_count++]=(Step){lx,rx,i?0:command,valid,shift,dark,dt,detect,0,0};
}
static void move(int lx,int rx,int n,int dx,int dy)
{
    for(int i=0;i<n;i++) steps[step_count++]=(Step){lx,rx,0,1,0,0,100,20,dx,dy};
}
int main(void)
{
    add(40,120,2,0,1,0,0,100,20);
    add(20,100,36,'c',1,0,0,100,20);
    add(40,120,36,0,1,0,0,100,20);add(60,140,36,0,1,0,0,100,20);
    add(20,100,30,0,1,0,0,100,20);add(20,140,4,0,1,0,0,100,20);
    add(60,140,10,0,1,0,0,100,20);add(40,120,5,0,1,0,0,100,20);
    add(60,140,9,0,1,0,0,100,20);
    add(40,120,1,0,1,0,0,1200,20);add(40,120,1,0,1,0,0,100,1200);
    add(40,120,1,0,1,40,0,100,20);add(40,120,2,0,1,0,0,100,20);
    add(40,120,1,'c',0,0,0,100,20);add(40,120,3,0,1,0,0,100,20);
    add(40,120,108,'c',1,0,0,100,20); /* Nonseparated calibration. */
    add(40,120,1,'t',1,0,0,100,20); /* Retry uses original anchor/prefix. */
    add(50,130,35,0,1,0,0,100,20);add(60,140,36,0,1,0,0,100,20);
    add(40,120,151,'c',1,0,1,100,20); /* Invalid eyes pause without timeout. */
    add(40,120,2,'a',1,0,0,100,20);
    add(60,140,36,'c',1,0,0,100,20); /* Mirrored ordering. */
    add(40,120,36,0,1,0,0,100,20);add(20,100,36,0,1,0,0,100,20);
    add(60,140,9,0,1,0,0,100,20);
    add(40,120,2,'r',1,0,0,100,20);
    add(40,120,1,'c',1,0,0,1200,20);
    add(40,120,2,0,1,0,0,100,20);add(40,120,1,'c',1,0,0,100,1200);
    add(40,120,2,'r',1,0,0,100,20);
    add(20,100,36,'c',1,0,0,100,20);
    add(40,120,25,0,1,0,0,100,20);
    add(40,120,12,0,0,0,0,100,20); /* Missing pair preserves partial point. */
    add(40,120,3,0,1,40,0,100,20); /* Drift pauses until back at anchor. */
    add(40,120,12,0,1,0,0,100,20);
    add(60,140,20,0,1,0,0,100,20);
    for(int i=0;i<32;i++) add(60,140,1,0,1,0,2+i%2,100,20);
    add(60,140,2,0,1,0,0,100,20);
    add(40,120,2,'r',1,0,0,100,20);
    add(20,100,36,'c',1,0,0,100,20);
    add(40,120,25,0,1,0,0,100,20);
    move(40,120,12,24,12); /* Finish center after translating the whole image/pair. */
    move(60,140,36,24,12);
    move(20,100,9,24,12);move(40,120,6,0,0);move(60,140,9,0,0);
    session=pc_gaze_create();
    if(!setjmp(finished)) firmware_main();
    unsigned fields=pc_gaze_values(session,0,0)-1;
    pc_gaze_destroy(session);
    printf("PASS firmware main.c parity: %d frames, %u state values/frame\n",comparisons,fields);
    return comparisons==step_count?0:3;
}
