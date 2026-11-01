#include "eye_tracker.h"

#define MIN_DARK_PIXELS 10u
#define MAX_DARK_PIXELS 18000u
#define CAL_STABLE_FRAMES 16u
#define CAL_SETTLE_MS 2000u
#define DWELL_LEFT_RIGHT_MS 750u
#define DWELL_CENTER_MS 350u

static u8 gray_at(const u8 *p)
{
    /* The capture IP emits {R,G,B}; AXI memory byte order is B,G,R. */
    return (u8)((29u * p[0] + 150u * p[1] + 77u * p[2]) >> 8);
}

int eye_analyze_rgb888(const u8 *frame, u32 stride, u32 width, u32 height,
                       const EyeRoi *roi, EyeFeature *out)
{
    u32 x, y, count = 0, sum = 0, dark_sum_x = 0, dark_sum_y = 0;
    u8 min_gray = 255, max_gray = 0;
    u16 x0 = roi->x, y0 = roi->y;
    *out = (EyeFeature){0};
    u16 x1 = (u16)(roi->x + roi->w), y1 = (u16)(roi->y + roi->h);
    u8 threshold;
    if (x1 > width) x1 = (u16)width;
    if (y1 > height) y1 = (u16)height;
    if (x0 >= x1 || y0 >= y1) return 0;

    for (y = y0; y < y1; y += 2) {
        const u8 *line = frame + y * stride;
        for (x = x0; x < x1; x += 2) {
            u8 g = gray_at(line + x * 3u);
            if (g < min_gray) min_gray = g;
            if (g > max_gray) max_gray = g;
            sum += g;
            count++;
        }
    }
    if (count == 0 || max_gray <= min_gray + 8u) return 0;

    threshold = (u8)(min_gray + roi->dark_margin);
    if ((u16)threshold > (u16)min_gray + (u16)(max_gray - min_gray) / 2u)
        threshold = (u8)(min_gray + (max_gray - min_gray) / 2u);
    for (y = y0; y < y1; y += 2) {
        const u8 *line = frame + y * stride;
        for (x = x0; x < x1; x += 2) {
            u8 g = gray_at(line + x * 3u);
            if (g <= threshold) {
                dark_sum_x += x;
                dark_sum_y += y;
                out->dark_count++;
            }
        }
    }
    out->min_gray = min_gray;
    out->max_gray = max_gray;
    out->contrast = (u8)(max_gray - min_gray);
    out->confidence = (u8)((out->contrast > 96u ? 96u : out->contrast) +
                           (out->dark_count >= MIN_DARK_PIXELS ? 32u : 0u));
    out->valid = (out->dark_count >= MIN_DARK_PIXELS &&
                  out->dark_count <= MAX_DARK_PIXELS &&
                  out->contrast >= 12u);
    if (out->valid) {
        out->x = (u16)(dark_sum_x / out->dark_count);
        out->y = (u16)(dark_sum_y / out->dark_count);
        out->normalized_x = (u16)(((u32)(out->x - roi->x) * 256u) / roi->w);
    }
    (void)sum;
    return out->valid;
}

static void clear_feature(EyeFeature *f) { *f = (EyeFeature){0}; }

void eye_tracker_init(EyeTracker *tracker, const EyeRoi *left, const EyeRoi *right)
{
    *tracker = (EyeTracker){0};
    tracker->left_roi = *left;
    tracker->right_roi = *right;
}

void eye_tracker_clear_calibration(EyeTracker *tracker)
{
    tracker->calibration_mask = 0;
    tracker->calibration_stage = 0;
    tracker->calibration_stable = 0;
    tracker->valid = 0;
    tracker->direction = EYE_DIR_INVALID;
    tracker->candidate = EYE_DIR_INVALID;
    tracker->dwell_ms = 0;
    tracker->commit = 0;
}

void eye_tracker_start_calibration(EyeTracker *tracker)
{
    eye_tracker_clear_calibration(tracker);
    tracker->calibration_stage = 1;
}

static u8 classify_one(const EyeTracker *t, const EyeFeature *f, u8 eye)
{
    u32 dl, dc, dr, best;
    if (!f->valid || !(t->calibration_mask & (1u << 0)) ||
        !(t->calibration_mask & (1u << 1)) || !(t->calibration_mask & (1u << 2)))
        return EYE_DIR_INVALID;
    dl = f->normalized_x > t->calibration[eye][0] ?
         f->normalized_x - t->calibration[eye][0] : t->calibration[eye][0] - f->normalized_x;
    dc = f->normalized_x > t->calibration[eye][1] ?
         f->normalized_x - t->calibration[eye][1] : t->calibration[eye][1] - f->normalized_x;
    dr = f->normalized_x > t->calibration[eye][2] ?
         f->normalized_x - t->calibration[eye][2] : t->calibration[eye][2] - f->normalized_x;
    best = dl;
    if (dc < best) best = dc;
    if (dr < best) best = dr;
    if (best > 48u) return EYE_DIR_INVALID;
    if (best == dl) return EYE_DIR_LEFT;
    if (best == dc) return EYE_DIR_CENTER;
    return EYE_DIR_RIGHT;
}

