#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "eye_tracker.h"
#include "hdmi_overlay.h"

#define W 160
#define H 80
#define STRIDE (W * 3)

static void frame_for(u8 *f, int lx, int rx)
{
    int x, y;
    memset(f, 160, STRIDE * H);
    for (y = 28; y < 36; ++y) for (x = lx - 4; x <= lx + 4; ++x) {
        f[y * STRIDE + x * 3 + 0] = 5; f[y * STRIDE + x * 3 + 1] = 5; f[y * STRIDE + x * 3 + 2] = 5;
    }
    for (y = 28; y < 36; ++y) for (x = rx - 4; x <= rx + 4; ++x) {
        f[y * STRIDE + x * 3 + 0] = 5; f[y * STRIDE + x * 3 + 1] = 5; f[y * STRIDE + x * 3 + 2] = 5;
    }
}

static void sample(EyeTracker *t, u8 *f, int lx, int rx, int n)
{
    int i;
    for (i = 0; i < n; ++i) { frame_for(f, lx, rx); eye_tracker_process(t, f, STRIDE, W, H, 100); }
}

int main(void)
{
    u8 *f = (u8 *)calloc(1, STRIDE * H);
    EyeRoi l = {10, 10, 60, 50, 24, 80}, r = {90, 10, 60, 50, 24, 80};
    EyeTracker t;
    if (!f) return 2;
    eye_tracker_init(&t, &l, &r);
    sample(&t,f,40,120,2);
    if(!t.left.valid||!t.right.valid||t.valid||t.commit) return 29;
    /* Main's c command must be reachable with measured eyes before calibration. */
    eye_tracker_start_calibration(&t);
    sample(&t, f, 20, 100, 36);
    sample(&t, f, 40, 120, 36);
    sample(&t, f, 60, 140, 36);
    if (t.calibration_mask != 7 || t.calibration_stage != 0) return 3;
    sample(&t, f, 20, 100, 14);
    if (t.event_seq != 1 || t.direction != EYE_DIR_LEFT) { printf("left fail seq=%lu dir=%d valid=%d cand=%d dwell=%lu nx=%d/%d\n", (unsigned long)t.event_seq, t.direction, t.valid, t.candidate, (unsigned long)t.dwell_ms, t.left.normalized_x, t.right.normalized_x); return 4; }
    t.commit = 0;
    sample(&t, f, 20, 100, 30);
    if(t.event_seq!=1) return 20; /* Sustained look must not repeat. */
    memset(f,0,STRIDE*H);
    eye_tracker_process(&t,f,STRIDE,W,H,100);
    if(t.valid||t.candidate||t.armed||t.commit) return 21;
    sample(&t,f,60,140,20);
    if(t.event_seq!=1) return 22; /* Invalid frames and direct side switch do not rearm. */
    sample(&t, f, 40, 120, 10);
    if (t.direction != EYE_DIR_CENTER || t.valid == 0) return 5;
    sample(&t, f, 60, 140, 14);
    if (t.event_seq != 2 || t.direction != EYE_DIR_RIGHT) return 6;
    frame_for(f, 20, 100);
    hdmi_overlay_apply(f, STRIDE, W, H, &t);
    if (f[0] == 160 || f[10 * STRIDE + 10 * 3] == 160) return 7;
    eye_tracker_start_calibration(&t);
    sample(&t,f,40,120,108);
    if(t.calibration_mask||!t.cal_failed) return 23;
    eye_tracker_start_calibration(&t);
    memset(f,0,STRIDE*H);
    for(int i=0;i<151;i++) eye_tracker_process(&t,f,STRIDE,W,H,100);
    if(t.cal_failed||t.calibration_stage!=1||t.calibration_mask) return 24;
    eye_tracker_init(&t,&l,&r);
    eye_tracker_start_calibration(&t);
    sample(&t,f,60,140,36); sample(&t,f,40,120,36); sample(&t,f,20,100,36);
    if(t.calibration_mask!=7) return 25; /* Mirrored camera is accepted. */
    sample(&t,f,60,140,14);
    if(t.event_seq!=1) return 26;
    eye_tracker_process(&t,f,STRIDE,W,H,1200);
    if(t.valid||t.commit||t.dwell_ms) return 27;
    EyeFeature invalid;
    EyeRoi bad={65530,0,100,10,24,80};
    if(eye_analyze_rgb888(f,STRIDE,W,H,&bad,&invalid)) return 28;
    eye_tracker_start_calibration(&t);
    eye_tracker_process(&t,f,STRIDE,W,H,1200);
    if(t.cal_failed||t.calibration_stage!=1||t.calibration_mask||t.valid) return 30;
    /* Completed point and partial samples survive both-eye loss and long gaps. */
    sample(&t,f,20,100,36); sample(&t,f,40,120,25);
    if(t.calibration_mask!=1||t.calibration_stage!=2||t.calibration_count[0]!=5) return 31;
    memset(f,0,STRIDE*H);
    for(int i=0;i<200;i++) eye_tracker_process(&t,f,STRIDE,W,H,100);
    eye_tracker_pause(&t,EYE_PAUSE_PAIR);
    eye_tracker_process(&t,f,STRIDE,W,H,1200);
    if(t.calibration_mask!=1||t.calibration_stage!=2||t.calibration_count[0]!=5||t.cal_failed) return 32;
    sample(&t,f,40,120,11);
    if(t.calibration_stage!=3||t.calibration_mask!=3) return 33;
    sample(&t,f,60,140,20);
    /* Neither eye needs to be valid on the same frame as its partner. */
    for(int i=0;i<32;i++) {
        frame_for(f,60,140);
        for(int y=10;y<60;y++) memset(f+y*STRIDE+(i%2?10:90)*3,160,60*3);
        eye_tracker_process(&t,f,STRIDE,W,H,100);
        if(t.valid||t.commit) return 34;
    }
    if(t.calibration_mask!=7||t.calibration_stage) return 35;
    /* Missing runtime eye must never commit or rearm from the surviving eye. */
    t.armed=0;
    eye_tracker_process(&t,f,STRIDE,W,H,100);
    if(t.valid||t.commit||t.armed||t.calibration_mask!=7) return 36;
    eye_tracker_start_calibration(&t); sample(&t,f,20,100,25);
    sample(&t,f,50,100,1); /* Outliers remain in a bounded robust window. */
    sample(&t,f,20,100,1);
    if(t.calibration_count[0]!=7||t.calibration_count[1]!=7) return 37;
    sample(&t,f,50,100,3); /* Keep progress; the rolling core decides stability. */
    if(t.calibration_count[0]!=10||t.calibration_count[1]!=10||t.calibration_stage!=1) return 38;
    printf("eye_tracker host test passed: events=%lu\n", (unsigned long)t.event_seq);
    free(f);
    return 0;
}
