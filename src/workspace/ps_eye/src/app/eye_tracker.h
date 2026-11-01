#ifndef PS_EYE_TRACKER_H
#define PS_EYE_TRACKER_H

#include "xil_types.h"

typedef struct {
    u16 x;
    u16 y;
    u16 w;
    u16 h;
    u8 dark_margin;
    u8 bright_floor;
} EyeRoi;

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
} EyeFeature;

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
} EyeTracker;

int eye_analyze_rgb888(const u8 *frame, u32 stride, u32 width, u32 height,
                       const EyeRoi *roi, EyeFeature *out);
void eye_tracker_init(EyeTracker *tracker, const EyeRoi *left, const EyeRoi *right);
void eye_tracker_start_calibration(EyeTracker *tracker);
void eye_tracker_clear_calibration(EyeTracker *tracker);
void eye_tracker_process(EyeTracker *tracker, const u8 *frame, u32 stride,
                         u32 width, u32 height, u32 elapsed_ms);
const char *eye_direction_name(u8 direction);

#endif