void eye_tracker_process(EyeTracker *tracker, const u8 *frame, u32 stride,
                         u32 width, u32 height, u32 elapsed_ms)
{
    u8 dl, dr, candidate = EYE_DIR_INVALID;
    tracker->commit = 0;
    clear_feature(&tracker->left);
    clear_feature(&tracker->right);
    eye_analyze_rgb888(frame, stride, width, height, &tracker->left_roi, &tracker->left);
    eye_analyze_rgb888(frame, stride, width, height, &tracker->right_roi, &tracker->right);
    tracker->frame_count++;
    if (!tracker->left.valid || !tracker->right.valid) {
        tracker->invalid_count++;
        tracker->valid = 0;
        tracker->dwell_ms = 0;
        return;
    }
    if (tracker->calibration_stage != 0 && tracker->calibration_stage <= 3) {
        if (tracker->dwell_ms < CAL_SETTLE_MS) {
            tracker->dwell_ms += elapsed_ms;
        } else {
            if (tracker->calibration_stable == 0) {
                tracker->calibration[0][tracker->calibration_stage - 1] = tracker->left.normalized_x;
                tracker->calibration[1][tracker->calibration_stage - 1] = tracker->right.normalized_x;
                tracker->calibration_min[0] = tracker->left.normalized_x;
                tracker->calibration_min[1] = tracker->right.normalized_x;
                tracker->calibration_max[0] = tracker->left.normalized_x;
                tracker->calibration_max[1] = tracker->right.normalized_x;
                tracker->calibration_stable = 1;
            } else if (tracker->calibration_stable < CAL_STABLE_FRAMES) {
                if (tracker->left.normalized_x < tracker->calibration_min[0]) tracker->calibration_min[0] = tracker->left.normalized_x;
                if (tracker->right.normalized_x < tracker->calibration_min[1]) tracker->calibration_min[1] = tracker->right.normalized_x;
                if (tracker->left.normalized_x > tracker->calibration_max[0]) tracker->calibration_max[0] = tracker->left.normalized_x;
                if (tracker->right.normalized_x > tracker->calibration_max[1]) tracker->calibration_max[1] = tracker->right.normalized_x;
                if ((u16)(tracker->calibration_max[0] - tracker->calibration_min[0]) > 10u ||
                    (u16)(tracker->calibration_max[1] - tracker->calibration_min[1]) > 10u) {
                    tracker->calibration_stable = 0;
                    tracker->dwell_ms = CAL_SETTLE_MS;
                    tracker->valid = 0;
                    return;
                }
                tracker->calibration_stable++;
            }
            if (tracker->calibration_stable >= CAL_STABLE_FRAMES) {
                tracker->calibration_mask |= (1u << (tracker->calibration_stage - 1));
                tracker->calibration_stage++;
                tracker->calibration_stable = 0;
                tracker->dwell_ms = 0;
                if (tracker->calibration_stage > 3) tracker->calibration_stage = 0;
            }
        }
        tracker->valid = 0;
        return;
    }
    dl = classify_one(tracker, &tracker->left, 0);
    dr = classify_one(tracker, &tracker->right, 1);
    if (dl == EYE_DIR_INVALID || dr == EYE_DIR_INVALID || dl != dr) {
        tracker->valid = 0;
        tracker->dwell_ms = 0;
        return;
    }
    candidate = dl;
    tracker->valid = 1;
    tracker->candidate = candidate;
    tracker->confidence = (tracker->left.confidence + tracker->right.confidence) / 2u;
    if (candidate != tracker->direction) {
        tracker->dwell_ms = 0;
        tracker->direction = candidate;
    } else {
        tracker->dwell_ms += elapsed_ms;
    }
    if ((candidate == EYE_DIR_LEFT || candidate == EYE_DIR_RIGHT) &&
        tracker->dwell_ms >= DWELL_LEFT_RIGHT_MS) {
        tracker->event_seq++;
        tracker->commit = 1;
        tracker->dwell_ms = 0;
    } else if (candidate == EYE_DIR_CENTER && tracker->dwell_ms >= DWELL_CENTER_MS) {
        tracker->dwell_ms = 0;
    }
}

const char *eye_direction_name(u8 direction)
{
    switch (direction) {
    case EYE_DIR_LEFT: return "LEFT";
    case EYE_DIR_CENTER: return "CENTER";
    case EYE_DIR_RIGHT: return "RIGHT";
    default: return "INVALID";
    }
}
