/* Host session adapter for the AUTO branch in src/app/main.c.
 * Gaze and localization algorithms are linked unchanged from firmware.
 * tests/test_gaze_parity.c executes the original main.c against this adapter.
 */
#include <stdlib.h>
#include <stddef.h>
#include "auto_face.h"

typedef struct {
    EyeTracker tracker;
    Localization anchor, last;
    int stable;
    u32 reason;
} PcGaze;

enum { OK, SEARCH, POSITION_CHANGED, TOO_SLOW, CAL_FAILED, CAL_STARTED, RESET };

static void clear(PcGaze *s)
{
    eye_tracker_clear_calibration(&s->tracker);
    s->stable=0; s->anchor=(Localization){0}; s->last=(Localization){0};
    eye_tracker_set_face(&s->tracker,0);
}
void *pc_gaze_create(void)
{
    PcGaze *s=calloc(1,sizeof(*s));
    if(s) {
        const EyeRoi l={300,240,260,160,24,80},r={720,240,260,160,24,80};
        eye_tracker_init(&s->tracker,&l,&r); s->reason=SEARCH;
    }
    return s;
}
void pc_gaze_destroy(PcGaze *s) { free(s); }
void pc_gaze_reset(PcGaze *s) { clear(s); s->reason=RESET; }
int pc_gaze_can_calibrate(const PcGaze *s)
{ return s->stable>=2 && (s->tracker.left.valid || s->tracker.right.valid); }
int pc_gaze_calibrate(PcGaze *s)
{
    if(!pc_gaze_can_calibrate(s)) return 0;
    s->anchor=s->last; eye_tracker_start_calibration(&s->tracker);
    s->reason=CAL_STARTED; return 1;
}
int pc_gaze_retry(PcGaze *s)
{
    if(!pc_gaze_can_calibrate(s)||!eye_tracker_retry_calibration(&s->tracker)) return 0;
    s->reason=CAL_STARTED;return 1;
}
void pc_gaze_step(PcGaze *s,const u8 *frame,u32 stride,u32 w,u32 h,
                  const Localization *loc,u32 dt,u32 detect_ms)
{
    EyeTracker *t=&s->tracker;
    int ready=loc->valid;
    u8 pause=EYE_PAUSE_PAIR;
    s->reason=OK;
    if(!ready) {
        s->stable=0; s->last=*loc; s->reason=SEARCH;
        eye_tracker_set_face(t,0);
    } else {
        int active=t->calibration_mask||t->calibration_stage||t->cal_failed;
        if(active&&!localization_follow(&s->anchor,loc,w,h,&t->left_roi,&t->right_roi)) {
            s->stable=0; s->reason=POSITION_CHANGED; pause=EYE_PAUSE_POSITION; ready=0;
        } else {
            s->stable=localization_near(&s->last,loc)?s->stable+1:1;
            if(s->stable>3) s->stable=3;
            if(!active) eye_tracker_set_roi(t,&loc->left,&loc->right);
            ready=s->stable>=2;
        }
        eye_tracker_set_face(t,&loc->face); s->last=*loc;
    }
    if(ready && detect_ms<=1000) eye_tracker_process(t,frame,stride,w,h,dt);
    else {
        eye_tracker_pause(t,detect_ms>1000?EYE_PAUSE_TIMING:pause);
    }
    if(detect_ms>1000||dt>1000) s->reason=TOO_SLOW;
    else if(t->cal_failed) s->reason=CAL_FAILED;
}
/* ABI consists only of uint32 values; names/order are checked in pc_gaze.py. */
unsigned pc_gaze_values(const PcGaze *s,u32 *out,unsigned capacity)
{
    const EyeTracker *t=&s->tracker;
    const u32 values[]={s->stable,s->last.valid,pc_gaze_can_calibrate(s),
        t->calibration_mask,t->calibration_stage,t->calibration_stable,t->stage_ms,
        t->calibration_settle_ms,t->cal_failed,t->valid,t->direction,t->armed,t->dwell_ms,
        t->event_seq,t->commit,s->reason,
        t->left_roi.x,t->left_roi.y,t->left_roi.w,t->left_roi.h,
        t->right_roi.x,t->right_roi.y,t->right_roi.w,t->right_roi.h,
        t->left.valid,t->left.normalized_x,t->left.x,t->left.y,
        t->left.dark_count,t->left.contrast,t->left.confidence,
        t->right.valid,t->right.normalized_x,t->right.x,t->right.y,
        t->right.dark_count,t->right.contrast,t->right.confidence,
        t->calibration[0][0],t->calibration[0][1],t->calibration[0][2],
        t->calibration[1][0],t->calibration[1][1],t->calibration[1][2],
        t->left.sample_count,t->left.selected_count,t->left.threshold,t->left.reason,
        t->right.sample_count,t->right.selected_count,t->right.threshold,t->right.reason,
        t->calibration_count[0],t->calibration_count[1],t->calibration_paused,
        EYE_CAL_SAMPLES,EYE_CAL_SETTLE_MS,EYE_TARGET_SIDE_PERCENT,EYE_TARGET_Y_PERCENT,
        (u32)(t->gaze_raw+512),(u32)(t->gaze_filtered+512),t->history_count,t->tracking_reason,
        t->calibration_mad[0][0],t->calibration_mad[0][1],t->calibration_mad[0][2],
        t->calibration_mad[1][0],t->calibration_mad[1][1],t->calibration_mad[1][2],
        t->cal_failure_reason,t->cal_failure_eye,t->cal_retry_stage,t->cal_failure_gap,t->cal_failure_noise,
        t->calibration_ready[0],t->calibration_ready[1],t->calibration_core_span[0],t->calibration_core_span[1],
        t->calibration_min[0],t->calibration_max[0],t->calibration_min[1],t->calibration_max[1]};
    unsigned count=sizeof(values)/sizeof(values[0]);
    if(out && capacity>=count) for(unsigned i=0;i<count;i++) out[i]=values[i];
    return count;
}
unsigned pc_feature_abi_value(unsigned index)
{
    const unsigned values[]={sizeof(EyeFeature),offsetof(EyeFeature,valid),offsetof(EyeFeature,x),
        offsetof(EyeFeature,y),offsetof(EyeFeature,dark_count),offsetof(EyeFeature,min_gray),
        offsetof(EyeFeature,max_gray),offsetof(EyeFeature,contrast),offsetof(EyeFeature,confidence),
        offsetof(EyeFeature,normalized_x),offsetof(EyeFeature,sample_count),
        offsetof(EyeFeature,selected_count),offsetof(EyeFeature,threshold),offsetof(EyeFeature,reason)};
    return index<sizeof(values)/sizeof(values[0])?values[index]:0;
}
