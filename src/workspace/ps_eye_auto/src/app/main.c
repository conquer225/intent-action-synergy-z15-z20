#include <string.h>
#include "xparameters.h"
#include "xil_printf.h"
#include "xil_io.h"
#include "xuartps_hw.h"
#include "sleep.h"
#include "emio_sccb_cfg/emio_sccb_cfg.h"
#include "ov5640/ov5640_init.h"
#include "auto_face.h"
#include "hdmi_overlay.h"
#include "live_osd.h"
#include "video_io.h"
static EyeTracker tracker;
static Localization anchor,last;
static u32 sequence,detect_ms,period_ms;
static int auto_mode=1,stable=0;
static void status(void)
{
    xil_printf("PS_AUTO seq=%lu mode=%s pair=%d stable=%d face=(%d,%d,%d,%d) "
        "L=(%d,%d,%d,%d) R=(%d,%d,%d,%d) eye_valid=%d/%d nx=%d/%d cal=%x stage=%d failed=%d "
        "dir=%s valid=%d armed=%d dwell=%lu detect_ms=%lu period_ms=%lu rx=%08lx tx=%08lx "
        "eye_reason=%d/%d dark=%d/%d samples=%d/%d selected=%d/%d threshold=%d/%d "
        "cal_samples=%d/%d pause=%d gaze_raw=%d gaze_filtered=%d filter_n=%d track=%d "
        "cal_error=%d eye=%d retry=%d gap=%d noise=%d ready=%d/%d core_span=%d/%d "
        "refs=%d,%d,%d/%d,%d,%d mad=%d,%d,%d/%d,%d,%d cam_frames=%lu hdmi_frames=%lu up_ms=%lu\r\n",
        (unsigned long)sequence,auto_mode?"AUTO":"FIXED",last.valid,stable,
        last.face.x,last.face.y,last.face.w,last.face.h,
        tracker.left_roi.x,tracker.left_roi.y,tracker.left_roi.w,tracker.left_roi.h,
        tracker.right_roi.x,tracker.right_roi.y,tracker.right_roi.w,tracker.right_roi.h,
        tracker.left.valid,tracker.right.valid,tracker.left.normalized_x,tracker.right.normalized_x,
        tracker.calibration_mask,tracker.calibration_stage,tracker.cal_failed,
        eye_direction_name(tracker.direction),tracker.valid,tracker.armed,
        (unsigned long)tracker.dwell_ms,(unsigned long)detect_ms,(unsigned long)period_ms,
        (unsigned long)video_rx_status(),(unsigned long)video_tx_status(),
        tracker.left.reason,tracker.right.reason,tracker.left.dark_count,tracker.right.dark_count,
        tracker.left.sample_count,tracker.right.sample_count,tracker.left.selected_count,tracker.right.selected_count,
        tracker.left.threshold,tracker.right.threshold,
        tracker.calibration_count[0],tracker.calibration_count[1],tracker.calibration_paused,
        tracker.gaze_raw,tracker.gaze_filtered,tracker.history_count,tracker.tracking_reason,
        tracker.cal_failure_reason,tracker.cal_failure_eye,tracker.cal_retry_stage,
        tracker.cal_failure_gap,tracker.cal_failure_noise,tracker.calibration_ready[0],tracker.calibration_ready[1],
        tracker.calibration_core_span[0],tracker.calibration_core_span[1],
        tracker.calibration[0][0],tracker.calibration[0][1],tracker.calibration[0][2],
        tracker.calibration[1][0],tracker.calibration[1][1],tracker.calibration[1][2],
        tracker.calibration_mad[0][0],tracker.calibration_mad[0][1],tracker.calibration_mad[0][2],
        tracker.calibration_mad[1][0],tracker.calibration_mad[1][1],tracker.calibration_mad[1][2],
        (unsigned long)live_osd_camera_frames(),(unsigned long)live_osd_display_frames(),(unsigned long)video_now_ms());
}
static void reset_tracking(void)
{
    eye_tracker_clear_calibration(&tracker); stable=0;
    last=(Localization){0}; anchor=(Localization){0};
    eye_tracker_set_face(&tracker,0);
    if(!live_osd_clear())xil_printf("OSD CLEAR FAILED\r\n");
}
int main(void)
{
    const EyeRoi left={300,240,260,160,24,80},right={720,240,260,160,24,80};
    u32 last_ms=0,last_log=0;
    xil_printf("\r\nPS_EYE_AUTO_START r8-live-osd BGR888 1280x720 unchanged r7 gaze + Haar\r\n");
    if(!live_osd_init()) {xil_printf("OSD HARDWARE MISMATCH - use matching r8 BOOT.BIN\r\n");return 1;}
    emio_init();
    if(ov5640_init(VIDEO_W,VIDEO_H,2570,980)!=0) { xil_printf("OV5640 FAIL\r\n"); return 1; }
    xil_printf("OV5640 OK\r\n");
    if(!video_init()) { xil_printf("VIDEO FAIL rx=%08lx tx=%08lx\r\n",(unsigned long)video_rx_status(),(unsigned long)video_tx_status()); return 1; }
    xil_printf("VDMA OK / HDMI STARTED\r\n");
    eye_tracker_init(&tracker,&left,&right);
    xil_printf("AUTO default. Commands: c=calibrate, t=retry failed point, r=clear, p=status, a=auto reacquire, m=fixed ROI\r\n");
    for(;;) {
        while(!(Xil_In32(STDIN_BASEADDRESS+XUARTPS_SR_OFFSET)&XUARTPS_SR_RXEMPTY)) {
            char c=(char)Xil_In32(STDIN_BASEADDRESS+XUARTPS_FIFO_OFFSET);
            if(c=='p'||c=='P') status();
            else if(c=='a'||c=='A') { auto_mode=1; reset_tracking(); xil_printf("AUTO SEARCH\r\n"); }
            else if(c=='m'||c=='M') { auto_mode=0; reset_tracking(); eye_tracker_set_roi(&tracker,&left,&right); xil_printf("FIXED ROI\r\n"); }
            else if(c=='r'||c=='R') { reset_tracking(); xil_printf("CAL CLEARED\r\n"); }
            else if(c=='t'||c=='T') {
                if((auto_mode&&stable<2)||(!tracker.left.valid&&!tracker.right.valid)||
                   !eye_tracker_retry_calibration(&tracker)) xil_printf("CAL RETRY BLOCKED\r\n");
                else xil_printf("CAL RETRY %s\r\n",eye_direction_name(tracker.calibration_stage));
            }
            else if(c=='c'||c=='C') {
                if((auto_mode&&stable<2)||(!tracker.left.valid&&!tracker.right.valid))
                    xil_printf("CAL BLOCKED: need stable detected pair and one valid eye feature\r\n");
                else { anchor=last; eye_tracker_start_calibration(&tracker); xil_printf("CAL LEFT: look at white target, hold until next prompt\r\n"); }
            }
        }
        const u8 *frame=video_snapshot();
        if(!frame) {
            reset_tracking(); xil_printf("VIDEO LOST/ERROR rx=%08lx tx=%08lx - restart required\r\n",(unsigned long)video_rx_status(),(unsigned long)video_tx_status());
            /* Fail closed; no stale image can generate an event. */
            return 1;
        }
        u32 sampled=video_now_ms();
        period_ms=last_ms?(u32)(sampled-last_ms):0; last_ms=sampled; sequence++;
        int ready=1;
        u8 pause=EYE_PAUSE_PAIR;
        detect_ms=0;
        if(auto_mode) {
            Localization loc;
            u32 started=video_now_ms();
            ready=auto_localize(frame,VIDEO_STRIDE,VIDEO_W,VIDEO_H,&loc);
            detect_ms=video_now_ms()-started;
            if(!ready) {
                stable=0; last=loc; eye_tracker_set_face(&tracker,0);
            } else {
                int active=tracker.calibration_mask||tracker.calibration_stage||tracker.cal_failed;
                if(active&&!localization_follow(&anchor,&loc,VIDEO_W,VIDEO_H,
                                               &tracker.left_roi,&tracker.right_roi)) {
                    stable=0; pause=EYE_PAUSE_POSITION; ready=0;
                } else {
                    stable=localization_near(&last,&loc)?stable+1:1;
                    if(stable>3) stable=3;
                    if(!active) eye_tracker_set_roi(&tracker,&loc.left,&loc.right);
                    ready=stable>=2;
                }
                eye_tracker_set_face(&tracker,&loc.face); last=loc;
            }
        }
        u8 previous_stage=tracker.calibration_stage;
        if(ready && detect_ms<=1000)
            eye_tracker_process(&tracker,frame,VIDEO_STRIDE,VIDEO_W,VIDEO_H,period_ms);
        else {
            eye_tracker_pause(&tracker,detect_ms>1000?EYE_PAUSE_TIMING:pause);
        }
        if(tracker.calibration_stage!=previous_stage) {
            if(tracker.calibration_stage) xil_printf("CAL %s: look at white target\r\n",eye_direction_name(tracker.calibration_stage));
            else xil_printf("CAL %s\r\n",tracker.calibration_mask==7?"OK":"FAILED: insufficient separation");
        }
        if(tracker.commit)
            xil_printf("EYE_EVENT seq=%lu direction=%s quality=%d\r\n",(unsigned long)tracker.event_seq,eye_direction_name(tracker.direction),tracker.confidence);
        if(!live_osd_publish(&tracker,sequence,sampled,auto_mode)) {
            reset_tracking();xil_printf("OSD PUBLISH FAILED - restart required\r\n");return 1;
        }
        if(!video_present(video_work_frame())) { reset_tracking(); xil_printf("DISPLAY FAILED - restart required\r\n"); return 1; }
        if((u32)(video_now_ms()-last_log)>=1000) { status(); last_log=video_now_ms(); }
        usleep(10000);
    }
}
