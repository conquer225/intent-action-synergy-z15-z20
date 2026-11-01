#include "net_transport.h"
#include "video_io.h"
#include "live_osd.h"
#include "xparameters.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "xuartps_hw.h"
#include "sleep.h"
#include "emio_sccb_cfg/emio_sccb_cfg.h"
#include "ov5640/ov5640_init.h"
static NetControl controller;
static u32 sequence,last_log,cooldown;
static int network_allowed=1,failures,cooling;
static void report(void){
    EyeTracker *t=&controller.eye;
    xil_printf("PS_NET seq=%lu source=%s pair=%d stable=%d eye_valid=%u/%u pupil=%u,%u/%u,%u nx=%u/%u "
        "cal=%u stage=%u failed=%u dir=%s valid=%u armed=%u dwell=%lu detect_ms=%lu period_ms=%lu "
        "accepted=%lu rejected=%lu timeouts=%lu rx=%08lx tx=%08lx cam_frames=%lu hdmi_frames=%lu up_ms=%lu\r\n",
        (unsigned long)sequence,controller.source==NET_SOURCE_PC?"PC":"LOCAL",controller.last.valid,controller.stable,
        t->left.valid,t->right.valid,t->left.x,t->left.y,t->right.x,t->right.y,t->left.normalized_x,t->right.normalized_x,
        t->calibration_mask,t->calibration_stage,t->cal_failed,eye_direction_name(t->direction),t->valid,t->armed,
        (unsigned long)t->dwell_ms,(unsigned long)controller.detect_ms,(unsigned long)controller.period_ms,
        (unsigned long)controller.accepted,(unsigned long)controller.rejected,(unsigned long)controller.timeouts,
        (unsigned long)video_rx_status(),(unsigned long)video_tx_status(),
        (unsigned long)live_osd_camera_frames(),(unsigned long)live_osd_display_frames(),(unsigned long)video_now_ms());
    net_transport_status();
}
static void uart(void){
    while(!(Xil_In32(STDIN_BASEADDRESS+XUARTPS_SR_OFFSET)&XUARTPS_SR_RXEMPTY)){
        char cmd=(char)Xil_In32(STDIN_BASEADDRESS+XUARTPS_FIFO_OFFSET);
        if(cmd>='A'&&cmd<='Z')cmd=(char)(cmd+'a'-'A');
        if(cmd=='p')report();
        else if(cmd=='n'){network_allowed=1;cooling=0;failures=0;net_control_reset(&controller);live_osd_clear();}
        else if(cmd=='l'){network_allowed=0;net_control_reset(&controller);live_osd_clear();}
        else if(cmd=='c'||cmd=='r'||cmd=='t'){
            int ok=net_control_command(&controller,cmd,video_now_ms());
            if(ok)live_osd_clear();
            xil_printf("CONTROL cmd=%c accepted=%d\r\n",cmd,ok);report();
        }
    }
}
static int fatal(const char *message){
    net_control_reset(&controller);live_osd_clear();net_transport_stop();xil_printf("%s - restart required\r\n",message);return 1;
}
int main(void){
    xil_printf("\r\nPS_EYE_NET_START r9-face-roi BGR888 1280x720 UDP pupil return + r8 live OSD\r\n");
    net_control_init(&controller);
    if(!live_osd_init())return fatal("OSD HARDWARE MISMATCH");
    emio_init();
    if(ov5640_init(VIDEO_W,VIDEO_H,2570,980)!=0)return fatal("OV5640 FAIL");
    xil_printf("OV5640 OK\r\n");
    if(!video_init())return fatal("VIDEO FAIL");
    if(!net_transport_init(&controller))xil_printf("NET INIT FAILED - local PS fallback\r\n");
    video_set_poll(net_transport_poll);
    xil_printf("Commands: c=calibrate t=retry r=clear p=status n=auto network l=local PS\r\n");
    for(;;){
        net_transport_poll();uart();u32 now=video_now_ms();
        if(cooling&&(u32)(now-cooldown)>=2000u)cooling=0;
        int source=network_allowed&&net_transport_peer()&&!cooling?NET_SOURCE_PC:NET_SOURCE_LOCAL;
        if(net_control_source(&controller,source)){
            live_osd_clear();
            xil_printf("SOURCE %s - calibration cleared, recalibrate on HDMI\r\n",source==NET_SOURCE_PC?"PC":"LOCAL");
        }
        const u8 *frame=video_snapshot();
        if(!frame)return fatal("VIDEO LOST/ERROR");
        u32 sampled=video_now_ms();sequence++;controller.sequence=sequence;
        u8 stage=controller.eye.calibration_stage;
        if(source==NET_SOURCE_PC){
            u32 accepted=controller.accepted;
            int sent=net_transport_send_frame(frame,sampled,sequence);
            if(sent){
                while(controller.waiting){
                    net_transport_poll();uart();
                    if(net_control_timeout(&controller,video_now_ms()))break;
                    usleep(100);
                }
            }
            if(controller.accepted!=accepted)failures=0;
            else if(++failures>=3){
                cooling=1;cooldown=video_now_ms();failures=0;
                xil_printf("NET STALE - local fallback; network retry in 2 s\r\n");
            }
        }else{
            Localization loc;u32 start=video_now_ms();
            auto_localize(frame,VIDEO_STRIDE,VIDEO_W,VIDEO_H,&loc);
            u32 elapsed=video_now_ms()-start;
            net_control_local(&controller,frame,VIDEO_STRIDE,VIDEO_W,VIDEO_H,&loc,sampled,elapsed);
        }
        if(controller.eye.calibration_stage!=stage){
            xil_printf("CAL stage=%u mask=%u failed=%u error=%u retry=%u\r\n",controller.eye.calibration_stage,
                controller.eye.calibration_mask,controller.eye.cal_failed,controller.eye.cal_failure_reason,controller.eye.cal_retry_stage);
        }
        if(controller.eye.commit){
            xil_printf("EYE_EVENT seq=%lu direction=%s quality=%u source=%s\r\n",(unsigned long)controller.eye.event_seq,
                eye_direction_name(controller.eye.direction),controller.eye.confidence,controller.source?"PC":"LOCAL");
            net_transport_status();controller.eye.commit=0;
        }
        if(!live_osd_publish(&controller.eye,sequence,sampled,1))return fatal("OSD PUBLISH FAILED");
        if(!video_present(frame))return fatal("DISPLAY FAILED");
        if((u32)(video_now_ms()-last_log)>=1000u){report();last_log=video_now_ms();}
        net_transport_poll();usleep(10000);
    }
}
