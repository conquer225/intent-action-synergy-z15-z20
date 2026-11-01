#include "hdmi_overlay.h"

typedef struct { u8 b, g, r; } OverlayColor;

static void put_pixel(u8 *frame, u32 stride, u32 width, u32 height,
                      int x, int y, OverlayColor c)
{
    u8 *p;
    if (x < 0 || y < 0 || (u32)x >= width || (u32)y >= height) return;
    p = frame + (u32)y * stride + (u32)x * 3u;
    p[0] = c.b; p[1] = c.g; p[2] = c.r;
}

static void fill_rect(u8 *frame, u32 stride, u32 width, u32 height,
                      int x0, int y0, int x1, int y1, OverlayColor c)
{
    int x, y;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > (int)width) x1 = (int)width;
    if (y1 > (int)height) y1 = (int)height;
    for (y = y0; y < y1; ++y)
        for (x = x0; x < x1; ++x)
            put_pixel(frame, stride, width, height, x, y, c);
}

static void border_rect(u8 *frame, u32 stride, u32 width, u32 height,
                        int x, int y, int w, int h, OverlayColor c)
{
    fill_rect(frame, stride, width, height, x, y, x + w, y + 3, c);
    fill_rect(frame, stride, width, height, x, y + h - 3, x + w, y + h, c);
    fill_rect(frame, stride, width, height, x, y, x + 3, y + h, c);
    fill_rect(frame, stride, width, height, x + w - 3, y, x + w, y + h, c);
}

static void crosshair(u8 *frame, u32 stride, u32 width, u32 height,
                      int x, int y, OverlayColor c)
{
    fill_rect(frame, stride, width, height, x - 10, y - 1, x + 11, y + 2, c);
    fill_rect(frame, stride, width, height, x - 1, y - 10, x + 2, y + 11, c);
}

void hdmi_overlay_apply(u8 *frame, u32 stride, u32 width, u32 height,
                        const EyeTracker *tracker)
{
    static const OverlayColor dark = {8, 8, 8};
    static const OverlayColor green = {0, 220, 0};
    static const OverlayColor red = {0, 0, 230};
    static const OverlayColor yellow = {0, 210, 220};
    static const OverlayColor blue = {220, 80, 0};
    OverlayColor state = tracker->valid ? green : red;
    int bar_h = height >= 32u ? 24 : (int)height;
    int progress;

    fill_rect(frame, stride, width, height, 0, 0, (int)width, bar_h, dark);
    /* Three direction cells; the current candidate is highlighted. */
    fill_rect(frame, stride, width, height, 8, 5, (int)width / 3 - 8, 19,
              tracker->candidate == EYE_DIR_LEFT ? yellow : blue);
    fill_rect(frame, stride, width, height, (int)width / 3 + 8, 5,
              (int)width * 2 / 3 - 8, 19,
              tracker->candidate == EYE_DIR_CENTER ? yellow : blue);
    fill_rect(frame, stride, width, height, (int)width * 2 / 3 + 8, 5,
              (int)width - 8, 19,
              tracker->candidate == EYE_DIR_RIGHT ? yellow : blue);
    /* Calibration progress is a thin green/yellow line at the bottom of the bar. */
    progress = (int)((u32)width * tracker->calibration_mask / 3u);
    if (tracker->calibration_stage != 0)
        progress += (int)((u32)width / 6u);
    if (progress > (int)width) progress = (int)width;
    fill_rect(frame, stride, width, height, 0, bar_h - 3, progress, bar_h, green);
    if (tracker->calibration_stage != 0)
        fill_rect(frame, stride, width, height, progress, bar_h - 3,
                  progress + (int)width / 12, bar_h, yellow);

    border_rect(frame, stride, width, height, tracker->left_roi.x,
                tracker->left_roi.y, tracker->left_roi.w, tracker->left_roi.h,
                tracker->left.valid ? green : red);
    border_rect(frame, stride, width, height, tracker->right_roi.x,
                tracker->right_roi.y, tracker->right_roi.w, tracker->right_roi.h,
                tracker->right.valid ? green : red);
    if (tracker->left.valid)
        crosshair(frame, stride, width, height, tracker->left.x, tracker->left.y, green);
    if (tracker->right.valid)
        crosshair(frame, stride, width, height, tracker->right.x, tracker->right.y, green);
    /* A committed event gets a short white marker at the center of the bar. */
    if (tracker->commit)
        fill_rect(frame, stride, width, height, (int)width / 2 - 12, 0,
                  (int)width / 2 + 12, 3, state);
}
