#ifndef PS_EYE_TRACKER_H
#define PS_EYE_TRACKER_H

#include "xil_types.h"

#define EYE_CAL_SAMPLES 16u
#define EYE_CAL_SETTLE_MS 2000u
#define EYE_TARGET_SIDE_PERCENT 8u
#define EYE_TARGET_Y_PERCENT 18u
#define EYE_FILTER_SAMPLES 5u
#define EYE_FILTER_WINDOW_MS 500u
#define EYE_RUNTIME_GAP_MS 250u
enum { EYE_CAL_OK=0, EYE_CAL_SEPARATION=1, EYE_CAL_ORDER=2, EYE_CAL_NOISE=3 };
enum { EYE_TRACK_WAIT=0, EYE_TRACK_OK=1, EYE_TRACK_FEATURE=2,
       EYE_TRACK_RANGE=3, EYE_TRACK_DISAGREE=4, EYE_TRACK_BOUNDARY=5,
       EYE_TRACK_SWITCH=6, EYE_TRACK_TIMING=7 };
enum { EYE_PAUSE_LEFT=1, EYE_PAUSE_RIGHT=2, EYE_PAUSE_PAIR=4,
       EYE_PAUSE_TIMING=8, EYE_PAUSE_POSITION=16 };

typedef struct {
    u16 x;
    u16 y;
    u16 w;
    u16 h;
    u8 dark_margin;
    u8 bright_floor;
} EyeRoi;

typedef enum {
    EYE_FEATURE_UNMEASURED=0, EYE_FEATURE_OK=1, EYE_FEATURE_ROI=2,
    EYE_FEATURE_CONTRAST=3, EYE_FEATURE_AREA=4, EYE_FEATURE_SHAPE=5,
    EYE_FEATURE_AMBIGUOUS=6
} EyeFeatureReason;

typedef struct {
    u8 valid;
    u16 x;
    u16 y;
    u16 dark_count;
    u8 min_gray;
    u8 max_gray;
    u8 contrast;
    u8 confidence;
    u16 normalized_x;
    u16 sample_count;
    u16 selected_count;
    u8 threshold;
    u8 reason;
} EyeFeature;

typedef struct {
    u16 x;
    u16 y;
    u16 w;
    u16 h;
    u8 valid;
} EyeFaceBox;

typedef enum {
    EYE_DIR_INVALID = 0,
    EYE_DIR_LEFT = 1,
    EYE_DIR_CENTER = 2,
    EYE_DIR_RIGHT = 3
} EyeDirection;

typedef struct {
    EyeRoi left_roi;
    EyeRoi right_roi;
    EyeFeature left;
    EyeFeature right;
    u16 calibration[2][3];
    u8 calibration_mask;
    u8 calibration_stage;
    u8 calibration_stable;
    u16 calibration_min[2];
    u16 calibration_max[2];
    u8 valid;
    u8 direction;
    u8 candidate;
    u8 confidence;
    u32 frame_count;
    u32 invalid_count;
    u32 dwell_ms;
    u32 event_seq;
    u8 commit;
    EyeFaceBox face;
    u8 armed;
    u8 cal_failed;
    u32 stage_ms;
    u32 calibration_sum[2];
    u32 calibration_settle_ms;
    u8 calibration_count[2];
    u8 calibration_outliers[2];
    u8 calibration_paused;
    u16 calibration_samples[2][EYE_CAL_SAMPLES];
    u16 calibration_mad[2][3];
    int gaze_raw, gaze_filtered; /* signed personal scale: -256, 0, +256 */
    int history[EYE_FILTER_SAMPLES];
    u32 history_age[EYE_FILTER_SAMPLES];
    u8 history_count, pending_direction, pending_count, tracking_reason;
    u32 pending_ms;
    u8 calibration_ready[2];
    u16 calibration_core_span[2];
    u8 cal_failure_reason, cal_failure_eye, cal_retry_stage;
    u16 cal_failure_gap, cal_failure_noise;
} EyeTracker;

int eye_analyze_rgb888(const u8 *frame, u32 stride, u32 width, u32 height,
                       const EyeRoi *roi, EyeFeature *out);
void eye_tracker_init(EyeTracker *tracker, const EyeRoi *left, const EyeRoi *right);
void eye_tracker_set_roi(EyeTracker *tracker, const EyeRoi *left, const EyeRoi *right);
void eye_tracker_set_face(EyeTracker *tracker, const EyeFaceBox *face);
void eye_tracker_invalidate(EyeTracker *tracker);
void eye_tracker_pause(EyeTracker *tracker, u8 reason);
void eye_tracker_start_calibration(EyeTracker *tracker);
int eye_tracker_retry_calibration(EyeTracker *tracker);
void eye_tracker_clear_calibration(EyeTracker *tracker);
void eye_tracker_process(EyeTracker *tracker, const u8 *frame, u32 stride,
                         u32 width, u32 height, u32 elapsed_ms);
const char *eye_direction_name(u8 direction);

#endif
